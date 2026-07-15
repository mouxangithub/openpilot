# 安装与集成

> 仓库：https://github.com/mouxangithub/ai  
> 路径：`<openpilot>/ai`

## 一键安装

**Comma 设备（默认 `/data/openpilot`）：**

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

**PC：**

```bash
export OPENPILOT_ROOT=/path/to/your/openpilot
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

## 安装脚本做什么

| 步骤 | 说明 |
|------|------|
| 1. 检测 `ai/` | 见下文「已有 ai 目录」 |
| 2. Git | 克隆或 `git pull` 到 `$OPENPILOT_ROOT/ai` |
| 3. **自动改写 `params_keys.h`** | 从 `ai/common/params.py` 补齐缺失的 `ai_*` 键（写前 `.bak.时间戳` 备份） |
| 4. **自动改写 `launch_chffrplus.sh`** | 若无 `start_op_assistant`，注入启动 `ai.aid` 的函数与看门狗 |
| 5. 编译 | 尝试 `scons common/params_pyx.so` 或 `system/manager/build.py` |

以上第 3–5 步由 `install/integrate_openpilot.py` 执行，**每次安装/更新后都会跑一遍**。

预编译 fork 若无 SConstruct：尽量复用已有 `params_pyx.so`；若新增了 Param 键，需在可编译环境重建。

## 已有 `ai/` 目录时怎么办

| 情况 | 安装脚本行为 |
|------|----------------|
| **不存在** `ai/` | 全新 `git clone` |
| **存在且为 git 仓库**（`ai/.git`） | 自动 `git pull` 更新，不删你的本地数据 |
| **存在但非 git**（例如主仓自带的拷贝） | 整目录备份为 `ai.bak.<时间戳>`，再重新 clone |

因此重复执行一键安装是安全的：git 安装会更新代码并重新 integrate；非 git 会先备份再覆盖。

## 更新

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/update.sh | bash
```

或 Web：**设置 → 开发 → op助手 版本 → 立即更新**（`git pull` + integrate）。

## 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/uninstall.sh | bash
# 或
bash /data/openpilot/ai/install/uninstall.sh
```

| 选项 | 作用 |
|------|------|
| （默认） | 停止 `ai.aid`，删除 `ai/` 目录 |
| `--restore-integrate` | 额外尝试用最新 `.bak` 恢复 `params_keys.h` / `launch_chffrplus.sh` |
| `--keep-local-data` | 删除前把 fork 分析/草稿备份到 `<openpilot>/.op-ai-local-backup/` |
| `--yes` | 跳过确认 |

**不会自动删除：** Params 里的 `ai_*` 配置（重装后可继续用）。

## Fork 分析与草稿存在哪？会影响 `git pull` 吗？

AI 分析 fork 后的文件都在 **`ai/` 目录内**，且已加入 `.gitignore`，**不会进入 git 仓库**：

| 路径 | 内容 |
|------|------|
| `ai/data/fork_analysis/latest.json` | AI 分析报告缓存（随 openpilot git commit 失效） |
| `ai/data/fork_drafts/<slug>/` | 技能/工具说明草稿（`FORK_SKILL.md`、`tools_notes.md`、`manifest.json`） |

**对更新的影响：**

- `git pull` 更新 op助手 **不会覆盖** 上述目录（未跟踪文件）。
- 更新 **不会删除** 草稿；仅当整目录 `rm -rf ai/` 卸载时才会消失（可用 `--keep-local-data` 先备份）。
- 草稿 **不会自动合并** 进 `ai/skills/` 正式技能，需人工审核后复制。

openpilot 主仓的 `launch_chffrplus.sh` / `params_keys.h` 补丁在 integrate 时写入；卸载默认**不还原**（除非 `--restore-integrate`）。

## 首次使用

打开 `http://<IP>:5090`，未完成配置时会弹出**首次向导**。也可在 **设置 → 模型** 配置。

## Fork 分析（不限定社区）

1. `GET /api/ai/fork/detect` — 扫描仓库  
2. `POST /api/ai/fork/analyze` — AI 阅读项目并写 `fork_analysis/latest.json`  
3. `POST /api/ai/fork/sync` — 生成 `fork_drafts/` 草稿  

开发面板：**设置 → 开发 → Fork 分析**。

## 手动集成

```bash
cd "$OPENPILOT_ROOT"
PYTHONPATH=$PWD python3 ai/install/integrate_openpilot.py --root "$PWD"
```

## 相关 API

| API | 说明 |
|-----|------|
| `GET /api/ai/package/version` | 版本 |
| `POST /api/ai/package/update` | 更新 + integrate |
| `POST /api/ai/integrate` | 仅重新 integrate |
