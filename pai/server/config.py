import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--dummy', action='store_true')
parser.add_argument('--host', default='0.0.0.0')
parser.add_argument('--script', default='infer.sh')
parser.add_argument('--port', type=int, default=3000)
parser.add_argument('--results-dir', default='./results')
parser.add_argument('--uploaded-dir', default='./uploaded')
args = parser.parse_args()

USE_DUMMY = args.dummy
HOST = args.host
PORT = args.port
SCRIPT_PATH = os.path.abspath(args.script)

RESULTS_DIR = args.results_dir
UPLOADED_DIR = args.uploaded_dir
