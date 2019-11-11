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

ws = None
cap = cv2.VideoCapture(VIDEO)
current_frame = None
def update_current_frame(f):
    global current_frame
    current_frame = f

current_frame = None
def update_current_frame(f):
    global current_frame
    current_frame = f

class Connection(Enum):
    INIT = 'Initializing...'
    RETRY = 'Retry to connect server...'
    FAILED = 'Failed to connect server'
    CONNECTED = 'Connected'
    UPLOADING = 'Uploading...'
    PROCESSING = 'Processing...'
    UNKNOWN = '????'

conn = Connection.INIT
def update_conn(c):
    global conn
    conn = c


builder = Gtk.Builder()
builder.add_from_file('client/app.glade')
window = builder.get_object('window')
label_status = builder.get_object('labelStatus')
button_analyze = builder.get_object('buttonAnalyze')
box = builder.get_object('box')
image = builder.get_object('image')

def is_ws_active():
    # return ws and ws.sock and ws.sock.connected
    return ws and ws.connected

def dispose_ws_connection():
    # return ws and ws.sock and ws.sock.connected
    if not ws:
        return
    if ws.connected:
        ws.close()
        return

def create_ws_connection():
    global ws
    try:
        ws = websocket.create_connection(f'ws://{WS_HOST}/api/status')
        return True
    except Exception as e:
        print('Failed to connect', e)
    return False

class Handler:
    def onDeleteWindow(self, *args):
        if ws and not ws.connected:
            ws.close()
        Gtk.main_quit(*args)

    def buttonQuitClicked(self, *args):
        window.close()

    def buttonAnalyzeClicked(self, *args):
        if current_frame is None:
            print('buffer is not loaded')
            return
        # result, data = cv2.imencode('.jpg', current_frame)
        # if not result:
        #     print('could not encode image')
        #     return
        buf = io.BytesIO()
        plt.imsave(buf, current_frame, format='jpg')
        data = buf.getvalue()
        res = requests.post(
                f'http://{API_HOST}/upload',
                files={'image': ('image.jpg', data, 'image/jpeg', {'Expires': '0'})})
        print(res)
        # update_conn(Connection.UPLOADING)
        # print(type(binary.tobytes()))

    def buttonCheckClicked(self, *args):
        response = requests.get(f'http://{API_HOST}/images')
        print(response.status_code)

# window.fullscreen()
window.resize(800, 450)
window.show_all()
builder.connect_signals(Handler())


def update_ws_connection(*args):
    create_ws_connection()
    while window.get_visible():
        # ws.run_forever()
        if not is_ws_active():
            print('Try re-connect')
            r = create_ws_connection()
            update_conn(Connection.FAILED)
            time.sleep(1)
            update_conn(Connection.RETRY)
            time.sleep(3)
            if not r:
                continue
        try:
            ws.send('status')
            time.sleep(1)
            data = ws.recv()
        except Exception as e:
            print('ERROR WHEN SENDING', e)
            dispose_ws_connection()
            continue
        # print(f'RECEIVE: {data}')
        try:
            server_status = json.loads(data)
            if server_status['current']:
                update_conn(Connection.PROCESSING)
            else:
                if not status is Connection.UPLOADING:
                    update_conn(Connection.CONNECTED)
        except json.JSONDecodeError as e:
            print(f'PARSE ERROR: {data}')
            update_conn(Connection.UNKNOWN)


def show_frame(*args):
    if True:
    ret, frame = cap.read()
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    update_current_frame(frame)
    win_w, win_h = window.get_size()
    img_h, img_w, _ = frame.shape
    frame = cv2.resize(frame, None, fx=win_w/img_w, fy=win_h/img_h, interpolation=cv2.INTER_CUBIC)
    pb = GdkPixbuf.Pixbuf.new_from_data(
            frame.tostring(),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            frame.shape[1],
            frame.shape[0],
            frame.shape[2]*frame.shape[1])
    image.set_from_pixbuf(pb)
    label_status.set_text(conn.value)
    button_analyze.set_sensitive(conn is Connection.CONNECTED)
    return True


# websocket.enableTrace(True)
thread = threading.Thread(target=update_ws_connection)
thread.daemon = True
thread.start()

GLib.idle_add(show_frame)
Gtk.main()

