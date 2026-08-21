# 代码发布（PR/MR）

op助手支持将本地改动 **commit → push → 创建 PR/MR**，并区分 **op助手仓** 与 **项目仓** 两类目标。

## 两类发布

| 类型 | 单元 | 默认目标 |
|------|------|----------|
| **A 类** | `assistant`（op助手 / ai） | 固定 **`mouxangithub/ai`** |
| **B 类** | `openpilot`、`opendbc`、`panda` 等 | **当前 git remote** 或 **用户 fork**（不写死 mouxangithub） |

仅有一个 openpilot 主仓、没有独立 opendbc/panda 子模块时完全正常。

## 发布模式（B 类）

- **`current_remote`**：读取 `git remote get-url origin`，PR 开在用户当前使用的仓库（GitHub / Gitee 均可）。
- **`user_fork`**：推送到配置的 fork URL，并在该仓创建 MR。

## 配置

**设置 → 开发 → 代码发布**：

- **GitHub PAT**：`repo` 权限（与 Runner token 不同）
- **Gitee 私人令牌**
- **项目仓默认模式**：当前 remote / 我的 fork
- **openpilot fork URL**（可选）

也可通过工具：

- `set_forge_token(forge=github|gitee, token=..., confirm=true)`
- `discover_publish_units()`
- `publish_changes(unit_id=..., target_mode=..., confirm=false)` 预览

## 工具

| 工具 | 说明 |
|------|------|
| `publish_changes` | 统一发布入口 |
| `git_publish_pull_request` | 兼容旧名，内部调用 `publish_changes` |
| `discover_publish_units` | 扫描可发布单元与 dirty 文件 |
| `forge_auth_status` | 检查 Token |
| `set_forge_token` | 保存 Token |

## API

- `GET /api/ai/publish` — 状态 + 单元列表
- `GET /api/ai/publish?view=units&dirty=1` — 仅有改动的单元
- `POST /api/ai/publish` — `operation`: `save_settings` | `set_forge_token` | `verify_forge` | `publish`

## 安全

- 离路 + `confirm=true` 才执行写操作
- 保护分支自动创建 `ai/*` 分支
- Token 存于 `/data/ai/config.json`，不出现在日志与 API 返回值中
