#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec python3 "$PWD/turtlebot4_session.py" stop
