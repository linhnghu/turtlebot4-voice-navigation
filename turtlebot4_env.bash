# Source this file from each terminal used for the practical.
_tb4_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
# All lab terminals use an isolated DDS domain to avoid robots on the LAN.
export ROS_DOMAIN_ID="${TURTLEBOT4_LAB_DOMAIN_ID:-49}"
export ROS_LOCALHOST_ONLY=1
export FASTRTPS_DEFAULT_PROFILES_FILE="${_tb4_ws}/src/turtlebot4_lab/config/fastdds.xml"
# VS Code Snap exports GTK/GIO modules linked to its own glibc. Use host modules
# for ROS desktop applications to avoid GLIBC_PRIVATE symbol lookup failures.
if [[ "${GTK_PATH:-}" == /snap/* || "${GIO_MODULE_DIR:-}" == */snap/* ]]; then
    unset GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GIO_MODULE_DIR
    unset GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR
fi
if [[ "${GSETTINGS_SCHEMA_DIR:-}" == /snap/* || "${SNAP_NAME:-}" == code ]]; then
    unset GSETTINGS_SCHEMA_DIR
    if [[ -n "${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-}" ]]; then
        export XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG"
    fi
fi
if [[ "${TURTLEBOT4_LAB_RENDERING_FIX:-1}" == 1 ]] && \
    python3 "${_tb4_ws}/prepare_turtlebot4_rendering.py"; then
    export AMENT_PREFIX_PATH="${_tb4_ws}/.turtlebot4_compat:${AMENT_PREFIX_PATH:-}"
fi
if [[ -f "${_tb4_ws}/install/local_setup.bash" ]]; then
    source "${_tb4_ws}/install/local_setup.bash"
fi
unset _tb4_ws
