#!/bin/sh
# Start Adam from anywhere: ./run_adam.sh
cd "$(dirname "$0")" && exec .venv/bin/python adam.py "$@"
