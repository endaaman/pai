import cv2
import numpy as np
import requests
from PIL import Image
import websocket
import time
import json
import threading
from enum import Enum, auto

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

HOST = 'localhost:8080'
RECONNECT_DURATION = 3
VIDEO = 0

ws = None
cap = cv2.VideoCapture(VIDEO)
current_frame = None

class Status(Enum):
    INIT = 'Initializing...'
    RETRY = 'Retry to connect server...'
    FAILED = 'Failed to connect server'
    CONNECTED = 'Connected'
    UPLOADING = 'Uploading...'
    PROCESSING = 'Processing...'
    UNKNOWN = '????'

status = Status.INIT
def update_status(s):
    global status
    status = s


builder = Gtk.Builder()
builder.add_from_file('app.glade')
window = builder.get_object('window')
label_status = builder.get_object('labelStatus')
button_analyze = builder.get_object('buttonAnalyze')
box = builder.get_object('box')
image = builder.get_object('image')

def on_ws_message(ws, message):
    global server_status
    server_status = json.loads(message)

def on_ws_error(ws, error):
    print(error)

def on_ws_close(ws):
    pass

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
        ws = websocket.create_connection(f'ws://{HOST}/api/status')
        # ws = websocket.WebSocketApp(
        #         f'ws://{HOST}/api/status',
        #         on_message=on_ws_message,
        #         on_error=on_ws_error,
        #         on_close=on_ws_close)
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
        result, binary = cv2.imencode('.jpg', current_frame)
        if not result:
            print('could not encode image')
            return
        update_status(Status.UPLOADING)
        # print(type(binary.tobytes()))
        ws.send_binary(binary.tobytes())
        # files = {'uploadFile': ('img.jpg', binary, 'image/jpeg')}
        # response = requests.post(f'http://{HOST}/api/upload', files=files)
        # print(response.status_code)

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
            update_status(Status.FAILED)
            time.sleep(1)
            update_status(Status.RETRY)
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
        print(f'RECEIVE: {data}')
        try:
            server_status = json.loads(data)
            if server_status['current']:
                update_status(Status.PROCESSING)
            else:
                if status != Status.UPLOADING:
                    update_status(Status.CONNECTED)
        except json.JSONDecodeError as e:
            print(f'PARSE ERROR: {data}')
            update_status(Status.UNKNOWN)


def show_frame(*args):
    global current_frame
    ret, frame = cap.read()

    current_frame = frame.copy()
    win_w, win_h = window.get_size()
    img_h, img_w, _ = frame.shape
    frame = cv2.resize(frame, None, fx=win_w/img_w, fy=win_h/img_h, interpolation=cv2.INTER_CUBIC)
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pb = GdkPixbuf.Pixbuf.new_from_data(
            frame.tostring(),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            frame.shape[1],
            frame.shape[0],
            frame.shape[2]*frame.shape[1])
    image.set_from_pixbuf(pb)
    label_status.set_text(status.value)
    button_analyze.set_sensitive(status is Status.CONNECTED)
    return True


# websocket.enableTrace(True)
thread = threading.Thread(target=update_ws_connection)
thread.daemon = True
thread.start()

GLib.idle_add(show_frame)
Gtk.main()

