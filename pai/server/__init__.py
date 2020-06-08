import os
import json
from collections import namedtuple, OrderedDict
import subprocess
from PIL import Image
from pprint import pprint

from tornado import web, ioloop, gen

from pai.common import ORIGINAL_FILENAME, Result

from .config import USE_DUMMY, HOST, PORT, SCRIPT_PATH, RESULTS_DIR, UPLOADED_DIR

def get_result(name):
    d = os.path.join(RESULTS_DIR, name)
    filenames = os.listdir(d)
    if not ORIGINAL_FILENAME in filenames:
        return None
    filenames.remove(ORIGINAL_FILENAME)
    overlays = sorted([filename for filename in filenames if 'overlay' in filename])
    return Result(name, ORIGINAL_FILENAME, overlays)


def get_results():
    dirs = os.listdir(RESULTS_DIR)
    results = []
    for name in reversed(sorted(dirs)):
        result = get_result(name)
        if not result:
            print(f'skip {d} because {ORIGINAL_FILENAME} is not contained')
            continue
        results.append(result)
    return results

def command_dummuy(image_path, name):
    overlay_filename = 'overlay.png'
    target_dir = os.path.join(RESULTS_DIR, name)
    os.makedirs(target_dir, exist_ok=True)
    sp = subprocess.Popen(f'cp {image_path} {target_dir}/{ORIGINAL_FILENAME}', shell=True)
    sp.wait()
    bases_size = Image.open(image_path).size
    overlay = Image.new('RGBA', bases_size, color=(255, 100, 50, 200))
    overlay.save(os.path.join(target_dir, overlay_filename))
    return get_result(name)

def command_inference(image_path, name):
    cmd = f'bash {SCRIPT_PATH} {image_path} {name}'
    print(f'Running: "{cmd}"')
    sp = subprocess.Popen(cmd, shell=True)
    sp.wait()
    return get_result(name)

class MainHandler(web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    async def get(self):
        loop = ioloop.IOLoop.current()
        results = await loop.run_in_executor(None, get_results)
        self.write(json.dumps([r._asdict() for r in results]))

class AnalyzeHandler(web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    async def post(self):
        img = self.request.files['image'][0]
        name = self.get_argument('name')

        image_path = os.path.join(UPLOADED_DIR, f'{name}.png')
        with open(image_path, 'wb') as f:
            f.write(img['body'])

        if USE_DUMMY:
            loop = ioloop.IOLoop.current()
            result = await loop.run_in_executor(None, command_dummuy, image_path, name)
            await gen.sleep(3)
        else:
            loop = ioloop.IOLoop.current()
            result = await loop.run_in_executor(None, command_inference, image_path, name)

        print('Result: ', result)
        self.write(result._asdict())


def start():
    app = web.Application([
        (r'/results', MainHandler),
        (r'/analyze', AnalyzeHandler),
        (r'/images/(.*)', web.StaticFileHandler, {'path': RESULTS_DIR}),
    ])
    app.listen(PORT, HOST)
    print(f'Server start at {HOST}:{PORT}')
    ioloop.IOLoop.current().start()
