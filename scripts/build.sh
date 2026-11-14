#!/usr/bin/env bash
set -e
source "$(dirname -- "$0")/env.sh"
cd "$GOMOKU_WS"
python3 "$GOMOKU_WS/scripts/setup_config.py"
colcon_path="$(command -v colcon)"
if [[ -z "$colcon_path" ]]; then echo 'Install python3-colcon-common-extensions first.' >&2; exit 1; fi
python3 "$colcon_path" build --base-paths "$GOMOKU_WS/src" --symlink-install --cmake-args -DPython3_EXECUTABLE="$(command -v python3)" "$@"
echo 'Build finished. Run: source ~/omok_integrated/scripts/env.sh'
