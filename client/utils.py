import io
import os
import threading
import time
import asyncio
import cv2
import requests
import numpy as np


FPS_SAMPLE_COUNT = 60
FPS = 30

def check_device(p):
    try:
        os.stat(p)
    except FileNotFoundError:
        return False
    return True

def download_image(path):
    r = requests.get(path, stream=True)
    if r.status_code != 200:
        print('not 200:', r.status_code, path)
        return None
    stream = io.BytesIO()
    for chunk in r.iter_content(1024):
        stream.write(chunk)
    return cv2.imdecode(np.frombuffer(stream.getvalue(), dtype=np.uint8), cv2.IMREAD_COLOR)
    # return cv2.imdecode(stream.getvalue(), cv2.IMREAD_COLOR)

def async_signal(F):
    def inner(loop, *args):
        loop.run_until_complete(F(*args))

    def outer(*args):
        loop = asyncio.get_event_loop()
        thread = threading.Thread(target=inner, args=(loop, *args))
        thread.daemon = True
        thread.start()

    return outer

async def glib_one_tick():
    pass

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

    def subscribe(self, hook):
        self.hook = hook

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

