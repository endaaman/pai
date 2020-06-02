import numpy as np
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gst
from PIL import Image

from .config import SYNC


class MessageDialog(Gtk.Dialog):
    def __init__(self, message, title, parent=None):
        Gtk.Dialog.__init__(self, title, parent, 0, (
            # Gtk.STOCK_CANCEL,
            # Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,
            Gtk.ResponseType.OK,
        ))
        self.set_default_size(150, 100)
        label = Gtk.Label(message)
        box = self.get_content_area()
        box.add(label)
        self.show_all()

    @classmethod
    def show(cls, message, title='Message'):
        d = MessageDialog(message, title)
        d.run()
        d.destroy()


class GstWidget(Gtk.Box):
    def __init__(self, src):
        super().__init__()
        self.connect('realize', self._on_realize)
        self.video_bin = Gst.parse_bin_from_description(src, True)
        self.pipeline = Gst.Pipeline()
        factory = self.pipeline.get_factory()
        self.gtksink = factory.make('gtksink')
        self.gtksink.set_property('sync', SYNC)

        self.pipeline.add(self.gtksink)
        self.pipeline.add(self.video_bin)
        self.video_bin.link(self.gtksink)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()

    def _on_realize(self, widget):
        w = self.gtksink.get_property('widget')
        self.pack_start(w, True, True, 0)
        w.show()
        self.pipeline.set_state(Gst.State.PLAYING)

    def start(self):
        if self.gtksink.get_property('widget').get_realized():
            self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        self.pipeline.set_state(Gst.State.PAUSED)


    def take_snapshot(self):
        sample = self.gtksink.get_property('last-sample')
        s = sample.get_caps().get_structure(0)
        width = s.get_int('width').value
        height = s.get_int('height').value
        buffer = sample.get_buffer()
        ret, map_info = buffer.map(Gst.MapFlags.READ)
        if not ret:
            print('ERROR')
            return
        arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(height, width, -1)
        img = Image.fromarray(np.uint8(arr))
        b, g, r, _ = img.split()
        return Image.merge('RGB', (r, g, b))
