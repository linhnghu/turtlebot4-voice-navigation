#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
exec python3 "$PWD/turtlebot4_session.py" start "$@"
