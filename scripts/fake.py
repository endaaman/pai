#!/usr/bin/env python3
import os
import argparse
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument('input')
args = parser.parse_args()


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOADED_DIR = os.path.join(PROJECT_DIR, 'uploaded')
GENERATED_DIR = os.path.join(PROJECT_DIR, 'generated')

SOURCE_FILE = os.path.join(UPLOADED_DIR, args.input)

print(SOURCE_FILE)

# TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(A)), 'templates')
