import argparse


parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action='store_true')
parser.add_argument('-a', '--api-host', default='http://localhost:3000')
parser.add_argument('--device', default='/dev/video0')
args = parser.parse_args()

DEVICE=args.device
if args.test:
    GST_SOURCE = 'videotestsrc ! clockoverlay'
else:
    GST_SOURCE = f'v4l2src device={DEVICE} ! videoconvert'

API_HOST = args.api_host
RECONNECT_INTERVAL = 5
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
