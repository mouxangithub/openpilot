# GitHub Wiki 同步

| 渠道 | 地址 | 是否需要 PAT |
|------|------|----------------|
| **GitHub Pages（推荐）** | https://mouxangithub.github.io/ai/ | 否（Actions 自动发布） |
| 主仓源稿 | https://github.com/mouxangithub/ai/tree/main/docs/wiki | 否 |
| GitHub Wiki | https://github.com/mouxangithub/ai/wiki | **是**（`WIKI_SYNC_TOKEN`） |

源稿目录：**`docs/wiki/`**（PR 审阅后由 CI 发布）。

## 为什么 Wiki git push 一直 404？

`GITHUB_TOKEN` **不能**读写隐藏仓库 `mouxangithub/ai.wiki`（GitHub 故意返回 `Repository not found`）。  
本地未登录时 `git clone` 也会同样报错。

**不是你的操作问题**，必须配置个人 PAT。

## 一次性配置 WIKI_SYNC_TOKEN（3 分钟）

**必须用 classic PAT**，且能访问隐藏仓库 `ai.wiki`：

| 配置项 | 要求 |
|--------|------|
| Token 类型 | **Generate new token (classic)**（`ghp_` 开头） |
| ❌ 不要用 | Fine-grained（`github_pat_` 开头）— **无法**访问 wiki git |
| Scope | 勾选 **`repo`** |
| 仓库范围 | **All repositories**（不要选 Only select repositories 只勾 `ai`） |

步骤：

1. https://github.com/settings/tokens → **Generate new token (classic)** → **`repo`** → **All repositories**
2. https://github.com/mouxangithub/ai/settings/secrets/actions → `WIKI_SYNC_TOKEN`
3. **Actions → Sync GitHub Wiki → Run workflow**

Workflow 会先跑 **Validate WIKI_SYNC_TOKEN**；若 Token 类型/权限不对，日志里会写明原因（不必再猜 404）。

成功后 Wiki 会出现 9 页：`Home`、`GEPA-Evolution`、`OP-CLI` 等。

## GitHub Pages（无需 PAT）

1. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**（若尚未选）  
2. 推送 `docs/wiki/**` 后 workflow **Deploy Wiki Docs (GitHub Pages)** 自动运行  
3. 访问 https://mouxangithub.github.io/ai/

## 页面列表

| Wiki 页 | 源文件 |
|---------|--------|
| Home | `docs/wiki/Home.md` |
| Quick-Start | `docs/wiki/Quick-Start.md` |
| OP-CLI | `docs/wiki/OP-CLI.md` |
| Web-Terminal | `docs/wiki/Web-Terminal.md` |
| Tuning-for-Owners | `docs/wiki/Tuning-for-Owners.md` |
| Troubleshooting | `docs/wiki/Troubleshooting.md` |
| Vehicle-Adaptation | `docs/wiki/Vehicle-Adaptation.md` |
| Daily-Memory | `docs/wiki/Daily-Memory.md` |
| GEPA-Evolution | `docs/wiki/GEPA-Evolution.md` |

## 本机手动同步 Wiki（可选）

```bash
export WIKI_SYNC_TOKEN=ghp_xxxx   # 你的 classic PAT
bash ai/scripts/sync_github_wiki.sh
```

## 与 docs/ 关系

| 类型 | 位置 |
|------|------|
| 用户 Wiki / Pages | `docs/wiki/` |
| 开发者长文 | `docs/*.md` |
| Issue/PR 模板 | `.github/` |
