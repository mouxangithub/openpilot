# OTA 更新代理自动探测与源选择（git_proxy）

> 2026-10-29 · 覆盖 `openpilot/sunnypilot/system/updated/git_proxy.py`、`openpilot/system/updated/updated.py`、`openpilot/common/time_helpers.py`

## 1. 背景与问题

- 设备在国内网络下 GitHub 官源经常不可达，OTA 更新（`updated` 守护进程）直接 fetch 失败。
- 现有 read-through 代理（`gh-proxy.com`、`cdn.gh-proxy.org` 等）质量参差：有的限流大仓库、有的间歇超时、有的随时下线。
- 设备 C3 无 RTC 电池，断电后时钟错乱 → TLS 证书校验失败（"certificate is not yet valid"），连校时请求本身都会失败（自举悖论）。

设计目标：**官源优先、能用官源不用代理；官源不通时自动实测多个代理选最快；主仓和所有子仓一起切；单源 fetch 中途死掉自动换下一个；附带解决时钟自举问题。**

## 2. 整体流程

```
updated 主循环（only_offroad）
  ├─ sync_system_time_http()      ← 先修时钟，否则后续 git HTTPS 全挂
  ├─ system_time_valid() 门控
  └─ check_for_update()
       ├─ ensure_git_source()     ← 探测 + 排序 + 应用最优源（每进程一次）
       │    ├─ _origin_url()      ← 剥掉旧代理前缀，还原真 upstream
       │    ├─ _extra_proxy_prefixes()  ← 读 /data/params/d/GitProxyPrefixes
       │    ├─ git_proxy.measure_and_rank()  ← 真实 git ls-remote 并发探测
       │    └─ _apply_prefix(best)      ← 主仓 origin + 全部子仓双处改写
       ├─ target_branch / _migrate_branch()   ← SP_BRANCH_MIGRATIONS + 远端存在性回退
       └─ fetch_update_with_retry()   ← 按延迟排序逐源 fetch，失败换下一个
```

## 3. 探测设计（git_proxy.py）

### 3.1 为什么是真实 `git ls-remote` 而不是 HTTP HEAD

实测教训：`cdn.gh-proxy.org` 对 HEAD 返回 301（看似健康）但 git 的 TLS 握手失败；`ghfast.top` 反之。HTTP 探测会选出"根本 fetch 不了"的源。`git ls-remote --heads` 是只读操作，能完整走一遍 git 传输栈，且要求返回非空 refs——防止 captive portal 返回 200 被误判为健康。

### 3.2 采样与预算

| 常量 | 值 | 含义 |
|---|---|---|
| `PROBE_SAMPLES` | 3 | 每源采样次数，取成功样本的中位数 |
| `PROBE_TIMEOUT_S` | 12 | 单次超时 |
| `PROBE_BUDGET_S` | 45 | 总预算（deadline），防止死源拖垮全局 |
| `MAX_PROBE_WORKERS` | 7 | 并发探测（源之间独立，串行会让死源的 timeout 叠加到后面每个候选） |
| `MAX_ACCEPTABLE_MS` | 15000 | 中位数超过此值视为不可用而非"慢" |

判活规则（`probe_source`）：
- **至少成功 1 次即健康**，中位数只取成功样本——单次超时不能把一个 2s 的好源判成 12s 慢链路（实测 cdn 首次 12s 超时、二次 1.8s 成功）。
- 失败 2 次提前放弃；成功 2 次提前结束——重试死源只会烧掉其余候选的预算。

### 3.3 排序与回退

`measure_and_rank()` 返回 `(ProbeResult, prefix)` 列表，按中位延迟升序；**稳定排序 + 官源永远排候选第一位 → 平局时官源赢**，能用的 github 永远不被等速代理顶掉。

排序列表整体缓存到 `_source_prefixes`：探测健康 ≠ fetch 能撑到底（限流代理对 ls-remote 表现正常、大传输中途死），所以 `fetch_update_with_retry()` 沿列表逐源尝试（每次 fetch 前 `_apply_prefix` 重写 remotes），全部失败才抛最后一个错误。

### 3.4 子仓双处改写（最易踩坑）

git 读子仓 URL 有**两个位置**，缺一不可：

1. 子仓自己的 `remote.origin.url` —— 已克隆子仓 fetch 用它；
2. 父仓 `.git/config` 的 `submodule.<name>.url` —— `git submodule update --init` 克隆新子仓用它。

`apply_source()` / `apply_submodules()` 两处都写；`restore_source()` 两处都还原。三个陷阱：

- **section 名 ≠ path**：opendbc 的 section 是 `opendbc`，path 是 `opendbc_repo`。`submodule.<name>.url` 的 `<name>` 用的是 section 名，按 path 推导会写错键。
- **`git submodule sync` 会冲掉代理**：它把 `.gitmodules` 的官源 URL 拷回 `submodule.<name>.url`（实测确认）。所以代理必须写在任何 sync **之后**。
- 子仓列表以 `.gitmodules` 为准（`git submodule foreach` 只访问已注册已克隆的，漏掉还没 fetch 的）；`.git/config` 里有但 `.gitmodules` 没有的子仓也单独补写 origin。

主仓的非 origin remote（cnb/sunnypilot/zp 等开发者自己的镜像）**不动**——重写它们会静默劫持 push。

## 4. 用户自定义代理：GitProxyPrefixes

内置 6 个代理固化在发布版里；用户网络下可能有更快的代理，不该等发版。`GitProxyPrefixes` 让用户自行追加。

### 4.1 格式与追加方法

- 值 = 一个或多个代理前缀，**逗号分隔**；每项必须是 `http(s)` 开头的 origin，缺尾斜杠自动补（前缀是原样拼接的，`https://p.com` 拼出来是 `https://p.comhttps://github.com/...`，没斜杠就废了）。
- key **故意不注册**进 `params_keys.h`：未注册 key 会让 `Params.get/put` 抛 `UnknownKeyName`，而把它绑到重编 libparams_c.so 意味着没重编的设备整个源选择直接炸。所以直读文件：

```bash
# 追加一个（保留已有）
old=$(cat /data/params/d/GitProxyPrefixes 2>/dev/null)
echo "${old:+$old,}https://my-proxy.example.com/" | sudo tee /data/params/d/GitProxyPrefixes

# 一次写多个
echo "https://a.example.com/,https://b.example.com/" | sudo tee /data/params/d/GitProxyPrefixes

# 查看
cat /data/params/d/GitProxyPrefixes

# 清空（回到只用内置 6 个）
sudo rm /data/params/d/GitProxyPrefixes
```

### 4.2 解析规则（`updated.py:_extra_proxy_prefixes`）

- 文件不存在 / 读失败 → 返回空元组（功能静默降级，不影响无自定义代理的设备）。
- 逐项：`http` 开头才收；补尾斜杠；**与内置 `PROXY_PREFIXES` 重复的丢弃**（内置的已在候选里）；坏项直接跳过不报错。
- 自定义代理排在**内置之前**探测（`build_candidates`）：用户特意加的，内置列表不可能知道他的理由。

### 4.3 生效时机

`ensure_git_source()` 每个进程只跑一次（`_source_applied` 缓存），改完参数需要重启 updated 生效：

```bash
sudo systemctl restart comma    # 立即生效
# 或等一次行车循环自然重启（updated 是 only_onroad 进程）
```

## 5. HTTP 校时（time_helpers.py）

自举悖论：时钟错乱 → HTTPS 证书校验失败 → 校时请求本身失败 → 时钟永远修不好。解法：

- 端点全用 **HTTP（80 端口）**：`baidu.com` / `aliyun.com` / `qq.com`，国内不被墙且无需 TLS；
- **不跟随重定向**的 opener：301 响应也带 `Date` 头，够用；
- 多端点候选取"合理候选"的**中位数**（`pick_http_time`），单个端点时钟漂移不影响；
- 时钟只在**向前拨且漂移 > 1 天**时才动——向后拨会破坏 monotonic 假设和日志因果；
- `set_system_time` 用 `date -s`，失败 try/except 不抛（校时失败不该拖死更新主循环）。

主循环顺序：`sync_system_time_http()` → `system_time_valid()` 门控 → 才进入 git 操作。

## 6. 分支迁移（SP_BRANCH_MIGRATIONS）

`target_branch`（请求）与 `requested_branch`（持久化）分离：迁移表只在内存里映射 target，`set_params` 写回的是 requested——否则迁移结果污染参数、用户再也回不去。迁移前查**远端分支存在性**，远端没有的（如 fork 里无 master-tici）回退到请求分支，防止 switch 死循环。分支列表索引用 `.get()` 防缺失分支 KeyError。

## 7. 测试与验证

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `sunnypilot/system/updated/tests/test_git_proxy.py` | 28 | 探测判活/预算/排序/平局官源优先/子仓双处改写/section 名陷阱/sync 冲掉代理 |
| `common/tests/test_time_helpers.py` | 14 | HTTP 校时/中位数/只向前拨/漂移阈值/注入 now |
| `sunnypilot/system/updated/tests/test_sp_branch_migrations.py` | 38 | 迁移表/远端回退/参数写回分离 |

- swaglog stub 采用 "try import 真模块，失败才 stub"，避免污染同进程其他测试。
- 设备实测：80 个单测全绿；重启后 updated idle、failed=0、时钟 valid；HTTP 校时 bogus 时钟恢复漂移 0s。
- 设备跑法：`cd /data/openpilot && PYTHONPATH=/data/openpilot:/data/openpilot/openpilot:/data/.pydeps /usr/local/venv/bin/python3 -m unittest ...`，**必核 skip=0**。

## 8. 残余风险与限制

- **代理限流大仓库**：ls-remote 探测无法预知，靠 `fetch_update_with_retry` 事后换源兜底；如果所有源都限流，只能等（这正是预算/重试设计成"逐源"而非"单源 N 次"的原因）。
- 代理是第三方服务，理论上可注入恶意数据；git 的 commit SHA 校验（fetch 按目标 commit 核对）是最终防线。
- 校时只向前拨：时钟被人为拨快超 1 天的情况不处理（避免破坏系统假设）。
- 自定义代理格式错误会被静默丢弃，无 UI 提示（key 未注册的代价，换来零重编部署）。
