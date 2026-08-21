# ModelManager — 驾驶神经网络模型

Settings → **Models**（不是 Vehicle 车型选择）。

## 工具

| 工具 | 作用 |
|------|------|
| `list_model_bundles` | 列出可选 bundle（ref、display_name、folder） |
| `get_model_manager_status` | 当前激活、下载进度、`ModelManager_DownloadIndex` |
| `select_model_bundle` | `ref=Default` 恢复 stock；否则按 ref 下载并切换 |
| `refresh_model_list` | `ModelManager_LastSyncTime=0` 强制拉取列表 |
| `cancel_model_download` | 清除 `ModelManager_DownloadIndex` |
| `clear_model_cache` | `ModelManager_ClearCache` 清缓存（保留当前模型） |
| `manage_model_favorites` | 增删 `ModelManager_Favs`（分号分隔 ref） |
| `get_model_tune_settings` | `CameraOffset` / `PlanplusControl` |
| `set_model_tune_settings` | 写入模型调参（静止） |

## 相关 Param

- `ModelManager_ActiveBundle` — 当前模型 JSON
- `ModelManager_DownloadIndex` — 后台下载中
- `LagdToggle` / `LaneTurnDesire` — 同页面的横向相关项

## 注意

- 切换 **generation** 不同时，UI 会提示重置标定
- 车型指纹用 `select_car_platform` / `CarPlatformBundle`，勿与本工具混淆
- `select_driving_model` 为历史别名，指向车型而非 NN 模型
