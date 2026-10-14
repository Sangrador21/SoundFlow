#!/usr/bin/env bash
set -e
python3 server.py --host 127.0.0.1 --port 5000 --server-id S1 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5001 "$@"
