import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--script',
                    help='Path to inference script')
parser.add_argument('--host', default='0.0.0.0',
                    help='IP addr to which the server listen')
parser.add_argument('--port', type=int, default=3000,
                    help='Port that the server uses')
parser.add_argument('--results-dir', default='./results',
                    help='Dir to save results files')
parser.add_argument('--uploaded-dir', default='./uploaded',
                    help='Dir to save temporary uploaded files')
args = parser.parse_args()

HOST = args.host
PORT = args.port
SCRIPT_PATH = args.script
RESULTS_DIR = args.results_dir
UPLOADED_DIR = args.uploaded_dir
