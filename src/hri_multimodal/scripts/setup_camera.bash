#!/usr/bin/env bash
set -euo pipefail
_hri_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
/usr/bin/python3 -m venv --system-site-packages "${_hri_ws}/.venv-gesture"
"${_hri_ws}/.venv-gesture/bin/python" -m pip install -r "${_hri_ws}/src/hri_multimodal/requirements-camera.txt"
mkdir -p "${_hri_ws}/.models"
"${_hri_ws}/.venv-gesture/bin/python" - "${_hri_ws}/.models/gesture_recognizer.task" <<'PY'
from pathlib import Path
import os
import sys
import urllib.request
import mediapipe as mp
target = Path(sys.argv[1])
if not target.is_file():
    temporary = target.with_suffix('.download')
    urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/'
        'gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task', temporary)
    os.replace(temporary, target)
with mp.tasks.vision.GestureRecognizer.create_from_options(
        mp.tasks.vision.GestureRecognizerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(target)))):
    print('Camera model ready:', target)
PY
