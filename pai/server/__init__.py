import os
from collections import namedtuple, OrderedDict
import subprocess

from pprint import pprint
import tornado.ioloop
import tornado.web

GENARATED_PATH = os.path.join(os.getcwd(), 'generated')
UPLOADED_PATH = os.path.join(os.getcwd(), 'uploaded')

Result = namedtuple('Result', ['name', 'original', 'overlays'])


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

class AnalyzeHandler(tornado.web.RequestHandler):
    def post(self):
        img = self.request.files['image'][0]
        name = self.get_argument('name')

        org_path = os.path.join(UPLOADED_PATH, f'{name}.jpg')
        with open(org_path, 'wb') as f:
            f.write(img['body'])

        ### TODO: imple inference
        target_dir = os.path.join(GENARATED_PATH, name)
        os.makedirs(target_dir, exist_ok=True)
        sp = subprocess.Popen(f'cp {org_path} {target_dir}/org.jpg', shell=True)
        sp.wait()

        result = Result(name, 'org.jpg', [])
        print('Result: ', result)
        self.write(result._asdict())


def start():
    app = tornado.web.Application([
        (r'/', MainHandler),
        (r'/analyze', AnalyzeHandler),
        (r'/generated/(.*)', tornado.web.StaticFileHandler, {'path': GENARATED_PATH}),
    ])
    app.listen(3000)
    tornado.ioloop.IOLoop.current().start()
