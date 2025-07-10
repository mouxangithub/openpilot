# 车辆数据广播系统修改说明

## 修改目标
基于 `jixiexiaoge/openpilot/opendbc_repo/opendbc/car/mazda/carstate.py` 的实际数据结构，修正车辆数据广播和web显示应用。

## 主要修改文件

### 1. vehicle_data_broadcaster.py
**修改内容：**
- 基于mazda carstate.py的实际字段结构重写数据获取逻辑
- 使用 `getattr()` 安全获取属性，避免属性不存在的错误
- 更新字段名称以匹配实际carState结构：
  - `engineRPM` → `engineRpm`
  - 增加 `gearStep` 字段
  - 更新踏板状态字段名：`Throttle Position` → `Gas Position`
  - 简化门状态：只保留 `doorOpen` 和 `seatbeltUnlatched`
  - 移除不适用的安全系统字段
  - 增加系统状态监控：`lowSpeedAlert`, `steerFaultTemporary`, `steerFaultPermanent`

**新增功能：**
- 改进的错误处理和恢复机制
- 更好的资源管理（socket关闭、线程同步）
- 连续错误监控（最多5次错误后停止）
- 优化的主循环和广播线程管理

### 2. vehicle_monitor_web.py
**修改内容：**
- 更新 `dataConfig` 以匹配新的数据结构
- 新增字段显示：
  - Vehicle Status: 增加 `Gear Step`
  - Cruise Information: 增加 `Standstill`
  - Steering System: `Lane Departure` → `Steering Pressed`, 增加 `Steering EPS Torque`
  - Pedal Status: `Throttle Position` → `Gas Position`
  - Door Status: 简化为 `Any Door Open` 和 `Seatbelt`
  - Light Status: 移除 `Low Beam`（mazda carstate中没有）
  - 新增 System Status 面板显示系统警告和故障

## 技术改进

### 数据安全性
- 所有字段访问都使用 `getattr(object, 'field', default_value)` 模式
- 避免了属性不存在导致的异常
- 增加了空值检查和类型验证

### 错误处理
- 广播线程增加连续错误计数机制
- 主循环使用 `Ratekeeper` 控制频率，避免CPU过度占用
- 更完善的资源清理（socket、线程）

### 兼容性
- 保持与原有UDP广播协议的兼容性
- web界面向后兼容，能处理新旧数据格式
- 保持8080端口广播，1Hz频率不变

## 新增监控功能

### 系统状态监控
- **Low Speed Alert**: 低速警告状态
- **Steer Fault Temporary**: 转向临时故障
- **Steer Fault Permanent**: 转向永久故障

### Mazda特有字段
- **Gear Step**: 变速箱具体档位信息
- **pcmCruiseGap**: 巡航跟车距离设置
- **Standstill**: 车辆静止状态
- **Steering EPS Torque**: 电动助力转向扭矩

## 启动说明
按原计划通过以下方式启动：
```python
PythonProcess("broadcast", "selfdrive.carrot.vehicle_data_broadcaster", only_onroad)
```

服务将自动：
1. 初始化车辆数据获取
2. 启动UDP广播线程
3. 在8080端口广播车辆数据
4. 提供详细的运行日志

## Web监控
通过运行 `vehicle_monitor_web.py` 启动Flask应用，可在浏览器中实时查看车辆数据。界面已更新以显示所有新增的mazda特有字段和系统状态信息。
