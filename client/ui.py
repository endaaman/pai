import numpy as np
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gst

class GstWidget(Gtk.Box):
    def __init__(self, src):
        super().__init__()
        self.connect('realize', self._on_realize)
        self.video_bin = Gst.parse_bin_from_description(src, True)

        self.pipeline = Gst.Pipeline()
        factory = self.pipeline.get_factory()
        self.gtksink = factory.make('gtksink')

        self.pipeline.add(self.gtksink)
        self.pipeline.add(self.video_bin)
        self.video_bin.link(self.gtksink)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

    def _on_realize(self, widget):
        w = self.gtksink.get_property('widget')
        self.pack_start(w, True, True, 0)
        w.show()
        self.pipeline.set_state(Gst.State.PLAYING)

    def on_message(self, bus, message):
        if message.type == Gst.MessageType.EOS:
            self.pipeline.set_state(Gst.State.NULL)
            print('EOS')
            return
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print('Error: %s' % err, debug)
            self.pipeline.set_state(Gst.State.NULL)
            return

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
        return arr
