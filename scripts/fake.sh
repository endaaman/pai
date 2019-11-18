#!/bin/bash

###* PREPARE

NAME="$1"

if [ -z $NAME ]; then
  echo 'NO NAME'
  exit 1
fi

ROOT=$(realpath "$(dirname $0)/..")
BASE=$(echo "$NAME" | cut -f 1 -d '.')

UPLOADED_PATH=$(realpath "$ROOT/uploaded/camera/$NAME")
GENERATED_DIR=$(realpath "$ROOT/generated/camera/$BASE")

if [ ! -e $UPLOADED_PATH ]; then
  echo "NO FILE: $UPLOADED_PATH"
  exit 1
fi


###* PROCEDURE

echo start

sleep 2

mkdir -p $GENERATED_DIR
cp "$UPLOADED_PATH" "$GENERATED_DIR/org.jpg"

echo ok
