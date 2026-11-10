#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
/usr/bin/python3 -m venv --system-site-packages .venv-gesture
.venv-gesture/bin/python -m pip install -r requirements-gesture.txt
mkdir -p .models
.venv-gesture/bin/python - <<'PY'
from pathlib import Path
import os
import urllib.request
import mediapipe as mp
import cv2
import rclpy
target = Path('.models/gesture_recognizer.task')
if not target.exists():
    temporary = target.with_suffix('.download')
    urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/'
        'gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task', temporary)
    os.replace(temporary, target)
with mp.tasks.vision.GestureRecognizer.create_from_options(
        mp.tasks.vision.GestureRecognizerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(target)))):
    print(f'MediaPipe {mp.__version__}, OpenCV {cv2.__version__}: model ready.')
PY
colcon build --symlink-install --packages-select turtlebot4_gesture
