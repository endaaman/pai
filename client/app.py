import os
import io
import json
import time
import threading
from enum import Enum, auto
from collections import namedtuple

import numpy as np
import cv2
import requests
from PIL import Image
import websocket

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib, GdkPixbuf, Gst


API_HOST = 'localhost:8080'
WS_HOST = 'localhost:8081'
RECONNECT_DURATION = 7
STATUS_UPDATE_DURATION = 7
VIDEO = 0
FPS_SAMPLE_COUNT = 60
FPS = 30
TEST_VIDEO_SRC = 'videotestsrc ! clockoverlay'
CAMERA_VIDEO_SRC = 'v4l2src ! videoconvert'

def check_device(p):
    try:
        os.stat(p)
    except FileNotFoundError:
        return False
    return True

class ConnectionStatus(Enum):
    INIT = 'Initializing...'
    DISCONNECTED = 'Disconnected'
    CONNECTED = 'Connected'
    UNKNOWN = '????'

class WS:
    def __init__(self):
        super().__init__()
        self.ws = None

    def is_active(self):
        # return ws and ws.sock and ws.sock.connected
        return self.ws and self.ws.connected

    def close(self):
        # return ws and ws.sock and ws.sock.connected
        if not self.ws:
            return
        if self.ws.connected:
            self.ws.close()
        self.ws = None

    def connect(self):
        try:
            self.ws = websocket.create_connection(f'ws://{WS_HOST}/status')
        except Exception as e:
            print('Failed to connect', e)
            self.ws = None
            return
        print('Connected')

    def acquire_status(self, *args):
        try:
            self.ws.send('status')
            return self.ws.recv()
        except Exception as e:
            print('ERROR WHEN SENDING OR RECEIVING', e)
        return False

Result = namedtuple('Result', ['name', 'mode', 'original', 'overlays'])

class ServerState:
    def __init__(self):
        self.current = None
        self.queue = []
        self.results = []
        self.connection_status = ConnectionStatus.INIT

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

class Fps:
    def __init__(self):
        self.count = 0
        self.start_time = None
        self.value = 0
        self.calculated = False

    def get_time(self):
        return time.time() * 1000

    def get_value(self):
        return self.value

    def get_label(self):
        if not self.calculated:
            return 'n/a'
        return f'{self.value:.2f}'

    def update(self):
        if self.count == 0:
            self.start_time = self.get_time()
            self.count += 1
            return
        if self.count == FPS_SAMPLE_COUNT:
            elapsed = self.get_time() - self.start_time
            self.value = 1000 / ((elapsed / FPS_SAMPLE_COUNT))
            self.count = 0
            self.calculated = True
            return
        self.count += 1


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


class GstWidget(Gtk.Box):
    def __init__(self, src):
        super().__init__()
        self.connect('realize', self._on_realize)
        self.video_bin = Gst.parse_bin_from_description(src, True)
        self.test_bin = Gst.parse_bin_from_description(TEST_VIDEO_SRC, True)

        self.pipeline = Gst.Pipeline()
        factory = self.pipeline.get_factory()
        self.gtksink = factory.make('gtksink')

        self.pipeline.add(self.gtksink)
        self.pipeline.add(self.video_bin)
        self.video_bin.link(self.gtksink)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

    def _on_realize(self, widget):
        w = self.gtksink.get_property('widget')
        self.pack_start(w, True, True, 0)
        w.show()
        self.pipeline.set_state(Gst.State.PLAYING)

    def on_message(self, bus, message):
        if message.type == Gst.MessageType.EOS:
            self.pipeline.set_state(Gst.State.NULL)
            print('EOS')
            return
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print('Error: %s' % err, debug)
            self.pipeline.set_state(Gst.State.NULL)
            return

    def take_snapshot(self):
        sample = self.gtksink.get_property('last-sample')
        s = sample.get_caps().get_structure(0)
        width = s.get_int('width').value
        height = s.get_int('height').value
        buffer = sample.get_buffer()
        ret, map_info = buffer.map(Gst.MapFlags.READ)
        if not ret:
            print('ERROR')
            return
        arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(height, width, -1)
        return arr


class App:
    def __init__(self):
        Gst.init(None)
        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')

        self.main_window = builder.get_object('main_window')
        self.status_grid = builder.get_object('status_grid')
        self.status_connection_label = builder.get_object('status_connection_label')
        self.task_count_label = builder.get_object('task_count_label')
        self.overlay = builder.get_object('overlay')

        self.control_window = builder.get_object('control_window')
        self.notebook = builder.get_object('notebook')
        self.result_tree = builder.get_object('tree_result')
        self.result_store = builder.get_object('result_store')
        self.result_filter_combo = builder.get_object('result_filter_combo')
        self.result_filter_store = builder.get_object('result_filter_store')

        self.menu = builder.get_object('menu')
        self.analyze_menu = builder.get_object('analyze_menu')
        self.fullscreen_toggler_menu = builder.get_object('fullscreen_toggler_menu')

        if check_device('/dev/video0'):
            src = CAMERA_VIDEO_SRC
        else:
            src = TEST_VIDEO_SRC
        self.gst_widget = GstWidget(src)
        self.overlay.add_overlay(self.gst_widget)
        self.overlay.reorder_overlay(self.gst_widget, 0)

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
            self.status_grid.set_visible(not self.status_grid.get_visible())
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
        self.analyze_menu.set_sensitive(self.server_state.connection_status is ConnectionStatus.CONNECTED)
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
