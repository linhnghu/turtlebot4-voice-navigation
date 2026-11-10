#!/usr/bin/env bash
set -euo pipefail
_engagement_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
/usr/bin/python3 -m venv --system-site-packages "${_engagement_ws}/.venv-gesture"
"${_engagement_ws}/.venv-gesture/bin/python" -m pip install -r "${_engagement_ws}/src/hri_engagement/requirements-camera.txt"
"${_engagement_ws}/.venv-gesture/bin/python" -c 'import mediapipe as mp; print("MediaPipe ready:", mp.__version__); assert hasattr(mp, "solutions")'
