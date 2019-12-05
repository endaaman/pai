import os
import io
import json
import time
import threading
import argparse
from enum import Enum, auto
from collections import namedtuple

import numpy as np
import cv2
import requests

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib, GdkPixbuf, Gst

from utils import Fps, check_device
from ws import WS
from ui import GstWidget

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action="store_true")
args = parser.parse_args()

ARG_TEST = args.test

API_HOST = 'localhost:8080'
RECONNECT_DURATION = 7
STATUS_UPDATE_DURATION = 7
TEST_VIDEO_SRC = 'videotestsrc ! clockoverlay'
CAMERA_VIDEO_SRC = 'v4l2src ! videoconvert'


Result = namedtuple('Result', ['name', 'mode', 'original', 'overlays'])

class ConnectionStatus(Enum):
    INIT = 'Initializing...'
    DISCONNECTED = 'Disconnected'
    CONNECTED = 'Connected'
    UNKNOWN = '????'

class ServerState:
    def __init__(self):
        self.current = None
        self.queue = []
        self.results = []
        self.connection_status = ConnectionStatus.INIT

    def is_connected(self):
        return self.connection_status is ConnectionStatus.CONNECTED

    def mark_connected(self):
        self.connection_status = ConnectionStatus.CONNECTED

    def overwrite_data(self, d):
        self.current = d['current']
        self.queue = d['queue']
        self.results = [Result(**r) for r in d['results']]

    def reset(self):
        self.current = None
        self.queue = []
        self.results = []
        self.connection_status = ConnectionStatus.DISCONNECTED

    def find_result(self, mode, name):
        for r in self.results:
            if mode == r.mode and name == r.name:
                return r
        return None

    def get_connection_message(self):
        if not self.connection_status is ConnectionStatus.CONNECTED:
            return self.connection_status.value
        count = len(self.queue)
        if count == 0:
            return 'Connected'
        if count == 1:
            return f'Processing...'
        t = f'1 task is queued' if count == 2 else f'{count - 1} tasks are queued'
        return f'Processing...({t})'

    def get_task_count_message(self):
        if not self.connection_status is ConnectionStatus.CONNECTED:
            return 'n/a'
        return str(len(self.queue))



class Model():
    def __init__(self):
        self.value = None
        self.hooks = []
        self.getter = None

    def subscribe(self, func):
        self.hooks.append(func)

    def override_getter(self, getter):
        self.getter = getter

    def set(self, v):
        old_value = self.value
        self.value = v
        for hook in self.hooks:
            hook(v, old_value)

    def get(self):
        if self.getter:
            return self.getter()
        return self.value




class App:
    def __init__(self):
        Gst.init(None)
        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')

        self.main_window = builder.get_object('main_window')
        self.status_connection_label = builder.get_object('status_connection_label')
        self.task_count_label = builder.get_object('task_count_label')
        self.container_overlay = builder.get_object('container_overlay')
        self.status_box = builder.get_object('status_box')

        self.control_window = builder.get_object('control_window')
        self.notebook = builder.get_object('notebook')
        self.result_tree = builder.get_object('tree_result')
        self.result_store = builder.get_object('result_store')
        self.result_filter_combo = builder.get_object('result_filter_combo')
        self.result_filter_store = builder.get_object('result_filter_store')

        self.menu = builder.get_object('menu')
        self.analyze_menu = builder.get_object('analyze_menu')
        self.fullscreen_toggler_menu = builder.get_object('fullscreen_toggler_menu')

        if not ARG_TEST and check_device('/dev/video0'):
            src = CAMERA_VIDEO_SRC
        else:
            src = TEST_VIDEO_SRC
        self.gst_widget = GstWidget(src)
        self.container_overlay.add_overlay(self.gst_widget)
        self.container_overlay.reorder_overlay(self.gst_widget, 0)

        builder.connect_signals(self)

        self.ws = WS()
        self.fps = Fps()
        self.server_state = ServerState()
        self.frame = None
        self.__last_triggered_time = None

        provider = Gtk.CssProvider()
        provider.load_from_path('client/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)

        # self.main_window.maximize()

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
            self.menu_fullscreen_toggler.set_active(flag)

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
        # self.set_status(ConnectionStatus.UPLOADING)
        # print(type(binary.tobytes()))

    def on_menu_menu_activate(self, *args):
        self.refresh_result_tree()
        self.control_window.show_all()

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
        print(result)


    def refresh_result_tree(self):
        active_filter = self.result_filter_combo.get_active()
        if active_filter > 0:
            target_mode = self.result_filter_store[active_filter][0]
        else:
            target_mode = None
        self.result_store.clear()
        for r in self.server_state.results:
            if target_mode:
                if r.mode != target_mode:
                    continue
            self.result_store.append([r.name, r.mode, r.original])

        return False # do not repeat

    def thread_proc(self, *args):
        self.ws.connect()
        while self.main_window.get_visible():
            # ws.run_forever()
            if not self.ws.is_active():
                print('Try re-connect')
                self.server_state.reset()
                time.sleep(RECONNECT_DURATION)
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
            self.server_state.mark_connected()
            self.server_state.overwrite_data(data)
            if self.control_window.get_visible():
                GLib.idle_add(self.refresh_result_tree)
            time.sleep(STATUS_UPDATE_DURATION)

    def frame_proc(self, *args):
        self.status_connection_label.set_text(self.server_state.get_connection_message())
        self.task_count_label.set_text(self.fps.get_label())
        self.analyze_menu.set_sensitive(self.server_state.is_connected())
        return True

    def start(self):
        thread = threading.Thread(target=self.thread_proc)
        thread.daemon = True
        thread.start()

        # self.player.set_state(Gst.State.PLAYING)
        GLib.idle_add(self.frame_proc)
        self.main_window.show_all()
        Gtk.main()


app = App()
app.start()
