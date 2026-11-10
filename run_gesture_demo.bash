#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
export TURTLEBOT4_WORKSPACE="$PWD"
if [[ ! -x .venv-gesture/bin/python || ! -f .models/gesture_recognizer.task || ! -d install/turtlebot4_gesture ]]; then
    printf 'Run ./setup_gesture.bash first.\n' >&2
    exit 1
fi
exec python3 "$PWD/turtlebot4_session.py" start-gesture "$@"
