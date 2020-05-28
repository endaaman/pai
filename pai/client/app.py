import os
import io
import json
import time
import threading
from enum import Enum, auto
import math
from collections import namedtuple, OrderedDict
import asyncio
from aiohttp.client_exceptions import ClientConnectorError
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

from .utils import create_model, debounce, check_device, glib_async, applay_pil_image_to_gtk_image
from .api import analyze_image, download_image
from .ws import WS
from .ui import GstWidget, MessageDialog
from .models import Result, Detail
from .config import GST_SOURCE, RESULT_TREE_UPDATE_INTERVAL, RECONNECT_INTERVAL


asyncio.set_event_loop_policy(gbulb.gtk.GtkEventLoopPolicy())
loop = asyncio.get_event_loop()


class Mode(Enum):
    SCANNING = auto()
    INSPECTING = auto()


class App:
    def __init__(self):
        Gst.init(None)

        self.data_detail = None
        self.data_result = None
        self.data_show_control = False
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
        self.set_mode(Mode.SCANNING)

    def flush_events(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def redraw_widget(self, window):
        window.queue_resize()
        self.flush_events()

    def set_mode(self, mode):
        self.mode = mode
        is_scanning = mode == Mode.SCANNING
        is_inspecting = mode == Mode.INSPECTING
        result = self.data_result
        detail = self.data_detail
        show_control = self.data_show_control
        if is_inspecting:
            title = f'Mode: inspecting - {result.name}'
        else:
            title = 'Mode: scanning'

        self.main_window.set_title(title)
        self.analyze_menu.set_visible(is_scanning)

        self.back_to_scan_menu.set_visible(is_inspecting)
        self.opacity_scale.set_visible(is_inspecting)
        self.overlay_select_combo.set_visible(is_inspecting)
        self.gst_widget.set_visible(not is_inspecting)
        self.canvas_image.set_visible(is_inspecting)
        self.control_box.set_visible(is_inspecting)

        if is_inspecting:
            for row in self.overlay_select_store:
                if row[1] == -1:
                    continue
                self.overlay_select_store.remove(row.iter)
            for i, o in enumerate(result.overlays):
                self.overlay_select_store.append([o, i])
            self.adjust_image()
        else:
            self.canvas_image.clear()

        self.redraw_widget(self.main_window)

    def on_main_window_size_allocate(self, *args):
        if self.data_result:
            self.adjust_image()

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
                self.control_box.set_visible(not self.control_box.get_visible())
            self.redraw_widget(self.main_window)
            return

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

    def on_opacity_scale_changed(self, widget, *args):
        print('scale:', self.opacity_scale.get_value())
        # needed to redraw scale slider

        self.data_overlay_opacity = self.opacity_scale.get_value() / 100
        self.adjust_image()
        self.redraw_widget(self.main_window)

    def on_overlay_select_combo_changed(self, widget, *args):
        row = self.overlay_select_store[self.overlay_select_combo.get_active()]
        self.data_overlay_index = row[1]
        self.adjust_image()

    @glib_async(loop)
    async def on_analyze_menu_activate(self, *args):
        if self.mode != Mode.SCANNING:
            MessageDialog.show('Do analyze only when scanning mode')
            return

        self.data_result = None
        snapshot = self.gst_widget.take_snapshot()
        name = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            result = await analyze_image(snapshot, name)
            original_image = await download_image(result.name, result.original)
            overlay_images = []
            for o in result.overlays:
                i = await download_image(result.name, o)
                overlay_images.append(i)
            detail = Detail(result, original_image, overlay_images)
        except ClientConnectorError as e:
            MessageDialog.show('Server is not running')
            return
        except Exception as e:
            MessageDialog.show(f'Server Error: {e}')
            return

        print('Result:', result)
        print('Detail:', detail)
        self.data_result = result
        self.data_detail = detail
        self.data_overlay_index = -1
        self.set_mode(Mode.INSPECTING)

    def on_back_to_scan_menu_activate(self, *args):
        self.data_result = None
        self.data_detail = None
        self.data_overlay_index = -1
        self.set_mode(Mode.SCANNING)

    def on_browser_menu_activate(self, *args):
        print('TODO: open browser')
        # self.opacity_scale.set_visible(not self.opacity_scale.get_visible())

    def on_menu_menu_activate(self, *args):
        self.menu_window.show_all()
        self.refresh_result_tree()

    def on_fullscreen_toggler_menu_toggled(self, widget, *args):
        if widget.get_active():
            self.main_window.maximize()
        else:
            self.main_window.unmaximize()

    def on_main_window_key_release(self, widget, event, *args):
        if event.keyval == Gdk.KEY_Escape:
            widget.unmaximize()

    def on_quit_menu_activate(self, *args):
        self.main_window.close()

    def on_contorol_window_key_release(self, widget, event, *args):
        if event.keyval == Gdk.KEY_Escape:
            self.menu_window.close()
            return

    def on_contorol_window_delete(self, *args):
        self.menu_window.hide()
        return True

    def on_result_filter_combo_changed(self, widget, *args):
        self.refresh_result_tree()

    def on_result_tree_row_activated(self, widget, path, column):
        pass
        # row = self.result_store[path]
        # result = find_results(self.results.get(), row[1], row[0])
        # self.result.set(result)
        # self.menu_window.hide()

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

    def adjust_image(self):
        '''Set image to canvas_image and adjust size to window.
        '''
        if not self.data_detail:
            print('Tried to adjust image when detail == None')
            return

        original_image = self.data_detail.original_image
        opacity = self.data_overlay_opacity

        print(f'adjust_image: index={self.data_overlay_index} {self.data_overlay_opacity}')
        show_overlay = self.data_overlay_index > -1
        if show_overlay:
            overlay_image = self.data_detail.overlay_images[self.data_overlay_index]
            # blended_image = original_image.copy()
            # mask = Image.new('L', original_image.size, math.floor(255 * opacity))
            # blended_image.paste(overlay_image, (0, 0), mask)
            blended_image = Image.blend(original_image.convert('RGBA'), overlay_image, alpha=opacity)
        else:
            blended_image = original_image

        adjusted_image = self.get_adjusted_pil_image(blended_image)
        applay_pil_image_to_gtk_image(self.canvas_image, adjusted_image)


    def refresh_result_tree(self):
        pass

    def start(self):
        loop.run_forever()
