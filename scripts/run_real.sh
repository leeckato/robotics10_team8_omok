#!/usr/bin/env bash
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
params_file="$GOMOKU_WS/src/team_robot/config/robot_params.yaml"
gripper_file="$GOMOKU_WS/src/team_robot/robot_assets/gripper_drl.py"
[[ -f "$params_file" && -f "$gripper_file" ]] || { echo 'Robot source config or gripper script missing' >&2; exit 1; }
echo "Robot settings: $params_file"
echo "Gripper script: $gripper_file"
exec ros2 launch team_robot omok_game.launch.py robot_mode:=real use_hand:="${1:-true}" n_playout:=100 robot_params:="$params_file" gripper_drl:="$gripper_file"
