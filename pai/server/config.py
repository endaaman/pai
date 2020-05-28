import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--dummy', action='store_true')
parser.add_argument('--host', default='0.0.0.0')
parser.add_argument('--port', type=int, default=3000)
args = parser.parse_args()

USE_DUMMY = args.dummy
HOST = args.host
PORT = args.port

print('servetr conf')
