#!/usr/bin/env bash
set -e
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
exec ros2 run gomoku_system calibrate --config "$HOME/.config/gomoku/marker_calibration.json" "$@"
