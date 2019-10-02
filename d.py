import cv2
import numpy as np
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

cap = cv2.VideoCapture(0)

builder = Gtk.Builder()
builder.add_from_file("d.glade")
window = builder.get_object("window1")
image = builder.get_object("image")

current_frame = None

class Handler:
    def onDeleteWindow(self, *args):
        Gtk.main_quit(*args)

    def button1Clicked(self, *args):
        window.close()

    def button2Clicked(self, *args):
        if current_frame is None:
            print('buffer is not loaded')
            return
        print(current_frame.shape)
        print('click button2')

window.fullscreen()
window.show_all()
builder.connect_signals(Handler())

def show_frame(*args):
    global current_frame
    ret, frame = cap.read()

    current_frame = frame.copy()
    win_w, win_h = window.get_size()
    img_h, img_w, _ = frame.shape
    frame = cv2.resize(frame, None, fx=win_w/img_w, fy=win_h/img_h, interpolation=cv2.INTER_CUBIC)

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pb = GdkPixbuf.Pixbuf.new_from_data(frame.tostring(),
                                        GdkPixbuf.Colorspace.RGB,
                                        False,
                                        8,
                                        frame.shape[1],
                                        frame.shape[0],
                                        frame.shape[2]*frame.shape[1])
    image.set_from_pixbuf(pb.copy())
    return True

GLib.idle_add(show_frame)
Gtk.main()
