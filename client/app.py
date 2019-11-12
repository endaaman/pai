import os
import io
import json
import time
import threading
from enum import Enum, auto

import numpy as np
import cv2
import requests
from PIL import Image
import websocket
import matplotlib.pyplot as plt

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf


API_HOST = 'localhost:8080'
WS_HOST = 'localhost:8081'
RECONNECT_DURATION = 3
VIDEO = 0


class ConnectionStatus(Enum):
    INIT = 'Initializing...'
    DISCONNECTED = 'Disconnected to server'
    RETRYING = 'Retry to connect server...'
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
        print('Connected')

    def acquire_status(self, *args):
        try:
            self.ws.send('status')
            time.sleep(1)
            return self.ws.recv()
        except Exception as e:
            print('ERROR WHEN SENDING OR RECEIVING', e)
            return False
        return True
        # print(f'RECEIVE: {data}')

class ServerState:
    def __init__(self):
        self.items = []
        self.current = None

    def load_dict(self, d):
        self.items = d['items']
        self.current = d['current']


class App:
    def __init__(self):
        builder = Gtk.Builder()
        builder.add_from_file('client/app.glade')
        self.window = builder.get_object('window')
        self.label_status = builder.get_object('labelStatus')
        self.button_analyze = builder.get_object('buttonAnalyze')
        self.box = builder.get_object('box')
        self.image = builder.get_object('image')

        self.capture = cv2.VideoCapture(VIDEO)
        self.ws = WS()

        self.status = ConnectionStatus.INIT
        self.server_state = ServerState()
        self.frame = None

        # window.fullscreen()
        self.window.resize(800, 450)
        self.window.show_all()
        builder.connect_signals(self)

    def set_frame(self, frame):
        self.frame = frame

    def set_status(self, c):
        self.status = c

    def onDeleteWindow(self, *args):
        if self.ws.is_active():
            self.ws.close()
        Gtk.main_quit(*args)

    def buttonQuitClicked(self, *args):
        self.window.close()

    def buttonAnalyzeClicked(self, *args):
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
                f'http://{API_HOST}/api/upload',
                files={'image': ('image.jpg', data, 'image/jpeg', {'Expires': '0'})})
        print(res)
        # self.set_status(ConnectionStatus.UPLOADING)
        # print(type(binary.tobytes()))

    def buttonCheckClicked(self, *args):
        response = requests.get(f'http://{API_HOST}/api/images')
        print(response.status_code)

    def thread_proc(self, *args):
        self.ws.connect()
        while self.window.get_visible():
            # ws.run_forever()
            if not self.ws.is_active():
                print('Try re-connect')
                self.ws.connect()
                self.set_status(ConnectionStatus.DISCONNECTED)
                time.sleep(1)
                self.set_status(ConnectionStatus.RETRYING)
                time.sleep(3)
                continue

            text = self.ws.acquire_status()
            if not text:
                self.ws.close()
                continue

            try:
                self.server_state.load_dict(json.loads(text))
                self.set_status(ConnectionStatus.CONNECTED)
            except json.JSONDecodeError as e:
                print(f'PARSE ERROR: {data}')
                self.ws.close()

    def render(self, frame):
        win_w, win_h = self.window.get_size()
        img_h, img_w, _ = frame.shape
        resized = cv2.resize(frame, None, fx=win_w/img_w, fy=win_h/img_h, interpolation=cv2.INTER_CUBIC)
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
        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self.set_frame(frame)

        self.render(frame)

        self.label_status.set_text(self.status.value)
        self.button_analyze.set_sensitive(self.status is ConnectionStatus.CONNECTED)
        return True


app = App()

# websocket.enableTrace(True)
thread = threading.Thread(target=app.thread_proc)
thread.daemon = True
thread.start()

GLib.idle_add(app.frame_proc)
Gtk.main()

