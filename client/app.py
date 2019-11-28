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
import matplotlib.pyplot as plt
import xmlplain

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

VIDO_SRC = 'v4l2src'


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



class GstWidget(Gtk.Box):
    def __init__(self, src='videotestsrc'):
        super().__init__()
        self.connect('realize', self._on_realize)
        self._bin = Gst.parse_bin_from_description(src, True)

    def _on_realize(self, widget):
        pipeline = Gst.Pipeline()
        factory = pipeline.get_factory()
        gtksink = factory.make('gtksink')
        pipeline.add(gtksink)
        pipeline.add(self._bin)
        self._bin.link(gtksink)
        self.pack_start(gtksink.props.widget, True, True, 0)
        gtksink.props.widget.show()
        pipeline.set_state(Gst.State.PLAYING)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('message', self.on_message)
        bus.connect('sync-message::element', self.on_sync_message)

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.player.set_state(Gst.State.NULL)
            print('EOS')
            return
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print('Error: %s' % err, debug)
            self.player.set_state(Gst.State.NULL)

    def on_sync_message(self, bus, message):
        s = message.get_structure()
        if s is None:
            print('structure is None')
            return
        print('structure name: ', s.get_name())
        message_name = s.get_name()
        if message_name == 'prepare-window-handle':
            imagesink = message.src
            imagesink.set_property('force-aspect-ratio', True)
            # imagesink.set_xwindow_id(self.drawing_area.xid)



class App:
    def __init__(self):
        Gst.init(None)
        builder = Gtk.Builder()
        # with open('client/app.glade.yml') as inf:
        #     obj = xmlplain.obj_from_yaml(inf)
        # with open('client/app.glade', 'w') as outf:
        #     xmlplain.xml_from_obj(obj, outf)
        builder.add_from_file('client/app.glade')

        self.window_main = builder.get_object('window_main')
        self.grid_status = builder.get_object('grid_status')
        self.label_status_connection = builder.get_object('label_status_connection')
        self.label_status_task_count = builder.get_object('label_status_task_count')
        self.overlay = builder.get_object('overlay')
        self.image = builder.get_object('image')

        self.window_control = builder.get_object('window_control')
        self.notebook = builder.get_object('notebook')
        self.result_tree = builder.get_object('result_tree')
        self.result_store = builder.get_object('result_store')

        self.menu = builder.get_object('menu')
        self.menu_item_analyze = builder.get_object('menu_item_analyze')

        self.gst =  GstWidget('v4l2src ! autovideosink')
        # self.gst.set_size_request(200, 200)
        self.overlay.add_overlay(self.gst)
        self.overlay.reorder_overlay(self.gst, 0)

        self.capture = cv2.VideoCapture(VIDEO)
        # self.player = Gst.parse_launch('v4l2src ! autovideosink')

        self.ws = WS()
        self.fps = Fps()
        self.server_state = ServerState()
        self.frame = None
        self.__last_triggered_time = None

        # window.fullscreen()
        builder.connect_signals(self)

        provider = Gtk.CssProvider()
        provider.load_from_path('client/app.css')
        screen = Gdk.Display.get_default_screen(Gdk.Display.get_default())
        Gtk.StyleContext.add_provider_for_screen(screen, provider, 600)


    def set_frame(self, frame):
        self.frame = frame

    def toggle_grid_status(self):
        self.grid_status.set_visible(not self.grid_status.get_visible())

    def on_window_main_delete(self, *args):
        if self.ws.is_active():
            self.ws.close()
        Gtk.main_quit(*args)

    def on_window_main_click(self, widget, event):
        ###* GUARD START
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return
        if self.__last_triggered_time == event.time:
            return
        self.__last_triggered_time = event.time
        ###* GUARD END

        if event.button == 1:
            self.toggle_grid_status()
            return

        if event.button == 3:
            self.menu.popup(None, None, None, None, event.button, event.time)
            return


    def on_menu_item_analyze_activate(self, *args):
        if self.frame is None:
            print('buffer is not loaded')
            return
        # result, data = cv2.imencode('.jpg', current_frame)
        # if not result:
        #     print('could not encode image')
        #     return
        buf = io.BytesIO()
        plt.imsave(buf, self.frame, format='jpg')
        data = buf.getvalue()
        res = requests.post(
            f'http://{API_HOST}/api/analyze',
            {'mode': 'camera'},
            files={'image': ('image.jpg', data, 'image/jpeg', {'Expires': '0'})})
        print(res)
        self.server_state.overwrite_data(res.json())
        # self.set_status(ConnectionStatus.UPLOADING)
        # print(type(binary.tobytes()))

    def on_menu_item_menu_activate(self, *args):
        self.window_control.show_all()

    # def on_menu_item_status_toggler_activate(self, widget, *args):
    #     self.toggle_grid_status()

    def on_menu_item_quit_activate(self, *args):
        self.window_main.close()

    def on_window_contorol_key_release(self, widget, event, *args):
       if event.keyval == Gdk.KEY_Escape:
            self.window_control.close()

    def on_window_contorol_delete(self, *args):
        self.window_control.hide()
        return True

    def apply_server_data(self):
        self.result_store.clear()
        for r in self.server_state.results:
            self.result_store.append([r.name, r.mode, r.original])
        return False # do not repeat

    def thread_proc(self, *args):
        self.ws.connect()
        while self.window_main.get_visible():
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
            GLib.idle_add(self.apply_server_data)
            time.sleep(STATUS_UPDATE_DURATION)

    def render(self):
        if not np.any(self.frame):
            return
        win_w, win_h = self.window_main.get_size()
        img_h, img_w, _ = self.frame.shape
        resized = cv2.resize(self.frame, None, fx=win_w/img_w, fy=win_h/img_h, interpolation=cv2.INTER_CUBIC)
        pb = GdkPixbuf.Pixbuf.new_from_data(
                resized.tostring(),
                GdkPixbuf.Colorspace.RGB,
                False,
                8,
                resized.shape[1],
                resized.shape[0],
                resized.shape[2] * resized.shape[1])
        self.image.set_from_pixbuf(pb)

    def frame_proc(self, *args):
        ret, bgr = self.capture.read()
        if ret:
            self.set_frame(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        else:
            d = 1.0 / FPS
            time.sleep(d)
            if not np.any(self.frame):
                f = cv2.imread('assets/images/shako.jpg')
                self.set_frame(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        # self.render()
        self.fps.update()

        self.label_status_connection.set_text(self.server_state.get_connection_message())
        self.label_status_task_count.set_text(self.fps.get_label())
        self.menu_item_analyze.set_sensitive(self.server_state.connection_status is ConnectionStatus.CONNECTED)

        return True


    def start(self):
        # websocket.enableTrace(True)
        thread = threading.Thread(target=self.thread_proc)
        thread.daemon = True
        thread.start()

        # self.player.set_state(Gst.State.PLAYING)
        GLib.idle_add(self.frame_proc)
        self.window_main.show_all()
        Gtk.main()


app = App()
app.start()
