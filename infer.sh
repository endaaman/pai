#!/bin/bash

set -ue

base=$(realpath $(dirname $0))
image_path=$1
name=$2

project_dir="$HOME/src/github.com/endaaman/prostate"
py='/opt/miniconda3/envs/prostate/bin/python'
script="${project_dir}/infer.py"
weight="${project_dir}/weights/gen3/768/unet16n/unet16n_30.pt"

cmd="$py $script -w $weight -m unet16n --dest ${base}/results/${name} ${image_path} --size 2000"
echo Running "$cmd"
$cmd
