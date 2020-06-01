import argparse


parser = argparse.ArgumentParser()
parser.add_argument('--src')
parser.add_argument('--api-host', default='http://localhost:3000')
parser.add_argument('--device', default='/dev/video0')
args = parser.parse_args()

DEVICE = args.device
if args.src:
    GST_SOURCE = args.src
else:
    GST_SOURCE = 'videotestsrc ! clockoverlay'

API_HOST = args.api_host
RECONNECT_INTERVAL = 5
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
