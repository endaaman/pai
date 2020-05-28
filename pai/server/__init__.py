import os
import json
from collections import namedtuple, OrderedDict
import subprocess
from PIL import Image
from pprint import pprint

from tornado import web, ioloop, gen

from pai.common import ORIGINAL_FILENAME, Result


RESULTS_PATH = os.path.join(os.getcwd(), 'results')
UPLOADED_PATH = os.path.join(os.getcwd(), 'uploaded')


def list_images():
    dirs = os.listdir(RESULTS_PATH)
    results = []
    for name in dirs:
        d = os.path.join(RESULTS_PATH, name)
        files = os.listdir(d)
        if not ORIGINAL_FILENAME in files:
            print(f'skip {d} because {ORIGINAL_FILENAME} is not contained')
            continue
        files.remove(ORIGINAL_FILENAME)
        results.append(Result(name, ORIGINAL_FILENAME, files))
    return results

def command_dummuy(image_path, name):
    overlay_filename = 'overlay1.png'
    target_dir = os.path.join(RESULTS_PATH, name)
    os.makedirs(target_dir, exist_ok=True)
    sp = subprocess.Popen(f'cp {image_path} {target_dir}/{ORIGINAL_FILENAME}', shell=True)
    sp.wait()
    bases_size = Image.open(image_path).size
    overlay = Image.new('RGBA', bases_size, color=(255, 100, 50, 200))
    overlay.save(os.path.join(target_dir, overlay_filename))
    return [overlay_filename]

class MainHandler(web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    async def get(self):
        loop = ioloop.IOLoop.current()
        results = await loop.run_in_executor(None, list_images)
        self.write(json.dumps([r._asdict() for r in results]))

class AnalyzeHandler(web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    async def post(self):
        img = self.request.files['image'][0]
        name = self.get_argument('name')

        image_path = os.path.join(UPLOADED_PATH, f'{name}.png')
        with open(image_path, 'wb') as f:
            f.write(img['body'])

        ### TODO: imple inference
        loop = ioloop.IOLoop.current()
        overlays = await loop.run_in_executor(None, command_dummuy, image_path, name)
        await gen.sleep(3)

        result = Result(name, ORIGINAL_FILENAME, overlays)
        print('Result: ', result)
        self.write(result._asdict())


def start():
    app = web.Application([
        (r'/results', MainHandler),
        (r'/analyze', AnalyzeHandler),
        (r'/images/(.*)', web.StaticFileHandler, {'path': RESULTS_PATH}),
    ])
    app.listen(3000)
    ioloop.IOLoop.current().start()
