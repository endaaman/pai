import os
import io
import json
import time
import threading
from enum import Enum, auto
import math
from collections import namedtuple, OrderedDict
import asyncio
from urllib.parse import urljoin
from pprint import pprint
from datetime import datetime

import numpy as np
from PIL import Image
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gst
import aiohttp
import gbulb
import gbulb.gtk

from .utils import debounce, glib_async, applay_pil_image_to_gtk_image, Withable, image_overlay
from .api import analyze_image, fetch_detail, fetch_results
from .ws import WS
from .ui import GstWidget, MessageDialog
from .config import GST_SOURCE, RESULT_TREE_UPDATE_INTERVAL, RECONNECT_INTERVAL
from pai.common import find_results


FRAME_UPDATE_INTERVAL = 100

asyncio.set_event_loop_policy(gbulb.gtk.GtkEventLoopPolicy())
loop = asyncio.get_event_loop()


class Mode(Enum):
    SCANNING = auto()
    INSPECTING = auto()


class App:
    def __init__(self):
        Gst.init(None)

        self.mode = Mode.SCANNING
        self.data_loading = False
        self.data_detail = None
        self.data_result = None
        self.data_results = []
        self.data_show_control = False
        self.data_show_overlay = True
        self.data_overlay_index = -1
        self.data_overlay_opacity = 0.5

        builder = Gtk.Builder()
        builder.add_from_file(os.path.dirname(__file__) + '/app.glade')

        self.main_window = builder.get_object('main_window')
        self.container_overlay = builder.get_object('container_overlay')

        self.control_box = builder.get_object('control_box')
        self.notifications_grid = builder.get_object('notifications_grid')
        self.opacity_scale = builder.get_object('opacity_scale')
        self.overlay_select_combo = builder.get_object('overlay_select_combo')
        self.overlay_select_store = builder.get_object('overlay_select_store')

        self.gst_widget = GstWidget(GST_SOURCE)
        self.canvas_image = builder.get_object('canvas_image')

        self.menu_window = builder.get_object('menu_window')
        self.notebook = builder.get_object('notebook')
        self.result_container = builder.get_object('result_container')
        self.result_tree = builder.get_object('result_tree')
        self.result_store = builder.get_object('result_store')
        self.result_filter_combo = builder.get_object('result_filter_combo')
        self.result_filter_store = builder.get_object('result_filter_store')

        self.menu = builder.get_object('menu')
        self.analyze_menu = builder.get_object('analyze_menu')
        self.back_to_scan_menu = builder.get_object('back_to_scan_menu')
        self.fullscreen_toggler_menu = builder.get_object('fullscreen_toggler_menu')
        self.show_control_toggler_menu = builder.get_object('show_control_toggler_menu')

        self.container_overlay.add_overlay(self.gst_widget)
        self.container_overlay.reorder_overlay(self.gst_widget, 0)

        builder.connect_signals(self)

        self.__last_triggered_time = None

        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.dirname(__file__) + '/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)
        # self.main_window.maximize()

        self.main_window.show_all()
        self.current_window_size = self.main_window.get_size()
        self.set_mode(Mode.SCANNING)

    def flush_events(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def redraw_widget(self, window):
        window.queue_resize()
        self.flush_events()

    def set_loading(self, flag):
        self.data_loading = flag
        cursor = Gdk.Cursor(Gdk.CursorType.WATCH) if flag else None
        self.main_window.get_property('window').set_cursor(cursor)

    def while_loading(self):
        return Withable(
            lambda: self.set_loading(False),
            lambda: self.set_loading(True))

    def set_mode(self, mode):
        self.mode = mode
        is_scanning = mode == Mode.SCANNING
        is_inspecting = mode == Mode.INSPECTING
        result = self.data_result
        if is_inspecting:
            title = f'Mode: inspecting - {result.name}'
        else:
            title = 'Mode: scanning'

        self.main_window.set_title(title)
        self.analyze_menu.set_visible(is_scanning)
        if is_scanning:
            self.gst_widget.start()
        else:
            self.gst_widget.stop()
        self.gst_widget.set_visible(is_scanning)

        self.back_to_scan_menu.set_visible(is_inspecting)
        self.show_control_toggler_menu.set_visible(is_inspecting)
        self.canvas_image.set_visible(is_inspecting)

        if is_inspecting:
            self.control_box.show_all()
        else:
            self.control_box.hide()

        if is_inspecting:
            for row in self.overlay_select_store:
                self.overlay_select_store.remove(row.iter)
            for i, o in enumerate(result.overlays):
                self.overlay_select_store.append([o, i])
            self.overlay_select_combo.set_active(0)
            self.adjust_canvas_image()
        else:
            self.canvas_image.clear()

        # self.redraw_widget(self.main_window)

    def on_main_window_size_allocate(self, *args):
        pass
        # if self.data_result:
        #     self.adjust_canvas_image()

        # if self.mode == Mode.SCANNING:
        #     self.redraw_widget(self.main_window)

    def on_main_window_delete(self, *args):
        # Gtk.main_quit(*args)
        loop.stop()

    def on_main_window_click(self, widget, event):
        ###* GUARD START
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return
        if self.__last_triggered_time == event.time:
            return
        self.__last_triggered_time = event.time
        ###* GUARD END

        if event.button == 1:
            if self.mode == Mode.INSPECTING:
                self.data_show_overlay = not self.data_show_overlay
                self.adjust_canvas_image()
                # self.control_box.set_visible(not self.control_box.get_visible())
                self.redraw_widget(self.main_window)
            else:
                self.redraw_widget(self.gst_widget)

        if event.button == 3:
            self.menu.popup(None, None, None, None, event.button, event.time)
            return

    def on_main_window_state_event(self, widget, event):
        if bool(event.changed_mask & Gdk.WindowState.MAXIMIZED):
            flag = bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
            if flag:
                self.main_window.fullscreen()
            else:
                self.main_window.unfullscreen()
            self.fullscreen_toggler_menu.set_active(flag)

            # if self.mode == Mode.SCANNING:
            #     self.redraw_widget(self.gst_widget)

    def opacity_changed(self):
        print('scale:', self.opacity_scale.get_value())
        self.data_overlay_opacity = self.opacity_scale.get_value() / 100
        self.adjust_canvas_image()
        # # needed to redraw scale slider
        # self.redraw_widget(self.main_window)

    def on_opacity_scale_changed(self, widget, *args):
        debounce(100, self.opacity_changed)

    def on_overlay_select_combo_changed(self, widget, *args):
        active = self.overlay_select_combo.get_active()
        # print('active: ', active)
        # row = self.overlay_select_store[active]
        self.data_overlay_index = active
        self.data_show_overlay = True
        self.adjust_canvas_image()

    @glib_async(loop)
    async def on_analyze_menu_activate(self, *args):
        if self.mode != Mode.SCANNING:
            MessageDialog.show('Do analyze only when scanning mode')
            return
        if self.data_loading:
            MessageDialog.show('Please wait for current job')
            return

        self.data_result = None
        name = datetime.now().strftime("%Y%m%d_%H%M%S")

        with self.while_loading():
            snapshot = self.gst_widget.take_snapshot()
            try:
                result = await analyze_image(snapshot, name)
                detail = await fetch_detail(result)
            except Exception as e:
                MessageDialog.show(f'Server Error: {e}')
                return

        print('Result:', result)
        print('Detail:', detail)
        self.data_result = result
        self.data_detail = detail
        self.data_overlay_index = 0
        self.data_show_overlay = True
        self.set_mode(Mode.INSPECTING)

    def on_back_to_scan_menu_activate(self, *args):
        self.data_result = None
        self.data_detail = None
        self.data_overlay_index = 0
        self.data_show_overlay = True
        self.set_mode(Mode.SCANNING)

    def on_browser_menu_activate(self, *args):
        print('TODO: open browser')
        # self.opacity_scale.set_visible(not self.opacity_scale.get_visible())

    @glib_async(loop)
    async def on_menu_menu_activate(self, *args):
        if self.data_loading:
            MessageDialog.show('Please wait for current job')
            return

        with self.while_loading():
            try:
                results = await fetch_results()
            except Exception as e:
                MessageDialog.show('Server error: ' + str(e))
                return

        self.data_results = results
        self.menu_window.show_all()
        self.refresh_result_tree()

    def on_fullscreen_toggler_menu_toggled(self, widget, *args):
        if widget.get_active():
            self.main_window.maximize()
        else:
            self.main_window.unmaximize()

    def on_show_control_toggler_menu_toggled(self, widget, *args):
        if widget.get_active():
            self.control_box.show_all()
        else:
            self.control_box.hide()

    def on_main_window_key_release(self, widget, event, *args):
        if event.keyval == Gdk.KEY_Escape:
            widget.unmaximize()

    def on_quit_menu_activate(self, *args):
        self.main_window.close()

    def on_menu_window_key_release(self, widget, event, *args):
        if event.keyval == Gdk.KEY_Escape:
            self.menu_window.close()
            return

    def on_menu_window_delete(self, *args):
        self.menu_window.hide()
        return True

    def on_result_filter_combo_changed(self, widget, *args):
        self.refresh_result_tree()

    @glib_async(loop)
    async def on_result_tree_row_activated(self, widget, path, column):
        if self.data_loading:
            MessageDialog.show('Please wait for current job')
            return

        row = self.result_store[path]
        name = row[0]
        result = find_results(self.data_results, name)
        self.menu_window.close()
        if not result:
            MessageDialog.show('No result found named "{name}"')
            return

        with self.while_loading():
            try:
                detail = await fetch_detail(result)
            except Exception as e:
                MessageDialog.show(f'Server Error: {e}')
                return

        print('Result:', result)
        print('Detail:', detail)
        self.data_result = result
        self.data_detail = detail
        self.data_overlay_index = 0
        self.data_show_overlay = True
        self.set_mode(Mode.INSPECTING)

    def get_adjusted_pil_image(self, pil_image):
        win_w, win_h = self.main_window.get_size()
        img_w, img_h = pil_image.size
        if win_w/win_h > img_w/img_h:
            new_w = math.floor(img_w * win_h / img_h)
            new_h = win_h
        else:
            new_w = win_w
            new_h = math.floor(img_h * win_w / img_w)
        # image = cv2.resize(image, None, fx=new_w/img_w, fy=new_h/img_h, interpolation=cv2.INTER_CUBIC)
        # pb = cv2pixbuf(image)
        return pil_image.resize((new_w, new_h))


    def adjust_canvas_image(self):
        '''Set image to canvas_image and adjust size to window.
        '''
        if not self.data_detail:
            print('Tried to adjust image when detail == None')
            return

        original_image = self.data_detail.original_image
        show_overlay = self.data_show_overlay
        opacity = self.data_overlay_opacity

        print(f'adjust_canvas_image: index={self.data_overlay_index} opacity={self.data_overlay_opacity}')
        valid_index = -1 < self.data_overlay_index < len(self.overlay_select_store)
        if valid_index and show_overlay:
            overlay_image = self.data_detail.overlay_images[self.data_overlay_index]
            blended_image = image_overlay(original_image, overlay_image, opacity)
        else:
            blended_image = original_image

        adjusted_image = self.get_adjusted_pil_image(blended_image)
        applay_pil_image_to_gtk_image(self.canvas_image, adjusted_image)

    def refresh_result_tree(self):
        if not self.menu_window.get_visible():
            return True
        scroll_value = self.result_container.get_vadjustment().get_value()
        selected_rows = self.result_tree.get_selection().get_selected_rows()[1]
        self.result_store.clear()
        for r in self.data_results:
            self.result_store.append([r.name, ', '.join(r.overlays)])

        if len(selected_rows) > 0:
            self.result_tree.set_cursor(selected_rows[0].get_indices()[0])
        self.result_container.get_vadjustment().set_value(scroll_value)

        self.redraw_widget(self.menu_window)

    def on_frame_update(self):
        size = self.main_window.get_size()
        if size != self.current_window_size:
            if self.mode == Mode.INSPECTING:
                self.adjust_canvas_image()

        self.current_window_size = size
        return True

    def start(self):
        GLib.timeout_add(FRAME_UPDATE_INTERVAL, self.on_frame_update)
        loop.run_forever()
