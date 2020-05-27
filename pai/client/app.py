import os
import io
import json
import time
import threading
import enum
import math
from collections import namedtuple, OrderedDict
import asyncio
from urllib.parse import urljoin
from pprint import pprint

import numpy as np

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gst
import gbulb
import gbulb.gtk

from .utils import create_model, debounce, check_device, async_glib, pil2pixbuf
from .api import upload_image, download_image
from .ws import WS
from .ui import GstWidget
from .models import Result, Detail
from .config import GST_SOURCE, RESULT_TREE_UPDATE_INTERVAL, RECONNECT_INTERVAL


asyncio.set_event_loop_policy(gbulb.gtk.GtkEventLoopPolicy())
loop = asyncio.get_event_loop()


def get_grid_row_count(grid):
    count = 0
    for child in grid.get_children():
        top = grid.child_get_property(child, 'top-attach')
        height = grid.child_get_property(child, 'width')
        count = max(count, top + height)
    return count


class App:
    def __init__(self):
        Gst.init(None)

        Model = create_model(self.update_view, loop)

        self.detail = Model('detail', None)
        self.result = Model('result', None)
        self.show_control = Model('show_control', False)

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
        self.original_image = builder.get_object('original_image')

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
        self.update_view(True)

    def flush_events(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def redraw_widget(self, window):
        window.queue_resize()
        self.flush_events()

    def update_view(self, force=False):
        print('update_view')
        result = self.result.get()
        detail = self.detail.get()
        show_control = self.show_control.get()

        if force or self.result.changed:
            print('update_view: result')
            if result:
                title = f'Inspecting: {result.name}'
            else:
                title = 'Scanning'
            self.main_window.set_title(title)
            self.analyze_menu.set_visible(not result)
            self.back_to_scan_menu.set_visible(result)
            self.opacity_scale.set_visible(result)
            self.overlay_select_combo.set_visible(result)
            self.gst_widget.set_visible(not result)
            self.original_image.set_visible(result)

            if result:
                for row in self.overlay_select_store:
                    if row[1] == -1:
                        continue
                    self.overlay_select_store.remove(row.iter)
                for i, o in enumerate(result.overlays):
                    self.overlay_select_store.append([o.name, i])

            if not result:
                self.detail.set(None)
            else:
                self.download_detail()
                # ↓↓↓danger↓↓↓
                # self.show_control.set(True)

        if force or self.detail.changed:
            print('update_view: detail')
            if detail:
                self.adjust_image()
            else:
                self.original_image.clear()

        if force or self.show_control.changed:
            print('update_view: show_control')
            self.control_box.set_visible(show_control and self.result.get())

        self.redraw_widget(self.main_window)

    @async_glib(loop)
    async def download_detail(self):
        print('download_detail')
        result = self.result.get()
        original_image = await download_image('/'.join(['generated', result.name, result.original]))
        overlay_images = []
        for o in result.overlays:
            i = await download_image('/'.join(['generated', result.name, o]))
            overlay_images.append(i)

        self.detail.set(Detail(result, original_image, overlay_images))

    def on_main_window_size_allocate(self, *args):
        if self.result.get():
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
            self.show_control.set(not self.show_control.get())
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
        # def cb():
        #     self.opacity_scale.queue_draw()
        #     self.flush_events()
        #     self.refresh_image()
        #     self.redraw(self.main_window)
        print('scale:', self.opacity_scale.get_value())
        # needed to redraw scale slider
        self.redraw_widget(self.main_window)


    def on_overlay_select_combo_changed(self, widget, *args):
        self.refresh_image()

    @async_glib(loop)
    async def on_analyze_menu_activate(self, *args):
        snapshot = self.gst_widget.take_snapshot()
        result = await upload_image(snapshot)
        self.result.set(result)

    def on_browser_menu_activate(self, *args):
        print('TODO: open browser')
        # self.opacity_scale.set_visible(not self.opacity_scale.get_visible())

    def on_back_to_scan_menu_activate(self, *args):
        self.result.set(None)

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


    def adjust_image(self):
        # print('adjust_image')
        image = self.detail.get().original_image
        if not image:
            return
        win_w, win_h = self.main_window.get_size()
        img_w, img_h = image.size
        if win_w/win_h > img_w/img_h:
            new_w = math.floor(img_w * win_h / img_h)
            new_h = win_h
        else:
            new_w = win_w
            new_h = math.floor(img_h * win_w / img_w)
        # image = cv2.resize(image, None, fx=new_w/img_w, fy=new_h/img_h, interpolation=cv2.INTER_CUBIC)
        # pb = cv2pixbuf(image)
        pb = pil2pixbuf(image.resize((new_w, new_h)))
        self.original_image.set_from_pixbuf(pb)


    def refresh_image(self):
        return
        if not self.result.get():
            return
        row = self.overlay_select_store[self.overlay_select_combo.get_active()]
        selected_overlay_index = row[1]
        detail = self.detail.get()
        if selected_overlay_index == -1:
            self.image.set(detail.original_image)
            return
        overlay = detail.overlay_images[selected_overlay_index]
        opacity = self.opacity_adjustment.get_value() / 100
        blended = overlay_transparent(detail.original_image, overlay, alpha=opacity)
        self.image.set(blended)


    def refresh_result_tree(self):
        pass

    def start(self):
        loop.run_forever()
