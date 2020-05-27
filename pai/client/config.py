import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action='store_true')
parser.add_argument('-a', '--api-host', default='localhost:3000')
args = parser.parse_args()


if args.test:
    GST_SOURCE = 'videotestsrc ! clockoverlay'
else:
    GST_SOURCE = 'v4l2src ! videoconvert'

CHUNK_SIZE = 1024
API_HOST = args.api_host

RECONNECT_INTERVAL = 5
SERVER_POLLING_INTERVAL = 3
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
