#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
if [[ ! -t 0 ]]; then
    printf 'Run ./run_teleop.bash in an interactive terminal to use the keyboard.\n' >&2
    exit 1
fi
python3 ./prepare_teleop.py
printf '\nTeleop ready on /cmd_vel (ROS domain %s).\n' "$ROS_DOMAIN_ID"
printf 'Keep this terminal focused. Hold i to move; j/l to turn; k to stop.\n\n'
exec ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args \
    -r cmd_vel:=/cmd_vel -p stamped:=false -p speed:=0.15 -p turn:=0.4
