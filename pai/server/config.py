import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--script', default='infer.sh',
                    help='Path to inference script')
parser.add_argument('--host', default='0.0.0.0',
                    help='IP addr to which the server listen')
parser.add_argument('--port', type=int, default=3000,
                    help='Port which the server uses')
parser.add_argument('--results-dir', default='./results',
                    help='Path to dir where the results files are saved')
parser.add_argument('--uploaded-dir', default='./uploaded',
                    help='Path to dir where the temporary uploaded files are saved')
args = parser.parse_args()

USE_DUMMY = args.dummy
HOST = args.host
PORT = args.port
SCRIPT_PATH = os.path.abspath(args.script)

RESULTS_DIR = args.results_dir
UPLOADED_DIR = args.uploaded_dir
