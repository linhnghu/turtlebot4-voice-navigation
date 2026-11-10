# Source in terminals used for Lesson 7; isolated from other lab demos.
_vn_env_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export TURTLEBOT4_LAB_DOMAIN_ID="${VOICE_NAV_DOMAIN_ID:-57}"
source "${_vn_env_ws}/turtlebot4_env.bash"
export IGN_PARTITION="tb4_voice_${USER}_${ROS_DOMAIN_ID}"
export LD_LIBRARY_PATH="${_vn_env_ws}/.voice-nav-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH):${LD_LIBRARY_PATH:-}"
export ROS_LOG_DIR="${_vn_env_ws}/artifacts/voice_nav/roslog"
mkdir -p "$ROS_LOG_DIR"
unset _vn_env_ws
