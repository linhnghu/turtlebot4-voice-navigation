#!/usr/bin/env python3
"""Create a local overlay for the upstream Ogre1 minimum-range lidar bug."""
from pathlib import Path
import re
import shutil

from ament_index_python.packages import get_package_share_directory

workspace = Path(__file__).resolve().parent
source = Path(get_package_share_directory('irobot_create_description'))
prefix = workspace / '.turtlebot4_compat'
target = prefix / 'share/irobot_create_description'
if not target.exists():
    shutil.copytree(source, target)
xacro = target / 'urdf/create3.urdf.xacro'
original = source / 'urdf/create3.urdf.xacro'
text = original.read_text()
updated = text.replace('<render_engine>ogre</render_engine>',
                       '<render_engine>ogre2</render_engine>')
if not xacro.exists() or xacro.read_text() != updated:
    xacro.write_text(updated)
index = prefix / 'share/ament_index/resource_index/packages'
index.mkdir(parents=True, exist_ok=True)
(index / 'irobot_create_description').touch()

# The upstream Lite GUI starts at floor level. Use an elevated camera so the
# robot and maze are visible immediately in the practical.
bringup_source = Path(get_package_share_directory('turtlebot4_ignition_bringup'))
bringup_target = prefix / 'share/turtlebot4_ignition_bringup'
if not bringup_target.exists():
    shutil.copytree(bringup_source, bringup_target)
for model in ('lite', 'standard'):
    gui = bringup_target / 'gui' / model / 'gui.config'
    config = gui.read_text()
    updated = re.sub(r'<camera_pose>.*?</camera_pose>',
                     '<camera_pose>-5 -5 10 0 0.95 0.7854</camera_pose>', config)
    if config != updated:
        gui.write_text(updated)
(index / 'turtlebot4_ignition_bringup').touch()
