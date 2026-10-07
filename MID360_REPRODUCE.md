# 使用 MID360 复现 HWSentryNav26

使用 MID360 采集地图、离线优化并重新定位，再用模拟底盘验证导航。环境为 Ubuntu 22.04 / ROS 2 Humble；先完成 [README 的环境配置](./README.md)，安装 Livox SDK2，并构建本仓库及 `HWSentryCommon26`。

## 1. 连接雷达

断电接线：航插接 MID360，RJ45 接电脑网口，电源红线接正极、黑线接负极。电源规格与接线见 [Livox 快速入门手册](https://dl.djicdn.com/downloads/Livox/Mid-360/QSG/Livox_Mid-360_Quick_Start_Guide_multi.pdf)。

给有线网卡设置与雷达同网段的静态 IPv4 地址。下文以主机 `192.168.1.50/24` 为例；雷达出厂 IP 为 `192.168.1.1XX`，`XX` 对应 SN 最后两位。按实际设备填写变量：

```bash
cd /path/to/HWSentryNav26
IFACE="有线网卡名"
LIDAR_IP="雷达IPv4地址"
HOST_IP="192.168.1.50"
ping -I "$IFACE" -c 3 "$LIDAR_IP"
python3 scripts/start_mid360.py --lidar-ip "$LIDAR_IP" --host-ip "$HOST_IP"
```

脚本将点云和内置 IMU 发送到主机的 `56301/56401` 端口。雷达断电重启后需重新执行；运行时关闭 Livox Viewer、其他 Livox 驱动和录包播放。

## 2. 准备运行环境

首次安装 Python 工具依赖：

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r scripts/requirements-mid360.txt
```

每个终端在仓库根目录执行：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
source .venv/bin/activate
```

点云工具和地图编辑器还需要系统的 `python3-tk` 和 `fonts-noto-cjk`。若使用 Fast DDS 且节点间通信异常，可在所有终端统一启用 UDP 配置：

```bash
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/mid360_driver/config/fastdds_udp.xml"
```

## 3. 采集地图并离线优化

启动雷达、里程计和 RViz；`host_ip` 必须与第 1 步一致：

```bash
ros2 launch mid360_driver mid360_live.launch.py \
  host_ip:=192.168.1.50 mapping:=true rviz:=true
```

入口使用 MID360 内置 IMU，并保存离线优化所需的关键帧。若设备 IMU 数据被 CRC 校验拒绝，可按设备情况添加 `validate_crc:=false`。

RViz 默认显示原始点云。查看里程计时把 Fixed Frame 改为 `odom`，添加 `/small_glim/registered_cloud`（PointCloud2，Best Effort）、`/small_glim/odometry`（Odometry）和 TF。

将雷达放正并固定，记住起点位置和朝向。启动后静止数秒，再缓慢走遍可通行区域并返回起点；观察位姿是否连续、点云是否重合。按 `Ctrl+C` 后等待地图保存完成。

结果位于 `~/mapping/mapping_<时间戳>/`，包含 `mapping.pcd`、`frame_*.pcd` 和 `poses.txt`。把下面的目录名替换为本次采集结果：

```bash
MAP_DIR="$HOME/mapping/mapping_<时间戳>"
ros2 launch offline_mapping_optimizer offline_mapping_optimizer.launch.py \
  data_path:="$MAP_DIR"
```

优化结果为同目录下的 `optimized_map.pcd` 和 `optimized_poses.txt`。后续命令在保留 `MAP_DIR` 的终端中执行。

## 4. 制作导航地图

导航需要同一坐标系下的三维点云 `.pcd` 和地形标注 `.msgpack`。

先运行点云变换工具，打开 `optimized_map.pcd`：

```bash
python3 utils/py/cloud/transform_cloud_manual.py
```

首次复现只平移地图，保持 Roll、Pitch、Yaw 为 `0`。平移 X、Y，使场地位于正坐标范围并留出边界；平移 Z，使地面位于 `z=0`。记下 `tx、ty、tz`，保存为 `$MAP_DIR/mid360_map.pcd`。

关闭变换工具，再运行标注工具：

```bash
python3 utils/py/map/terrain_label_editor.py
```

新建地图时用 `0.05 m/px`，宽、高覆盖场地，例如 `400×300` 像素对应 `20×15 m`。加载 `mid360_map.pcd` 作为背景，标出可通行区域、墙体和障碍物；未采集区域和地图边界也要标成障碍物。新地图默认全为平地，加载点云不会自动生成标注。保存为 `$MAP_DIR/mid360_map.msgpack`。

安装地图：

```bash
mkdir -p map_server/maps odom_localizer/maps
cp "$MAP_DIR/mid360_map.pcd" "$MAP_DIR/mid360_map.msgpack" map_server/maps/
cp "$MAP_DIR/mid360_map.pcd" odom_localizer/maps/
```

修改以下配置，其余参数保留：

| 配置文件 | 参数 | 值 |
| --- | --- | --- |
| `map_server/config/params.yaml` | `global_map.cloud_filename` | `mid360_map.pcd` |
| 同上 | `global_map.blue_nav_map_filename`、`red_nav_map_filename`、`default_nav_map_filename` | 均为 `mid360_map.msgpack` |
| `odom_localizer/config/params.yaml` | `map.cloud_filename` | `mid360_map.pcd` |
| 同上 | `startup.initial_transform.default` | `[tx, ty, tz, 0.0, 0.0, 0.0, 1.0]` |

定位初值是 `map → odom`，格式为 `[x, y, z, qx, qy, qz, qw]`。上面的值适用于只平移地图、从原起点和朝向重新启动；旋转地图或更换起点后需重新计算。本流程没有裁判系统输入，因此使用 `default`。

```bash
colcon build --symlink-install --packages-select map_server odom_localizer \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
```

## 5. 重新定位

把雷达放回建图起点，保持原朝向。若重新上过电，先执行第 1 步。三个终端分别运行：

```bash
# 终端 A：雷达、里程计和 RViz，不保存地图
ros2 launch mid360_driver mid360_live.launch.py \
  host_ip:=192.168.1.50 mapping:=false rviz:=true

# 终端 B：全局定位
ros2 launch odom_localizer odom_localizer.launch.py

# 终端 C：显示先验地图；未接底盘时绕过动态障碍物处理
ros2 run map_server map_server_node --ros-args \
  --params-file map_server/config/params.yaml \
  -p local_map.bypass_dynamic_obstacle:=true
```

等待定位日志出现 `Accepted registration`。RViz 的 Fixed Frame 设为 `map`，用不同颜色显示 `/small_glim/registered_cloud` 和 `/map_server/debug/global_map_cloud`（PointCloud2，Best Effort）。当前点云应与先验地图重合，缓慢移动后仍保持对齐；仅有 `map → odom` 变换不能确认匹配成功。

## 6. 运行导航

先停止第 5 步的全部节点，避免与模拟器发布的里程计和 TF 冲突。在 `utils/py/sim/wheel_leg_lqr_follow_sim.py` 的 `SimConfig` 中，将 `INIT_X`、`INIT_Y` 设为地图内的可通行起点，`INIT_THETA` 设为初始朝向（弧度）。

```bash
bash scripts/start_nav_demo.sh --no-goal
```

脚本按当前地图配置启动地图服务、规划控制、TF、模拟底盘、目标转发和 RViz。用 RViz 的 **Publish Point** 点击可通行目标，观察轨迹和模拟车辆运动；按 `Ctrl+C` 统一停止。更多演示设置见 [DEMO.md](./DEMO.md)。上车运行按 [实车部署说明](./DEPLOY.md) 接入底盘反馈。
