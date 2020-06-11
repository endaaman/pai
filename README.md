# pai

## Requirements

On Debian-based distro

```
$ sudo apt install python3 python-pip3 python3-venv libgirepository1.0-dev libcairo2-dev gstreamer1.0-gtk3 libgstreamer1.0-dev gstreamer1.0-plugins-bad
```

## Client

```
$ poetry install
$ poetry run client
```

See `poetry run client -h` for deitals.

## Server

```
$ poetry install
$ poetry run server
```

See `poetry run server -h` for deitals.

## Poster/slide

```
$ cd poster
$ latexmk poster.tex
$ latexmk slide.tex
```
