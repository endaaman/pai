import os
from collections import namedtuple, OrderedDict
import subprocess

from pprint import pprint
import tornado.ioloop
import tornado.web

RESULTS_PATH = os.path.join(os.getcwd(), 'results')
UPLOADED_PATH = os.path.join(os.getcwd(), 'uploaded')

Result = namedtuple('Result', ['name', 'original', 'overlays'])


def command_dummuy(image_path, name):
    overlay_filename = 'overlay1.png'
    target_dir = os.path.join(RESULTS_PATH, name)
    os.makedirs(target_dir, exist_ok=True)
    sp = subprocess.Popen(f'cp {image_path} {target_dir}/org.jpg', shell=True)
    sp.wait()
    bases_size = Image.open(image_path).size
    overlay = Image.new('RGBA', bases_size, color=(255, 100, 50, 200))
    overlay.save(os.path.join(target_dir, overlay_filename))

    return [overlay_filename]

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

class AnalyzeHandler(tornado.web.RequestHandler):
    def post(self):
        img = self.request.files['image'][0]
        name = self.get_argument('name')

        image_path = os.path.join(UPLOADED_PATH, f'{name}.jpg')
        with open(image_path, 'wb') as f:
            f.write(img['body'])

        ### TODO: imple inference
        overlays = command_dummuy()

        result = Result(name, 'org.jpg', overlays)
        print('Result: ', result)
        self.write(result._asdict())


def start():
    app = tornado.web.Application([
        (r'/', MainHandler),
        (r'/analyze', AnalyzeHandler),
        (r'/results/(.*)', tornado.web.StaticFileHandler, {'path': RESULTS_PATH}),
    ])
    app.listen(3000)
    tornado.ioloop.IOLoop.current().start()
