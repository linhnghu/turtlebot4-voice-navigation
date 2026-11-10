#!/usr/bin/env bash
set -e
_hri_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
source "${_hri_ws}/install/local_setup.bash"
export HRI_WORKSPACE="${_hri_ws}"
export ROS_DOMAIN_ID="${HRI_DOMAIN_ID:-66}"
export ROS_LOCALHOST_ONLY=1
export IGN_PARTITION="${HRI_IGN_PARTITION:-hri_${USER}_${ROS_DOMAIN_ID}}"
unset GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GIO_MODULE_DIR GIO_EXTRA_MODULES
unset GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR QT_QPA_PLATFORM_PLUGIN_PATH GSETTINGS_SCHEMA_DIR
if [[ -n "${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-}" ]]; then
    export XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG"
fi
exec ros2 launch hri_multimodal gazebo.launch.py "$@"
