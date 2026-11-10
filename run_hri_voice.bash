#!/usr/bin/env bash
set -e
_hri_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
source "${_hri_ws}/install/local_setup.bash"
export ROS_DOMAIN_ID="${HRI_DOMAIN_ID:-66}"
export ROS_LOCALHOST_ONLY=1
export LD_LIBRARY_PATH="${_hri_ws}/.hri-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH):${LD_LIBRARY_PATH:-}"
exec "${_hri_ws}/.venv-hri/bin/python" -c \
  'from hri_multimodal.voice import main; main()' --ros-args \
  -p model_path:="${_hri_ws}/.models/hri/vosk-model-small-en-us-0.15" "$@"
