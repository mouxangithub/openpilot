# 车型与模型切换

本 fork 有 **两个独立概念**：

## 1. 车型平台（指纹）

- UI：Settings → Vehicle  
- Param：`CarPlatformBundle`  
- 工具：`list_car_platforms`、`select_car_platform`（别名 `select_driving_model`）

## 2. 驾驶神经网络模型

- UI：Settings → Models  
- Param：`ModelManager_ActiveBundle` 等  
- 工具：`list_model_bundles`、`select_model_bundle`

勿将「换模型」与「换车型」混淆。

## 验证

`read_params` 核对写入；`get_build_info` 看软件版本；换 NN 模型后观察 `get_model_manager_status` 下载进度。
