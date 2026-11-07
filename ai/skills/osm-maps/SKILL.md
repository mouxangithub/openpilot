# OSM 离线地图

Settings → **OSM**（mapd 离线地图，供 SmartCruiseControlMap 等使用）。

## 工作流

1. `get_osm_status` — 已选国家/州、下载进度、磁盘占用  
2. `list_osm_regions` — `Country` 或 `State`（美国）  
3. `select_osm_region` — 设置 `OsmLocationName` / `OsmStateName`（不自动下载）  
4. `trigger_osm_download` — `OsmDbUpdatesCheck=true`（需 offroad + WiFi）  
5. 轮询 `get_osm_status` 直到完成  
6. `cancel_osm_download` — 取消进行中的下载（尽力清除 shm 队列）  
7. `delete_osm_maps` — 清空离线数据（需 confirm）

## Param 摘要

- `OsmLocationName` / `OsmLocationTitle` — 国家  
- `OsmStateName` / `OsmStateTitle` — 美国州（`All` ≈ 6GB）  
- `OsmDbUpdatesCheck` — 触发下载  
- `MapdVersion` — mapd 版本（只读）

下载进度在 `/dev/shm/params` 的 `OSMDownloadProgress`（由 mapd 写入）。
