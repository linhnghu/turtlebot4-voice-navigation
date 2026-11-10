#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ./turtlebot4_env.bash
mkdir -p maps
ros2 run nav2_map_server map_saver_cli -f "$PWD/maps/map" --ros-args \
    -p use_sim_time:=true -p save_map_timeout:=15.0 -p map_subscribe_transient_local:=true \
    -p free_thresh_default:=0.196 -p occupied_thresh_default:=0.65
test -s maps/map.yaml
test -s maps/map.pgm
printf 'Saved: %s/maps/map.yaml and map.pgm\n' "$PWD"
