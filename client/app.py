import os
import io
import json
import time
import threading
import argparse
import enum
from collections import namedtuple

import numpy as np
import cv2
import requests

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gst

from utils import Fps, Model, check_device
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

class Connection(enum.Enum):
    INITIALIZING = 'Initializing'
    DISCONNECTED = 'Disconnected'
    CONNECTED = 'Connected'
    UNKNOWN = '????'


class ServerState:
    def __init__(self):
        self.current = None
        self.queue = []
        self.results = []

    def overwrite_data(self, d):
        self.current = d['current']
        self.queue = d['queue']
        self.results = [Result(**r) for r in d['results']]

    def reset(self):
        self.current = None
        self.queue = []
        self.results = []

    def find_result(self, mode, name):
        for r in self.results:
            if mode == r.mode and name == r.name:
                return r
        return None

    def get_task_count_message(self):
        if not self.connection_status is ConnectionStatus.CONNECTED:
            return 'n/a'
        return str(len(self.queue))


class App:
    def __init__(self):
        Gst.init(None)
        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')

        self.main_window = builder.get_object('main_window')
        self.container_overlay = builder.get_object('container_overlay')
        self.status_box = builder.get_object('status_box')
        self.connection_label = builder.get_object('connection_label')
        self.task_count_label = builder.get_object('task_count_label')
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
        self.server_state = ServerState()
        self.frame = None
        self.current_result = Model(None, [self.handler_current_result])
        self.connection = Model(Connection.INITIALIZING, [self.handler_connection])
        self.__last_triggered_time = None

        provider = Gtk.CssProvider()
        provider.load_from_path('client/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)

        # self.main_window.maximize()

    def handler_connection(self, connection, old):
        self.connection_label.set_text(connection.value)
        self.analyze_menu.set_sensitive(connection == Connection.CONNECTED)

    def handler_current_result(self, result, old):
        # Show gst
        resulting = result
        scanning = not result
        if scanning:
            title = 'Scanning'
        else:
            title = f'Result: {result.name} ({result.mode})'
        self.main_window.set_title(title)
        self.analyze_menu.set_visible(scanning)
        self.back_to_scan_menu.set_visible(resulting)
        self.gst_widget.set_visible(scanning)
        self.result_image.set_visible(resulting)

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
            self.status_box.set_visible(not self.status_box.get_visible())
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
        print(res)
        self.server_state.overwrite_data(res.json())

    def on_back_to_scan_menu_activate(self, *args):
        self.current_result.set(None)

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
        result = self.server_state.find_result(row[1], row[0])
        self.current_result.set(result)
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
        for r in reversed(self.server_state.results):
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

    def thread_proc(self, *args):
        self.ws.connect()
        while self.main_window.get_visible():
            if not self.ws.is_active():
                print('Try re-connect')
                self.connection.set(Connection.DISCONNECTED)
                self.server_state.reset()
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
            self.server_state.overwrite_data(data)
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
