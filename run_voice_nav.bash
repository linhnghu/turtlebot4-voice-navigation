#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export TURTLEBOT4_WORKSPACE="$PWD"
source ./voice_nav_env.bash
export QT_QPA_PLATFORM_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/qt5/plugins
exec /usr/bin/python3 "$PWD/turtlebot4_session.py" start-voice "$@"
