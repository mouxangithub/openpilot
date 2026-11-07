# PC 开发联调

`get_host_environment`、`pc_launch_replay`、`pc_launch_plotjuggler`、`git_*`、`run_scons_build`

## C3 / Panda 开发

- 列出全部 USB Panda：`list_all_pandas`（含多 Panda 场景、`pgrep pandad`）
- 仅 F4（DOS/黑熊）：`list_f4_pandas`
- 编译 F4 固件：`build_panda_firmware` 或 `scons` in `panda/board`
- 刷机文档：`ai/docs/PANDA_FLASH.md`；技能 `c3-dos-panda`
- 车机刷机：`pc_devsync_run` 同步代码后 SSH 跑 `ai/scripts/recover_dos_panda.py`（仅 F4）
- 异构双 Panda（内置 F4 + 外接红熊）：车机侧重编 `rebuild_pandad_tici`，见 `PANDA_FLASH.md`

## GitHub Runner / prebuilt

- 状态：`github_runner_status`、`github_runner_recovery_hint`
- 文档：`ai/docs/GITHUB_RUNNER.md`；技能 `github-runner`
- 用户手册：`release/ci/README.md`
- 触发编译：推 `master-c3` 或 Actions → `build.yaml`
- 车机安装产物：`git reset --hard origin/master-c3-prebuilt` + 确认 `prebuilt` 文件
- **推送代码**：`GIT_LFS_SKIP_PUSH=1`（op助手 `git_push` 已自动设置）；见 `ai/docs/GIT_LFS.md`

## 知识库

- 文档变更后：`sync_knowledge_from_docs` — 同步 `ai/docs/` 进 RAG
