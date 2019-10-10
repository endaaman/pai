import os
from datetime import datetime
import time
import threading
import json
import subprocess

import numpy as np
import cv2
import werkzeug
from flask import Flask, request, make_response, jsonify
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

UPLOAD_DIR = 'uploads/'

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024


class Status:
    def __init__(self):
        self.current = None

    def is_active(self):
        return self.current != None

    def clear_current(self):
        self.current = None

    def set_current(self, item):
        self.current = item

    def to_json(self):
        data = {
                'current': self.current,
                'time': str(datetime.now()),
                }
        return json.dumps(data)

status = Status()

def generate_id():
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def get_path(id):
    return os.path.join(UPLOAD_DIR, id + '.jpg')

@app.errorhandler(werkzeug.exceptions.RequestEntityTooLarge)
def handle_over_max_file_size(error):
    app.logger.debug('werkzeug.exceptions.RequestEntityTooLarge')
    return 'result : file size is overed.'

@app.route('/api/upload', methods=['POST'])
def upload():
    if status.is_active():
        return make_response(jsonify({'result': 'now there is an active item.'}))

    if 'uploadFile' not in request.files:
        return make_response(jsonify({'result': 'upload file is required.'}))

    f = request.files['uploadFile']
    id = generate_id()
    f.save(get_path(id))
    # process_current_item(id)
    return make_response(jsonify({'result': 'upload OK.', 'id': id}))

@app.route('/api/status')
def pipe():
    ws = request.environ.get('wsgi.websocket')
    if not ws:
        return
    print('ESTABLISHED CONNECTION')
    while True:
        time.sleep(1)
        message = ws.receive()
        if not message or ws.closed:
            app.logger.debug('SOCKET CLOSED')
            break
        if message == 'status':
            data = status.to_json()
            ws.send(data)
            continue
        print(type(message))
        arr = np.frombuffer(message, dtype='uint8')
        arr = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        id = generate_id()
        cv2.imwrite(get_path(id), arr)
        status.set_current(id)
        process_current_item()
        print('ID: ', id, arr.shape)
    return make_response('done')

@app.route('/api/images')
def images():
    app.logger.debug('images')
    return make_response('images')

def process_current_item():
    def inner():
        print('inner')
        time.sleep(7)
        # subprocess.check_output(["ls", "-l"])
        print('done')
        status.clear_current()
    thread = threading.Thread(target=inner)
    thread.daemon = True
    thread.start()

# main
if __name__ == '__main__':
    app.logger.debug(app.url_map)
    # app.run(host='localhost', port=3000, debug=True)
    server = pywsgi.WSGIServer(('', 8080), app, handler_class=WebSocketHandler)
    server.serve_forever()
