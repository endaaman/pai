import argparse

print('client conf')

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--test', action='store_true')
parser.add_argument('-a', '--api-host', default='http://localhost:3000')
args = parser.parse_args()


if args.test:
    GST_SOURCE = 'videotestsrc ! clockoverlay'
else:
    GST_SOURCE = 'v4l2src ! videoconvert'

API_HOST = args.api_host
RECONNECT_INTERVAL = 5
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
