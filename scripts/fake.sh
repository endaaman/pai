#!/bin/bash

###* PREPARE

TARGET="$1"

if [ -z $TARGET ]; then
  echo 'NO TARGET'
  exit 1
fi

ROOT=$(realpath "$(dirname $0)/..")

BASE=$(echo "$TARGET" | cut -f 1 -d '.')


UPLOADED_PATH=$(realpath "$ROOT/uploaded/$TARGET")
GENERATED_DIR=$(realpath "$ROOT/generated/$BASE")

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
