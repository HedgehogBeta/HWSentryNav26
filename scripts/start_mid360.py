#!/usr/bin/env python3
"""Use installed Livox SDK2 to route a single MID360 to the native ROS driver.

SDK headers: https://github.com/Livox-SDK/Livox-SDK2/tree/master/include
The SDK briefly receives on 56311/56411; the final destinations are 56301/56401.
Run again after power cycling the lidar. Close Livox Viewer / other SDK drivers first.
"""

import argparse
import ctypes as ct
import ipaddress
import json
import socket
import tempfile
import threading
from pathlib import Path


class LidarInfo(ct.Structure):
    _pack_ = 1
    _fields_ = [("dev_type", ct.c_uint8), ("sn", ct.c_char * 16), ("lidar_ip", ct.c_char * 16)]


class Response(ct.Structure):
    _pack_ = 1
    _fields_ = [("ret_code", ct.c_uint8), ("error_key", ct.c_uint16)]


class HostIPInfo(ct.Structure):
    _pack_ = 1
    _fields_ = [("host_ip_addr", ct.c_char * 16), ("host_port", ct.c_uint16), ("lidar_port", ct.c_uint16)]


InfoCallback = ct.CFUNCTYPE(None, ct.c_uint32, ct.POINTER(LidarInfo), ct.c_void_p)
ControlCallback = ct.CFUNCTYPE(None, ct.c_int32, ct.c_uint32, ct.POINTER(Response), ct.c_void_p)


def ipv4(value):
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def start(args):
    # Fail clearly before entering SDK threads if the wired IP is not active.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind((args.host_ip, 0))
    sdk = ct.CDLL(str(args.sdk_lib))
    sdk.LivoxLidarSdkInit.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_void_p]
    sdk.LivoxLidarSdkInit.restype = ct.c_bool
    sdk.LivoxLidarSdkUninit.argtypes = []
    sdk.LivoxLidarSdkUninit.restype = None
    sdk.SetLivoxLidarInfoChangeCallback.argtypes = [InfoCallback, ct.c_void_p]
    sdk.SetLivoxLidarInfoChangeCallback.restype = None
    sdk.DisableLivoxSdkConsoleLogger.argtypes = []
    sdk.DisableLivoxSdkConsoleLogger.restype = None
    commands = {
        "SetLivoxLidarPointDataHostIPCfg": [ct.POINTER(HostIPInfo)],
        "SetLivoxLidarImuDataHostIPCfg": [ct.POINTER(HostIPInfo)],
        "SetLivoxLidarPclDataType": [ct.c_int],
        "SetLivoxLidarWorkMode": [ct.c_int],
        "EnableLivoxLidarImuData": [],
    }
    for name, parameters in commands.items():
        function = getattr(sdk, name)
        function.argtypes = [ct.c_uint32, *parameters, ControlCallback, ct.c_void_p]
        function.restype = ct.c_int32

    detected = threading.Event()
    acknowledged = threading.Event()
    device = {}
    result = []

    @InfoCallback
    def on_info(handle, info, _):
        if not info:
            return
        data = info.contents
        if data.dev_type == 9 and data.lidar_ip.decode() == args.lidar_ip:
            device.update(handle=handle, sn=data.sn.decode())
            detected.set()

    @ControlCallback
    def on_control(status, handle, response, _):
        if handle != device.get("handle"):
            return
        result[:] = [status, response.contents.ret_code if response else None,
                     response.contents.error_key if response else None]
        acknowledged.set()

    net_info = {
        "lidar_ip": [args.lidar_ip], "host_ip": args.host_ip,
        "cmd_data_port": 56101, "push_msg_port": 56201,
        "point_data_port": 56311, "imu_data_port": 56411, "log_data_port": 56501,
    }
    config = {
        "master_sdk": True, "lidar_log_enable": False,
        "lidar_log_cache_size_MB": 0, "lidar_log_path": tempfile.gettempdir(),
        "MID360": {
            "lidar_net_info": {"cmd_data_port": 56100, "push_msg_port": 56200,
                               "point_data_port": 56300, "imu_data_port": 56400, "log_data_port": 56500},
            "host_net_info": [net_info],
        },
    }
    with tempfile.TemporaryDirectory(prefix="mid360-start-") as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(json.dumps(config))
        if not args.verbose_sdk:
            sdk.DisableLivoxSdkConsoleLogger()
        sdk.SetLivoxLidarInfoChangeCallback(on_info, None)
        try:
            if not sdk.LivoxLidarSdkInit(str(config_path).encode(), b"", None):
                raise RuntimeError("Livox SDK2 初始化失败；检查本机 IP、端口占用及 SDK 安装。")
            print(f"等待 MID360 {args.lidar_ip}（最多 {args.timeout:g} 秒）…", flush=True)
            if not detected.wait(args.timeout):
                raise RuntimeError("未发现指定雷达；检查供电、网线、SN/IP、防火墙及 VPN 路由。")
            print(f"已连接 SN={device['sn']}，IP={args.lidar_ip}", flush=True)

            point_info = HostIPInfo(args.host_ip.encode(), 56301, 56300)
            imu_info = HostIPInfo(args.host_ip.encode(), 56401, 56400)
            steps = [
                ("点云目标", "SetLivoxLidarPointDataHostIPCfg", [ct.byref(point_info)]),
                ("IMU 目标", "SetLivoxLidarImuDataHostIPCfg", [ct.byref(imu_info)]),
                ("高精度直角坐标点云", "SetLivoxLidarPclDataType", [1]),
                ("正常工作模式", "SetLivoxLidarWorkMode", [1]),
                ("开启内置 IMU", "EnableLivoxLidarImuData", []),
            ]
            for label, name, parameters in steps:
                acknowledged.clear()
                status = getattr(sdk, name)(device["handle"], *parameters, on_control, None)
                if status != 0:
                    raise RuntimeError(f"{label}发送失败：SDK status={status}")
                if not acknowledged.wait(args.timeout):
                    raise RuntimeError(f"{label}未收到 ACK；请检查连接后重新运行。")
                if result != [0, 0, 0]:
                    raise RuntimeError(f"{label}被拒绝：status/ret_code/error_key={result}")
                print(f"{label}：成功", flush=True)
            print(f"配置完成：点云 → {args.host_ip}:56301，IMU → {args.host_ip}:56401。\n"
                  f"现在运行 ros2 launch mid360_driver mid360_live.launch.py host_ip:={args.host_ip}。", flush=True)
        finally:
            sdk.LivoxLidarSdkUninit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lidar-ip", required=True, type=ipv4,
                        help="出厂 IP 为 192.168.1.1XX，XX 是 SN 最后两位")
    parser.add_argument("--host-ip", default="192.168.1.50", type=ipv4)
    parser.add_argument("--sdk-lib", type=Path, default=Path("/usr/local/lib/liblivox_lidar_sdk_shared.so"))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--verbose-sdk", action="store_true", help="显示官方 SDK 的详细日志")
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout != args.timeout or args.timeout == float("inf"):
        parser.error("--timeout 必须是有限正数")
    if args.lidar_ip == args.host_ip:
        parser.error("雷达 IP 和电脑 IP 不能相同")
    try:
        start(args)
    except (OSError, RuntimeError, AttributeError) as error:
        parser.exit(1, f"启动失败：{error}\n请检查有线网卡配置及 --host-ip、--lidar-ip。\n")


if __name__ == "__main__":
    main()
