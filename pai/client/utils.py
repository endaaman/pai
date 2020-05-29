import io
import os
import threading
import asyncio
import time
import array
import functools
from PIL import Image

import numpy as np
from gi.repository import GLib

from gi.repository import GdkPixbuf


FPS_SAMPLE_COUNT = 60
FPS = 30

def check_device(p):
    try:
        os.stat(p)
    except FileNotFoundError:
        return False
    return True

def glib_async(loop):
    def _glib_async(F):
        def inner(*args):
            return loop.create_task(F(*args))
        return inner
    return _glib_async

class Withable:
    def __init__(self, leave, enter):
        self.enter = enter
        self.leave = leave

    def __enter__(self):
        if self.enter:
            self.enter()

    def __exit__(self, *args):
        self.leave()

last_timout_tag = None
def debounce(duration, func):
    global last_timout_tag
    if last_timout_tag:
        GLib.source_remove(last_timout_tag)
        last_timout_tag = None
    last_timout_tag = GLib.timeout_add(duration, func)

def cv2pixbuf(self, img, color_converting=True):
    if color_converting:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return GdkPixbuf.Pixbuf.new_from_data(
        img.tobytes(),
        GdkPixbuf.Colorspace.RGB,
        False,
        8,
        image.shape[1],
        image.shape[0],
        image.shape[2] * image.shape[1])

def pil2pixbuf(img):
    img = img.convert('RGB')
    arr = array.array('B', img.tobytes())
    width, height = img.size
    return GdkPixbuf.Pixbuf.new_from_data(arr, GdkPixbuf.Colorspace.RGB, False, 8, width, height, 3 * img.width)

def applay_pil_image_to_gtk_image(gtk_image, pil_image):
    pb = pil2pixbuf(pil_image)
    gtk_image.set_from_pixbuf(pb)


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
            self.value = 1000 / (elapsed / FPS_SAMPLE_COUNT)
            self.count = 0
            self.calculated = True
            return
        self.count += 1

def create_model(handler, loop):
    class _Model():
        def __init__(self, name, value):
            self.name = name
            self.value = value
            self.changed = False

        async def inner(self, v):
            await asyncio.sleep(0)
            self.changed = True
            handler()
            self.changed = False

        def set(self, v):
            org = self.value
            self.value = v
            if org != v:
                print(f'Model[{self.name}] updated: ', org, ' -> ', v)
                loop.create_task(self.inner(v))

        def get(self):
            return self.value

    return _Model


def image_overlay(back, fore, alpha):
    back = np.asarray(back)
    fore = np.asarray(fore)
    if fore.shape[2] > 3:
        mask = fore[:,:,[3]] * alpha / 255
    else:
        mask = alpha
    a = back[:,:,0:3] * (- mask + 1)
    b = fore[:,:,0:3] * mask
    out = (a + b).astype(np.uint8)
    return Image.fromarray(out)

def overlay_transparent(background, overlay, alpha=1.0, x=0, y=0):
    background = np.copy(background)
    background_width = background.shape[1]
    background_height = background.shape[0]

    if x >= background_width or y >= background_height:
        return background

    h, w = overlay.shape[0], overlay.shape[1]

    if x + w > background_width:
        w = background_width - x
        overlay = overlay[:, :w]

    if y + h > background_height:
        h = background_height - y
        overlay = overlay[:h]

    if overlay.shape[2] < 4:
        overlay = np.concatenate(
            [
                overlay,
                np.ones((overlay.shape[0], overlay.shape[1], 1), dtype = overlay.dtype) * 255
            ],
            axis = 2,
        )
    overlay_image = overlay[..., :3]
    mask = (overlay[..., 3:] / 255.0) * alpha
    background[y:y+h, x:x+w] = (1.0 - mask) * background[y:y+h, x:x+w] + mask * overlay_image
    return background
