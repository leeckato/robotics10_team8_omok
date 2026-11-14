#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
exec ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=110.120.1.63 port:=12345 model:=e0509
