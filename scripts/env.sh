#!/usr/bin/env bash
# Use: source ~/omok_integrated/scripts/env.sh
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Use: source ~/omok_integrated/scripts/env.sh' >&2
  exit 1
fi
export GOMOKU_WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f /opt/ros/jazzy/setup.bash ]]; then
  echo 'ROS 2 Jazzy setup not found: /opt/ros/jazzy/setup.bash' >&2
  return 1
fi
source /opt/ros/jazzy/setup.bash || return 1
if [[ -f "$HOME/ros2_ws/install/setup.bash" ]]; then
  source "$HOME/ros2_ws/install/setup.bash" || return 1
fi
if [[ -f "$HOME/gomoku_ros_env/bin/activate" ]]; then
  source "$HOME/gomoku_ros_env/bin/activate" || return 1
else
  echo 'Python environment missing: create ~/gomoku_ros_env before build/run.' >&2
  return 1
fi
if [[ -f "$GOMOKU_WS/install/setup.bash" ]]; then
  source "$GOMOKU_WS/install/setup.bash" || return 1
fi
