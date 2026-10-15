#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN=python3
fi
exec "$PYTHON_BIN" main.py --server http://127.0.0.1:5000 --fallback http://127.0.0.1:5001 "$@"
