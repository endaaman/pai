import os
import io
import json
import time
import argparse
import threading
import enum
from collections import namedtuple, OrderedDict
import asyncio

import numpy as np
import cv2
import requests

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gst

from utils import Fps, Model, check_device, download_image, async_signal
from ws import WS
from ui import GstWidget

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action="store_true")
args = parser.parse_args()

ARG_TEST = args.test

API_HOST = 'localhost:8080'
RECONNECT_INTERVAL = 7
SERVER_POLLING_INTERVAL = 7
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
if not ARG_TEST and check_device('/dev/video0'):
    GST_SOURCE = 'v4l2src ! videoconvert'
else:
    GST_SOURCE = 'videotestsrc ! clockoverlay'

Result = namedtuple('Result', ['name', 'mode', 'original', 'overlays'])


class Detail:
    def __init__(self, result):
        self.result = result
        self.original_image = None
        self.overlay_images = []

    def to_url(self, rel):
        return f'http://{API_HOST}/{rel}'

    def download(self):
        self.original_image = download_image(self.to_url(self.result.original))
        for o in self.result.overlays:
            self.overlay_images.append(download_image(self.to_url(o)))

class Connection(enum.Enum):
    INITIALIZING = 'Initializing'
    DISCONNECTED = 'Disconnected'
    CONNECTED = 'Connected'
    UNKNOWN = '????'


def find_results(results, mode, name):
    for r in results:
        if mode == r.mode and name == r.name:
            return r
    return None

def get_grid_row_count(grid):
    count = 0
    for child in grid.get_children():
        top = grid.child_get_property(child, 'top-attach')
        height = grid.child_get_property(child, 'width')
        count = max(count, top + height)
    return count


async def wait(s):
    print(f'start wait {s}')
    await sleep(s)
    print(f'end wait {s}')

class App:
    def __init__(self):
        Gst.init(None)
        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')

        self.main_window = builder.get_object('main_window')
        self.container_overlay = builder.get_object('container_overlay')
        self.notifications_grid = builder.get_object('notifications_grid')

        self.connection_label = builder.get_object('connection_label')
        self.gst_widget = GstWidget(GST_SOURCE)
        self.result_image = builder.get_object('result_image')

        self.control_window = builder.get_object('control_window')
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

        self.results = Model([])
        self.notifications = Model(OrderedDict(), self.handler_notifications)
        self.detail = Model(None, self.handler_detail)
        self.result = Model(None, self.handler_result)
        self.connection = Model(Connection.INITIALIZING, self.handler_connection)
        self.__last_triggered_time = None

        provider = Gtk.CssProvider()
        provider.load_from_path('client/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)
        # self.main_window.maximize()

    def handler_notifications(self, notifications, old):
        row_count = get_grid_row_count(self.notifications_grid)
        notifications_count = len([v for v in notifications.values() if v])
        if row_count < notifications_count:
            for top in range(row_count, notifications_count):
                for left in [0, 1]:
                    label = Gtk.Label()
                    label.props.xalign = 0
                    self.notifications_grid.attach(label, left, top, 1, 1)
        if row_count > notifications_count:
            for r in range(notifications_count, row_count):
                self.notifications_grid.remove_row(r)
        top = 0
        for key, value in notifications.items():
            if not value:
                continue
            key_label = self.notifications_grid.get_child_at(0, top)
            key_label.set_label(key + ':')
            value_label = self.notifications_grid.get_child_at(1, top)
            value_label.set_label(value)
            top += 1
        self.notifications_grid.show_all()

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
        inspecting = result
        scanning = not result
        if scanning:
            title = 'Scanning'
        else:
            title = f'Inspecting: {result.name} ({result.mode})'
        self.main_window.set_title(title)

        self.analyze_menu.set_visible(scanning)
        self.back_to_scan_menu.set_visible(inspecting)
        # self.inspect_menu.set_visible(inspecting)

        self.gst_widget.set_visible(scanning)
        self.result_image.set_visible(inspecting)

        self.set_notification([
            ['Mode', result.mode if inspecting else None],
            ['Result', result.name if inspecting else None],
        ])

        if not result:
            self.detail.set(None)
            return
        self.detail.set(Detail(result))

    def handler_detail(self, detail, old):
        if not detail:
            return
        detail.download()
        print(detail.original_image.shape)
        if len(detail.overlay_images) > 0:
            print(detail.overlays[0].shape)

    def on_main_window_delete(self, *args):
        if self.ws.is_active():
            self.ws.close()
        Gtk.main_quit(*args)

    def on_main_window_click(self, widget, event):
        ###* GUARD START
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return
        if self.__last_triggered_time == event.time:
            return
        self.__last_triggered_time = event.time
        ###* GUARD END

        if event.button == 1:
            self.notifications_grid.set_visible(not self.notifications_grid.get_visible())
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

    def on_analyze_menu_activate(self, *args):
        snapshot = self.gst_widget.take_snapshot()
        if not np.any(snapshot):
            print('Failed to take snapshot')
            return
        is_success, raw = cv2.imencode('.jpg', snapshot)
        if not is_success:
            print('ERROR')
            return
        buffer = io.BytesIO(raw)
        res = requests.post(
            f'http://{API_HOST}/api/analyze',
            {'mode': 'camera'},
            files={'image': ('image.jpg', buffer.getvalue(), 'image/jpeg', {'Expires': '0'})})
        self.results.set(Result(**r) for r in [res.json()['results']])

    @async_signal
    async def on_browser_menu_activate(self, *args):

        self.main_window.set_title('done')

    def on_back_to_scan_menu_activate(self, *args):
        self.result.set(None)

    def on_menu_menu_activate(self, *args):
        self.control_window.show_all()
        self.refresh_result_tree()

    def on_fullscreen_toggler_menu_toggled(self, widget, *args):
        if widget.get_active():
            self.main_window.maximize()
        else:
            self.main_window.unmaximize()

    def on_quit_menu_activate(self, *args):
        self.main_window.close()

    def on_contorol_window_key_release(self, widget, event, *args):
       if event.keyval == Gdk.KEY_Escape:
            self.control_window.close()

    def on_contorol_window_delete(self, *args):
        self.control_window.hide()
        return True

    def on_result_filter_combo_changed(self, widget, *args):
        self.refresh_result_tree()

    def on_result_tree_row_activated(self, widget, path, column):
        row = self.result_store[path]
        result = find_results(self.results.get(), row[1], row[0])
        self.result.set(result)
        self.control_window.hide()

    def refresh_result_tree(self):
        if not self.control_window.get_visible():
            return True
        active_filter = self.result_filter_combo.get_active()
        if active_filter > 0:
            target_mode = self.result_filter_store[active_filter][0]
        else:
            target_mode = None

        scroll_value = self.result_container.get_vadjustment().get_value()
        selected_rows = self.result_tree.get_selection().get_selected_rows()[1]
        self.result_store.clear()
        for r in reversed(self.results.get()):
            if target_mode:
                if r.mode != target_mode:
                    continue
            self.result_store.append([r.name, r.mode, r.original])
        def adjust():
            if len(selected_rows) > 0:
                self.result_tree.set_cursor(selected_rows[0].get_indices()[0])
            self.result_container.get_vadjustment().set_value(scroll_value)
        GLib.idle_add(adjust)
        return True # repeat

    def download_result(self):
        return

    def thread_proc(self, *args):
        self.ws.connect()
        while self.main_window.get_visible():
            if not self.ws.is_active():
                print('Try re-connect')
                self.connection.set(Connection.DISCONNECTED)
                self.results.set([])
                time.sleep(RECONNECT_INTERVAL)
                self.ws.connect()
                continue
            text = self.ws.acquire_status()
            if not text:
                self.ws.close()
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                print(f'PARSE ERROR: {data}')
                self.ws.close()
                continue
            self.results.set([Result(**r) for r in data['results']])
            self.connection.set(Connection.CONNECTED)
            time.sleep(SERVER_POLLING_INTERVAL)

    def start(self):
        thread = threading.Thread(target=self.thread_proc)
        thread.daemon = True
        thread.start()
        self.main_window.show_all()
        GLib.timeout_add(RESULT_TREE_UPDATE_INTERVAL, self.refresh_result_tree)
        Gtk.main()

app = App()
app.start()
