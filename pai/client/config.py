import argparse


parser = argparse.ArgumentParser()
parser.add_argument('--dummy', action='store_true')
parser.add_argument('--h264', action='store_true')
parser.add_argument('--api-host', default='http://localhost:3000')
parser.add_argument('--device', default='/dev/video0')
args = parser.parse_args()

DEVICE = args.device
if args.dummy:
    GST_SOURCE = ' ! '.join(['videotestsrc', 'clockoverlay'])
else:
    ss = [f'v4l2src device={DEVICE}', 'videoconvert']
    if args.h264:
        ss.insert(1, 'avdec_h264')
    GST_SOURCE = ' ! '.join(ss)

API_HOST = args.api_host
RECONNECT_INTERVAL = 5
RESULT_TREE_UPDATE_INTERVAL = 20 * 1000
