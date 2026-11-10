#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
python3 -m venv --system-site-packages .venv-yolo
.venv-yolo/bin/python -m pip install torch==2.5.1+cpu torchvision==0.20.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu
.venv-yolo/bin/python -m pip install -r requirements-vision.txt
mkdir -p .models
.venv-yolo/bin/python - <<'PY'
from ultralytics import YOLO
from cv_bridge import CvBridge
import numpy as np
YOLO('.models/yolo11n.pt')
assert CvBridge().cv2_to_imgmsg(np.zeros((8, 8, 3), dtype=np.uint8), 'bgr8').width == 8
print('YOLO and cv_bridge ready.')
PY
colcon build --symlink-install --packages-select turtlebot4_lab turtlebot4_vision_nav
