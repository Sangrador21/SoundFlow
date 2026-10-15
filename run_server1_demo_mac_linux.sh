#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN=python3
fi
"$PYTHON_BIN" tools/prepare_demo.py
exec "$PYTHON_BIN" server.py --port 5000 --server-id S1 --music .demo_music/S1 --peer http://127.0.0.1:5001 "$@"
