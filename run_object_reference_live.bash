#!/usr/bin/env bash
set -e
_reference_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
source "${_reference_ws}/install/local_setup.bash"
export ROS_DOMAIN_ID="${REFERENCE_DOMAIN_ID:-68}"
export ROS_LOCALHOST_ONLY=1
export LD_LIBRARY_PATH="${_reference_ws}/.hri-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH):${LD_LIBRARY_PATH:-}"
unset GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GIO_MODULE_DIR
unset GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR QT_QPA_PLATFORM_PLUGIN_PATH
unset GSETTINGS_SCHEMA_DIR
if [[ -n "${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-}" ]]; then
    export XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG"
fi
exec ros2 launch hri_object_reference live.launch.py \
    camera_python:="${_reference_ws}/.venv-gesture/bin/python" \
    voice_python:="${_reference_ws}/.venv-hri/bin/python" \
    voice_model:="${_reference_ws}/.models/hri/vosk-model-small-vn-0.4" "$@"
