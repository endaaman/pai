FPS_SAMPLE_COUNT = 60
FPS = 30

def check_device(p):
    try:
        os.stat(p)
    except FileNotFoundError:
        return False
    return True

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
    def __init__(self, value, hooks=[], getter=None):
        self.value = None
        self.hooks = []
        for hook in hooks:
            self.subscribe(hook)
        if getter:
            self.override_getter(getter)
        self.set(value)

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

