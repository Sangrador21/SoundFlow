#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN=python3
fi
exec "$PYTHON_BIN" server.py --port 5000 --server-id S1 "$@"
