# 车型平台 CarPlatformBundle

当自动指纹不可靠时，手动指定 **opendbc platform**。

## 工具

- `list_car_platforms` — 搜索 `car_list.json`（可按 brand/search 过滤）  
- `get_car_platform_bundle` — 当前 manual/auto 状态  
- `select_car_platform` — 设置或清空（`model=""` → 自动识别）  

别名：`select_driving_model`（同一实现，历史命名易与 NN 模型混淆）。

## Param

`CarPlatformBundle` — JSON：`platform`、`name` 等；**删除** Param 恢复自动。

## 注意

- 改平台后通常需重启或重新识别 CarParams  
- NN 驾驶模型用 **model-manager** 技能（`ModelManager_*`）
