import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('arg')
args = parser.parse_args()


A = args.arg
print((os.path.abspath(A)))

# TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(A)), 'templates')
