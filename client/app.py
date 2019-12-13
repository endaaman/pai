import os
import io
import json
import time
import argparse
import threading
import enum
from collections import namedtuple, OrderedDict
import asyncio
from urllib.parse import urljoin

import numpy as np
import cv2

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gst
import gbulb
import gbulb.gtk

from utils import Fps, Model, debounce, check_device, async_glib, overlay_transparent
from api import upload_image
from ws import WS
from ui import GstWidget
from models import Result, Detail, convert_to_results, find_results

asyncio.set_event_loop_policy(gbulb.gtk.GtkEventLoopPolicy())

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action="store_true")
args = parser.parse_args()

ARG_TEST = args.test

API_HOST = 'localhost:8080'
RECONNECT_INTERVAL = 5
SERVER_POLLING_INTERVAL = 3
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
if not ARG_TEST and check_device('/dev/video0'):
    GST_SOURCE = 'v4l2src ! videoconvert'
else:
    GST_SOURCE = 'videotestsrc ! clockoverlay'


class Connection(enum.Enum):
    DISCONNECTED = 'Disconnected'
    CONNECTED = 'Connected'
    UNKNOWN = '????'

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
        self.loop = asyncio.get_event_loop()

        self.results = Model([])
        self.notifications = Model(OrderedDict())
        self.image = Model(None)
        self.detail = Model(None)
        self.results = Model(None)
        self.result = Model(None)
        self.opacity = Model(None)
        self.connection = Model(Connection.DISCONNECTED)

        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')

        self.main_window = builder.get_object('main_window')
        self.container_overlay = builder.get_object('container_overlay')

        self.control_box = builder.get_object('control_box')
        self.notifications_grid = builder.get_object('notifications_grid')
        self.opacity_scale = builder.get_object('opacity_scale')
        self.opacity_adjustment = builder.get_object('opacity_adjustment')
        self.overlay_select_combo = builder.get_object('overlay_select_combo')
        self.overlay_select_store = builder.get_object('overlay_select_store')

        self.connection_label = builder.get_object('connection_label')
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

        self.ws = WS()
        self.fps = Fps()

        self.main_window.show_all()

        self.notifications.subscribe(self.handler_notifications, True)
        self.image.subscribe(self.handler_image, True)
        self.detail.subscribe(self.handler_detail, True)
        # self.results.subscribe(self.handler_results, True)
        self.result.subscribe(self.handler_result, True)
        self.opacity.subscribe(self.handler_opacity, True)
        self.connection.subscribe(self.handler_connection, True)
        self.__last_triggered_time = None

        provider = Gtk.CssProvider()
        provider.load_from_path('client/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)
        # self.main_window.maximize()

    def handler_notifications(self, notifications, old):
        row_count = get_grid_row_count(self.notifications_grid)
        notifications_count = len([v for v in notifications.values() if v])
        changed = False
        if row_count < notifications_count:
            changed = True
            for top in range(row_count, notifications_count):
                for left in [0, 1]:
                    label = Gtk.Label()
                    label.props.xalign = 0
                    self.notifications_grid.attach(label, left, top, 1, 1)
        if row_count > notifications_count:
            for r in reversed(range(notifications_count, row_count)):
                self.notifications_grid.remove_row(r)
        top = 0
        for key, value in notifications.items():
            if not value:
                continue
            changed = True
            key_label = self.notifications_grid.get_child_at(0, top)
            key_label.set_label(key + ':')
            value_label = self.notifications_grid.get_child_at(1, top)
            value_label.set_label(value)
            top += 1
        self.notifications_grid.show_all()
        if changed:
            pass
            # Gtk.main_iteration()

    def set_notification(self, pairs):
        n = self.notifications.get()
        for pair in pairs:
            n[pair[0]] = pair[1]
        self.notifications.set(n)

    def handler_connection(self, connection, old):
        # self.connection_label.set_text(connection.value)
        self.analyze_menu.set_sensitive(connection == Connection.CONNECTED)
        self.set_notification([['Connection', connection.value]])


    def handler_result(self, result, old):
        if result:
            title = f'Inspecting: {result.name} ({result.mode})'
        else:
            title = 'Scanning'
        self.main_window.set_title(title)

        self.analyze_menu.set_visible(not result)
        self.back_to_scan_menu.set_visible(result)
        self.opacity_scale.set_visible(result)
        self.overlay_select_combo.set_visible(result)
        self.gst_widget.set_visible(not result)
        self.canvas_image.set_visible(result)

        self.set_notification([
            ['Mode', result.mode if result else None],
            ['Result', result.name if result else None],
        ])

        if result:
            for row in self.overlay_select_store:
                if row[1] == -1:
                    continue
                self.overlay_select_store.remove(row.iter)
            for i, o in enumerate(result.overlays):
                self.overlay_select_store.append([o.name, i])

        while Gtk.events_pending():
          Gtk.main_iteration()

        if not result:
            self.detail.set(None)
            return
        self.detail.set(Detail(result))

    def handler_opacity(self, detail, old):
        pass

    @async_glib
    async def handler_detail(self, detail, old):
        self.image.set(None)
        if not detail:
            return
        await detail.download()
        self.image.set(detail.original_image)

    def handler_image(self, image, old):
        flag = not np.any(image)
        if flag:
            self.canvas_image.clear()
            return
        self.adjust_canvas_image()

    def on_main_window_size_allocate(self, *args):
        if self.result.get():
            self.adjust_canvas_image()

    def on_main_window_delete(self, *args):
        if self.ws.is_active():
            self.task.cancel()
        # Gtk.main_quit(*args)
        self.loop.stop()

    def on_main_window_click(self, widget, event):
        ###* GUARD START
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return
        if self.__last_triggered_time == event.time:
            return
        self.__last_triggered_time = event.time
        ###* GUARD END

        if event.button == 1:
            self.control_box.set_visible(not self.control_box.get_visible())
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
        def cb():
            self.refresh_image()
        debounce(100, cb)

    def on_overlay_select_combo_changed(self, widget, *args):
        self.refresh_image()

    @async_glib
    async def on_analyze_menu_activate(self, *args):
        snapshot = self.gst_widget.take_snapshot()
        data = await upload_image('camera', snapshot)
        self.results.set(convert_to_results(data['results']))

    def on_browser_menu_activate(self, *args):
        print('open browser')

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
        row = self.result_store[path]
        result = find_results(self.results.get(), row[1], row[0])
        self.result.set(result)
        self.menu_window.hide()

    def adjust_canvas_image(self):
        image = self.image.get()
        if not np.any(image):
            return
        win_w, win_h = self.main_window.get_size()
        img_h, img_w, _ = image.shape
        if win_w/win_h > img_w/img_h:
            new_w = img_w * win_h / img_h
            new_h = win_h
        else:
            new_w = win_w
            new_h = img_h * win_w / img_w
        image = cv2.resize(image, None, fx=new_w/img_w, fy=new_h/img_h, interpolation=cv2.INTER_CUBIC)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pb = GdkPixbuf.Pixbuf.new_from_data(
                image.tostring(),
                GdkPixbuf.Colorspace.RGB,
                False,
                8,
                image.shape[1],
                image.shape[0],
                image.shape[2] * image.shape[1])
        self.canvas_image.set_from_pixbuf(pb)

    def refresh_image(self):
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
        if not self.menu_window.get_visible():
            return True
        active_filter = self.result_filter_combo.get_active()
        if active_filter > 0:
            target_mode = self.result_filter_store[active_filter][1]
        else:
            target_mode = None

        scroll_value = self.result_container.get_vadjustment().get_value()
        selected_rows = self.result_tree.get_selection().get_selected_rows()[1]
        self.result_store.clear()
        for r in reversed(self.results.get()):
            if target_mode:
                if r.mode != target_mode:
                    continue
            self.result_store.append([r.name, r.mode, r.original.name])
        while Gtk.events_pending():
          Gtk.main_iteration()
        if len(selected_rows) > 0:
            self.result_tree.set_cursor(selected_rows[0].get_indices()[0])
        self.result_container.get_vadjustment().set_value(scroll_value)
        return True # repeat

    async def ws_proc(self, *args):
        await self.ws.connect()
        while self.loop.is_running():
            if not self.ws.is_active():
                print('Try re-connect')
                self.connection.set(Connection.DISCONNECTED)
                self.results.set([])
                await asyncio.sleep(RECONNECT_INTERVAL)
                await self.ws.connect()
                continue
            data = await self.ws.acquire_status()
            rr = convert_to_results(data['results'])
            self.results.set(rr)
            self.connection.set(Connection.CONNECTED)
            self.refresh_result_tree()
            await asyncio.sleep(SERVER_POLLING_INTERVAL)
        print('ws_proc terminated')


    def start(self):
        GLib.timeout_add(RESULT_TREE_UPDATE_INTERVAL, self.refresh_result_tree)
        self.task = self.loop.create_task(self.ws_proc())
        self.loop.run_forever()

app = App()
app.start()
