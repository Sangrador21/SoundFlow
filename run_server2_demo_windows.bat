@echo off
py server.py --host 127.0.0.1 --port 5001 --server-id S2 --advertise-host 127.0.0.1 --max-streams 2 --peer 127.0.0.1:5000 %*
