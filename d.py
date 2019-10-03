import cv2
import numpy as np
import requests
from PIL import Image
from websocket import create_connection
import time
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

HOST = 'localhost:8080'
RECONNECT_DURATION = 3
VIDEO = 0

ws = None
cap = cv2.VideoCapture(VIDEO)
current_frame = None


builder = Gtk.Builder()
builder.add_from_file('d.glade')
window = builder.get_object('window1')
image = builder.get_object('image')

def create_ws_connection():
    global ws
    try:
        ws = create_connection(f'ws://{HOST}/api/status')
        return True
    except Exception as e:
        print('Failed to connect', e)
    return False

class Handler:
    def onDeleteWindow(self, *args):
        Gtk.main_quit(*args)

    def button1Clicked(self, *args):
        if ws:
            ws.close()
        window.close()

    def button2Clicked(self, *args):
        if current_frame is None:
            print('buffer is not loaded')
            return

        result, binary = cv2.imencode('.jpg', current_frame)
        if not result:
            print('could not encode image')
            return
        files = {'uploadFile': ('img.jpg', binary, 'image/jpeg')}
        url = f'http://{HOST}/api/upload'
        response = requests.post(url, files=files)
        print(response.status_code)

# window.fullscreen()
window.resize(800, 450)
window.show_all()
builder.connect_signals(Handler())


def update_server_status(*args):
    while True:
        if not ws or not ws.connected:
            time.sleep(RECONNECT_DURATION)
            print('Try re-connect')
            r = create_ws_connection()
            if not r:
                print(f'Wait for {RECONNECT_DURATION}s')
                continue
        result = ws.recv()
        print(f'Received: {result}')
        time.sleep(1)

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
    image.set_from_pixbuf(pb.copy())
    return True

create_ws_connection()
thread = threading.Thread(target=update_server_status)
thread.daemon = True
thread.start()

GLib.idle_add(show_frame)
Gtk.main()

