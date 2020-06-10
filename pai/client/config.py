import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--src',
                    help='GStreamer src e.g. `v4l2src device=/dev/video0 ! videoconvert`')
parser.add_argument('--api-uri', default='http://localhost:3000',
                    help='Base URI of server e.g. `http://localhost:3000`')
parser.add_argument('--sync', action='store_true',
                    help='`sync` option for gtksink')
args = parser.parse_args()

if args.src:
    GST_SOURCE = args.src
else:
    GST_SOURCE = 'videotestsrc ! clockoverlay'

SYNC = args.sync
API_URI = args.api_uri
RECONNECT_INTERVAL = 5
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
