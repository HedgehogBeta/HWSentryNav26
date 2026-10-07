"""Live MID360 odometry and mapping with its built-in IMU."""

import glob
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    driver_share = get_package_share_directory("mid360_driver")
    glim_share = get_package_share_directory("small_glim")
    return LaunchDescription([
        DeclareLaunchArgument("host_ip", default_value="192.168.1.50"),
        DeclareLaunchArgument("validate_crc", default_value="true",
                              description="Validate sensor packet CRC; disable for firmware without valid IMU CRC"),
        DeclareLaunchArgument("odometry", default_value="true",
                              description="Start small_glim with the built-in IMU"),
        DeclareLaunchArgument("mapping", default_value="false",
                              description="Save a map when odometry is enabled"),
        DeclareLaunchArgument("output_root", default_value="~/mapping"),
        DeclareLaunchArgument("rviz", default_value="false",
                              description="Open RViz with the raw MID360 point cloud"),
        Node(
            package="mid360_driver",
            executable="mid360_driver_node",
            output="screen",
            parameters=[os.path.join(driver_share, "config", "params.yaml"), {
                "host_ip": LaunchConfiguration("host_ip"),
                "validate_crc": ParameterValue(LaunchConfiguration("validate_crc"), value_type=bool),
                "lidar_frame": "lidar_link",
                "imu_frame": "imu_link",
                "use_sim_time": False,
            }],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            output="screen",
            condition=IfCondition(LaunchConfiguration("rviz")),
            arguments=["-d", os.path.join(driver_share, "config", "mid360.rviz")],
            parameters=[{"use_sim_time": False}],
        ),
        Node(
            package="small_glim",
            executable="small_glim_node",
            output="screen",
            condition=IfCondition(LaunchConfiguration("odometry")),
            parameters=sorted(glob.glob(os.path.join(glim_share, "config", "params_*.yaml"))) + [{
                "use_sim_time": False,
                "node.imu_sub_topic": "/mid360_driver/imu",
                "node.lidar_sub_topic": "/mid360_driver/lidar",
                "node.imu_frame_id": "imu_link",
                "node.lidar_frame_id": "lidar_link",
                # The native driver passes Livox acceleration through in g.
                "node.acc_scale": 9.80665,
                "node.enable_tf_publish": True,
                "node.use_mapping_trigger": False,
                "node.enable_mapping": ParameterValue(LaunchConfiguration("mapping"), value_type=bool),
                "mapping.output_root": LaunchConfiguration("output_root"),
                "mapping.save_raw_mapping_frames": True,
                "sensors.imu_upright": True,
                "sensors.T_lidar_imu": [0.011, 0.02329, -0.04412, 0.0, 0.0, 0.0, 1.0],
                "sensors.imu_acc_saturation_thresh": 39.0,
            }],
        ),
    ])
