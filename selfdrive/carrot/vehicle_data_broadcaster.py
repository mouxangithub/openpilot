#!/usr/bin/env python3
"""
车辆数据广播服务
参考carrot_man.py的UDP广播机制和fleet_manager.py的车辆数据获取方式
在8080端口进行UDP广播，每秒1次
"""

import json
import socket
import time
import threading
import traceback
from datetime import datetime

import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.opendbc_repo.opendbc.car.interfaces import CarInterfaceBase
from openpilot.opendbc_repo.opendbc.car.values import PLATFORMS


class VehicleDataBroadcaster:
    def __init__(self):
        print("VehicleDataBroadcaster 初始化...")

        try:
            self.params = Params()
            self.sm = messaging.SubMaster([
                'carState', 'deviceState', 'controlsState',
                'longitudinalPlan', 'selfdriveState', 'liveLocationKalman'
            ])

            # UDP广播配置
            self.broadcast_port = 8080
            self.broadcast_ip = "255.255.255.255"  # 广播地址

            # 运行状态
            self.is_running = True
            self.broadcast_thread = None

            # 启动广播线程
            self._start_broadcast_thread()

            print("VehicleDataBroadcaster 初始化完成")

        except Exception as e:
            print(f"VehicleDataBroadcaster 初始化失败: {e}")
            traceback.print_exc()
            raise

    def _start_broadcast_thread(self):
        """启动广播线程"""
        try:
            self.broadcast_thread = threading.Thread(target=self.broadcast_vehicle_data)
            self.broadcast_thread.daemon = True
            self.broadcast_thread.start()
            print("广播线程已启动")
        except Exception as e:
            print(f"启动广播线程失败: {e}")
            raise

    def get_vehicle_status_data(self):
        """获取车辆状态数据 - 参考fleet_manager.py的carinfo实现"""
        try:
            # 更新消息
            self.sm.update()

            # 获取车辆基本信息
            try:
                car_name = self.params.get("CarName", encoding='utf8')
                if car_name and car_name in PLATFORMS:
                    platform = PLATFORMS[car_name]
                    car_fingerprint = platform.config.platform_str
                    car_specs = platform.config.specs
                else:
                    car_name = "Unknown Model"
                    car_fingerprint = "Unknown Fingerprint"
                    car_specs = None
            except Exception as e:
                print(f"Failed to get vehicle basic info: {e}")
                car_name = "Unknown Model"
                car_fingerprint = "Unknown Fingerprint"
                car_specs = None

            # 检查是否在路上
            is_onroad = self.params.get_bool("IsOnroad")

            # 构建基础数据结构
            vehicle_data = {
                "timestamp": datetime.now().isoformat(),
                "is_onroad": is_onroad,
                "status": "vehicle_not_started"
            }

            # 获取车辆状态信息 - 完全参考fleet_manager.py的实现
            if self.sm.alive['carState']:
                CS = self.sm['carState']

                # 基本状态判断
                is_car_started = CS.vEgo > 0.1
                is_car_engaged = CS.cruiseState.enabled

                # 更新状态
                if is_car_started:
                    vehicle_data["status"] = "vehicle_started"
                else:
                    vehicle_data["status"] = "vehicle_stopped"

                # 构建基础信息 - 与参考代码完全一致
                vehicle_data["Vehicle Status"] = {
                    "Running Status": "Moving" if is_car_started else "Stopped",
                    "Cruise System": "Enabled" if is_car_engaged else "Disabled",
                    "Current Speed": f"{CS.vEgo * 3.6:.1f} km/h",
                    "Engine RPM": f"{CS.engineRPM:.0f} RPM" if hasattr(CS, 'engineRPM') and CS.engineRPM is not None and CS.engineRPM > 0 else "Unknown",
                    "Gear Position": str(CS.gearShifter) if hasattr(CS, 'gearShifter') and CS.gearShifter is not None else "Unknown"
                }

                vehicle_data["Basic Information"] = {
                    "Car Model": car_name,
                    "Fingerprint": str(car_fingerprint),
                    "Weight": f"{car_specs.mass:.0f} kg" if car_specs and hasattr(car_specs, 'mass') else "Unknown",
                    "Wheelbase": f"{car_specs.wheelbase:.3f} m" if car_specs and hasattr(car_specs, 'wheelbase') else "Unknown",
                    "Steering Ratio": f"{car_specs.steerRatio:.1f}" if car_specs and hasattr(car_specs, 'steerRatio') else "Unknown"
                }

                # 巡航信息 - 即使车辆未启动也显示基本设置
                vehicle_data["Cruise Information"] = {
                    "Cruise Status": "On" if CS.cruiseState.enabled else "Off",
                    "Adaptive Cruise": "On" if CS.cruiseState.available else "Off",
                    "Set Speed": f"{CS.cruiseState.speed * 3.6:.1f} km/h" if CS.cruiseState.speed > 0 else "Not Set",
                    "Following Distance": str(CS.pcmCruiseGap) if hasattr(CS, 'pcmCruiseGap') and CS.pcmCruiseGap > 0 else (str(CS.cruiseState.followDistance) if hasattr(CS.cruiseState, 'followDistance') and CS.cruiseState.followDistance is not None else "Unknown")
                }

                # 详细信息 - 与参考代码完全一致
                if is_car_started or is_car_engaged:
                    vehicle_data.update({
                        "Wheel Speeds": {
                            "Front Left": f"{CS.wheelSpeeds.fl * 3.6:.1f} km/h",
                            "Front Right": f"{CS.wheelSpeeds.fr * 3.6:.1f} km/h",
                            "Rear Left": f"{CS.wheelSpeeds.rl * 3.6:.1f} km/h",
                            "Rear Right": f"{CS.wheelSpeeds.rr * 3.6:.1f} km/h"
                        },
                        "Steering System": {
                            "Steering Angle": f"{CS.steeringAngleDeg:.1f}°",
                            "Steering Torque": f"{CS.steeringTorque:.1f} Nm",
                            "Steering Rate": f"{CS.steeringRateDeg:.1f}°/s",
                            "Lane Departure": "Yes" if CS.leftBlinker or CS.rightBlinker else "No"
                        },
                        "Pedal Status": {
                            "Throttle Position": f"{CS.gas * 100:.1f}%",
                            "Brake Pressure": f"{CS.brake * 100:.1f}%",
                            "Gas Pedal": "Pressed" if CS.gasPressed else "Released",
                            "Brake Pedal": "Pressed" if CS.brakePressed else "Released"
                        },
                        "Safety Systems": {
                            "ESP Status": "Active" if CS.espDisabled else "Normal",
                            "ABS Status": "Active" if hasattr(CS, 'absActive') and CS.absActive else "Normal",
                            "Traction Control": "Active" if hasattr(CS, 'tcsActive') and CS.tcsActive else "Normal",
                            "Collision Warning": "Warning" if hasattr(CS, 'collisionWarning') and CS.collisionWarning else "Normal"
                        },
                        "Door Status": {
                            "Driver Door": "Open" if CS.doorOpen else "Closed",
                            "Passenger Door": "Open" if hasattr(CS, 'passengerDoorOpen') and CS.passengerDoorOpen else "Closed",
                            "Trunk": "Open" if hasattr(CS, 'trunkOpen') and CS.trunkOpen else "Closed",
                            "Hood": "Open" if hasattr(CS, 'hoodOpen') and CS.hoodOpen else "Closed",
                            "Seatbelt": "Unbuckled" if CS.seatbeltUnlatched else "Buckled"
                        },
                        "Light Status": {
                            "Left Turn Signal": "On" if CS.leftBlinker else "Off",
                            "Right Turn Signal": "On" if CS.rightBlinker else "Off",
                            "High Beam": "On" if CS.genericToggle else "Off",
                            "Low Beam": "On" if hasattr(CS, 'lowBeamOn') and CS.lowBeamOn else "Off"
                        },
                        "Blind Spot Monitor": {
                            "Left Side": "Vehicle Detected" if CS.leftBlindspot else "Clear",
                            "Right Side": "Vehicle Detected" if CS.rightBlindspot else "Clear"
                        }
                    })

                    # 添加可选的其他信息 - 与参考代码完全一致
                    other_info = {}
                    if hasattr(CS, 'outsideTemp'):
                        other_info["Outside Temperature"] = f"{CS.outsideTemp:.1f}°C"
                    if hasattr(CS, 'fuelGauge'):
                        other_info["Range"] = f"{CS.fuelGauge:.1f}km"
                    if hasattr(CS, 'odometer'):
                        other_info["Odometer"] = f"{CS.odometer:.1f}km"
                    if hasattr(CS, 'instantFuelConsumption'):
                        other_info["Instant Fuel Consumption"] = f"{CS.instantFuelConsumption:.1f}L/100km"

                    if other_info:
                        vehicle_data["Other Information"] = other_info

            else:
                print("调试: carState 不可用")
                vehicle_data["message"] = "车辆状态数据不可用"

            # 获取自驾系统状态
            if self.sm.alive['selfdriveState']:
                selfdrive = self.sm['selfdriveState']
                vehicle_data["selfdrive_status"] = {
                    "active": selfdrive.active,
                    "state": str(selfdrive.state)
                }

            # 获取设备状态
            if self.sm.alive['deviceState']:
                device = self.sm['deviceState']
                device_status = {
                    "network_type": str(device.networkType),
                    "memory_usage_percent": device.memoryUsagePercent,
                    "free_space_percent": device.freeSpacePercent,
                    "thermal_status": str(device.thermalStatus)
                }

                # 添加可用的温度信息
                if hasattr(device, 'cpuTempC') and len(device.cpuTempC) > 0:
                    device_status["cpu_temp_c"] = round(device.cpuTempC[0], 1)
                if hasattr(device, 'maxTempC'):
                    device_status["max_temp_c"] = round(device.maxTempC, 1)

                vehicle_data["device_status"] = device_status

            return vehicle_data

        except Exception as e:
            print(f"获取车辆状态数据时出错: {e}")
            traceback.print_exc()
            return {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error_message": str(e)
            }

    def broadcast_vehicle_data(self):
        """广播车辆数据"""
        sock = None
        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            print(f"开始在端口 {self.broadcast_port} 广播车辆数据...")

        except Exception as e:
            print(f"创建UDP socket失败: {e}")
            return

        rk = Ratekeeper(1.0, print_delay_threshold=None)  # 1Hz

        while self.is_running:
            try:
                # 获取车辆数据
                vehicle_data = self.get_vehicle_status_data()

                # 转换为JSON
                json_data = json.dumps(vehicle_data, ensure_ascii=False, indent=None)

                # UDP广播
                sock.sendto(json_data.encode('utf-8'), (self.broadcast_ip, self.broadcast_port))

                # 获取当前速度用于显示
                current_speed = "N/A"
                if "Vehicle Status" in vehicle_data and isinstance(vehicle_data["Vehicle Status"], dict):
                    current_speed = vehicle_data["Vehicle Status"].get("Current Speed", "N/A")

                print(f"广播数据: 状态={vehicle_data.get('status', 'unknown')}, "
                      f"速度={current_speed}")

                # 重置错误计数
                consecutive_errors = 0

                rk.keep_time()

            except Exception as e:
                consecutive_errors += 1
                print(f"广播数据时出错 (第{consecutive_errors}次): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    print(f"连续错误达到{max_consecutive_errors}次，停止广播")
                    break

                # 短暂等待后重试
                time.sleep(1)

        # 清理资源
        if sock:
            try:
                sock.close()
                print("UDP socket已关闭")
            except:
                pass

        print("广播线程已退出")

    def stop(self):
        """停止广播"""
        print("正在停止车辆数据广播服务...")
        self.is_running = False

        # 等待广播线程结束
        if self.broadcast_thread and self.broadcast_thread.is_alive():
            print("等待广播线程结束...")
            self.broadcast_thread.join(timeout=3.0)

            if self.broadcast_thread.is_alive():
                print("警告: 广播线程未能在超时时间内结束")
            else:
                print("广播线程已安全结束")

        print("车辆数据广播服务已停止")


def main():
    """主函数 - 优化为PythonProcess启动"""
    broadcaster = None

    try:
        print("启动车辆数据广播服务...")
        broadcaster = VehicleDataBroadcaster()

        # 使用Ratekeeper控制主循环，避免过度占用CPU
        rk = Ratekeeper(10.0, print_delay_threshold=None)  # 10Hz检查频率

        print("车辆数据广播服务已启动，等待运行...")

        # 主循环 - 持续运行直到收到停止信号
        while broadcaster.is_running:
            rk.keep_time()

    except KeyboardInterrupt:
        print("收到键盘中断信号...")
    except Exception as e:
        print(f"主程序运行出错: {e}")
        traceback.print_exc()
    finally:
        # 确保资源清理
        if broadcaster:
            print("正在停止车辆数据广播服务...")
            broadcaster.stop()
            # 等待广播线程结束
            if broadcaster.broadcast_thread.is_alive():
                broadcaster.broadcast_thread.join(timeout=2.0)
        print("车辆数据广播服务已完全停止")


if __name__ == "__main__":
    main()
