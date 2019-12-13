import io
import os
import threading
import asyncio
import time

import cv2
import numpy as np
from gi.repository import GLib


FPS_SAMPLE_COUNT = 60
FPS = 30

def check_device(p):
    try:
        os.stat(p)
    except FileNotFoundError:
        return False
    return True

def async_glib(F):
    def inner(*args):
        loop = asyncio.get_event_loop()
        return loop.create_task(F(*args))
    return inner


last_timout_tag = None
def debounce(duration, func):
    global last_timout_tag
    if last_timout_tag:
        GLib.source_remove(last_timout_tag)
        last_timout_tag = None
    last_timout_tag = GLib.timeout_add(duration, func)


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

class Model():
    def __init__(self, value, hook=None, getter=None):
        self.value = None
        self.getter = None
        self.hook = None
        if hook:
            self.subscribe(hook)
        if getter:
            self.override_getter(getter)
        self.set(value)

    def subscribe(self, hook, immediate=False):
        self.hook = hook
        if immediate:
            self.set(self.value)

    def override_getter(self, getter):
        self.getter = getter

    def set(self, v):
        old_value = self.value
        self.value = v
        if self.hook:
            self.hook(v, old_value)

    def get(self):
        if self.getter:
            return self.getter(self.value)
        return self.value

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
