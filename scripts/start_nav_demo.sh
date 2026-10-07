#!/usr/bin/env bash
# Start the navigation demo, RViz2, and the example navigation goal.

set -eo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="/opt/ros/humble/setup.bash"
workspace_setup="$repo_dir/install/setup.bash"

usage() {
  echo "用法: $0 [--no-goal]"
  echo "默认按 map_server 配置启动导航和 RViz2，并发送示例目标点 (5.0, 3.0)。"
  echo "--no-goal 仅启动演示，稍后可用 RViz2 的 Publish Point 工具手动发送目标。"
}

send_goal=true
case "${1:-}" in
  "") ;;
  --no-goal) send_goal=false ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  usage >&2
  exit 2
fi

for setup in "$ros_setup" "$workspace_setup"; do
  if [[ ! -f "$setup" ]]; then
    echo "找不到环境文件：$setup" >&2
    exit 1
  fi
done

# The setup scripts are written for normal shells and may read unset variables.
source "$ros_setup"
source "$workspace_setup"

for command in ros2 rviz2 python3 setsid timeout; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "找不到命令：$command" >&2
    exit 1
  fi
done
for package in map_server nav_executor tf_maintainer interfaces; do
  if ! ros2 pkg prefix "$package" >/dev/null 2>&1; then
    echo "找不到已构建的 ROS 包：$package" >&2
    exit 1
  fi
done

log_dir="$(mktemp -d "${TMPDIR:-/tmp}/hwsentry-nav-demo.XXXXXX")"
export ROS_HOME="$log_dir/ros-home"
export ROS_LOG_DIR="$log_dir/ros-logs"
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR"

rviz_config="$log_dir/nav_demo.rviz"
cat >"$rviz_config" <<'RVIZ_CONFIG'
Panels:
  - Class: rviz_common/Displays
    Name: Displays
  - Class: rviz_common/Tool Properties
    Name: Tool Properties
  - Class: rviz_common/Views
    Name: Views
Visualization Manager:
  Class: ""
  Global Options:
    Background Color: 24; 27; 34
    Fixed Frame: map
    Frame Rate: 30
  Displays:
    - Class: rviz_default_plugins/Grid
      Name: Grid
      Enabled: true
      Plane: XY
      Cell Size: 1
      Plane Cell Count: 30
      Color: 85; 85; 90
    - Class: rviz_default_plugins/PointCloud2
      Name: Global Map Cloud
      Enabled: true
      Topic:
        Value: /map_server/debug/global_map_cloud
      Position Transformer: XYZ
      Color Transformer: FlatColor
      Color: 140; 165; 185
      Style: Flat Squares
      Size (Pixels): 2
      Size (m): 0.03
      Alpha: 1
    - Class: rviz_default_plugins/Map
      Name: Final Cost Map
      Enabled: true
      Topic:
        Value: /nav_executor/debug/final_cost_map
      Color Scheme: costmap
      Alpha: 0.45
      Draw Behind: false
    - Class: rviz_default_plugins/Marker
      Name: MINCO Trajectory
      Enabled: true
      Topic:
        Value: /nav_executor/debug/minco_trajectory
    - Class: rviz_default_plugins/Path
      Name: MPC Path
      Enabled: true
      Topic:
        Value: /nav_executor/debug/mpc_path
      Color: 255; 80; 80
      Line Style: Lines
      Line Width: 0.05
      Buffer Length: 1
    - Class: rviz_default_plugins/TF
      Name: TF
      Enabled: true
      Frame Timeout: 15
      Show Axes: true
      Show Arrows: false
      Show Names: true
      Marker Scale: 0.5
  Tools:
    - Class: rviz_default_plugins/Interact
    - Class: rviz_default_plugins/MoveCamera
    - Class: rviz_default_plugins/Select
    - Class: rviz_default_plugins/PublishPoint
      Single click: true
      Topic: /nav_goal
  Views:
    Current:
      Class: rviz_default_plugins/TopDownOrtho
      Scale: 50
      Target Frame: <Fixed Frame>
      X: 14
      Y: 7.5
Window Geometry:
  Width: 1280
  Height: 850
RVIZ_CONFIG

declare -a pids=() names=()

cleanup() {
  trap - EXIT INT TERM
  if (( ${#pids[@]} > 0 )); then
    echo "正在停止导航演示进程……"
    for pid in "${pids[@]}"; do
      kill -INT -- "-$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in "${pids[@]}"; do
      kill -TERM -- "-$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${pids[@]}"; do
      kill -KILL -- "-$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    done
  fi
  echo "日志保存在：$log_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_process() {
  local name="$1"
  shift
  setsid "$@" >"$log_dir/$name.log" 2>&1 &
  pids+=("$!")
  names+=("$name")
  echo "已启动 $name（PID ${pids[-1]}，日志 $log_dir/$name.log）"
}

check_processes() {
  local index
  for index in "${!pids[@]}"; do
    if ! kill -0 "${pids[$index]}" 2>/dev/null; then
      echo "${names[$index]} 已退出，最近日志：" >&2
      tail -n 20 "$log_dir/${names[$index]}.log" >&2
      return 1
    fi
  done
}

wait_for_topic() {
  local topic="$1" count_label="$2" deadline=$((SECONDS + 45))
  echo "等待 $topic 的 $count_label……"
  until ros2 topic info --no-daemon --spin-time 1 "$topic" 2>/dev/null | grep -Eq "${count_label}: [1-9][0-9]*"; do
    check_processes || return 1
    if (( SECONDS >= deadline )); then
      echo "等待 $topic 超时；请查看 $log_dir 中的日志。" >&2
      return 1
    fi
    sleep 1
  done
}

cd "$repo_dir"
start_process map_server ros2 launch map_server map_server.launch.py
start_process nav_executor ros2 launch nav_executor nav_executor.launch.py
start_process tf_maintainer ros2 launch tf_maintainer tf_maintainer.launch.py
start_process wheel_leg_sim python3 utils/py/sim/wheel_leg_lqr_follow_sim.py
start_process nav_goal_relay python3 utils/py/msg/nav_goal_relay.py
start_process rviz2 rviz2 -d "$rviz_config"

wait_for_topic /map_server/global_cost_map 'Publisher count'
wait_for_topic /small_glim/odometry 'Publisher count'
wait_for_topic /decision/nav_goal 'Subscription count'
wait_for_topic /nav_goal 'Subscription count'
check_processes

if [[ "$send_goal" == true ]]; then
  echo "发送示例目标：map 坐标 (5.0, 3.0)"
  if ! timeout 15s ros2 topic pub --once /nav_goal geometry_msgs/msg/PointStamped \
    '{header: {frame_id: map}, point: {x: 5.0, y: 3.0, z: 0.0}}'; then
    echo "发送目标失败；请查看 $log_dir 中的日志。" >&2
    exit 1
  fi
fi

echo "导航演示和 RViz2 已启动。可在 RViz2 中使用 Publish Point 工具点击新目标。"
echo "按 Ctrl+C 停止全部进程。日志目录：$log_dir"
if wait -n "${pids[@]}"; then
  echo "一个演示进程已结束，正在停止其他进程。" >&2
else
  echo "一个演示进程异常退出，正在停止其他进程；请查看 $log_dir 中的日志。" >&2
  exit 1
fi
