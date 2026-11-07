# GEPA 技能自进化

OP Agent 内置 **GEPA**（Genetic-Pareto）风格技能优化：用评测集打分 → 反思变异 → 生成技能补丁提案，**不会自动覆盖**你的 `SKILL.md`，需人工或 PR 合并。

## 什么时候用

| 场景 | 建议 |
|------|------|
| 某技能回答总跑偏 | 对该 `skill_id` 跑 GEPA，看提案 diff |
| 新车型话术不准 | 先补 `golden.jsonl` 用例，再进化 |
| 日常用车 | **不用管**；默认关闭自动进化 |

## 车主入口（高级）

Web 设置 → **AI 进化** → 开启 GEPA（开发者/维护者）。

API（需 aid 运行）：

```http
POST /api/ai/platform/evolution
Content-Type: application/json

{
  "operation": "gepa",
  "skill_id": "engage-troubleshooting",
  "eval_source": "golden",
  "dry_run": true
}
```

- `dry_run: true` — 只评测当前技能，不改文件  
- `eval_source: golden` — 使用仓库内 golden 数据集（见下）

## Golden 评测集（对用户可见）

源文件在仓库：

`ai/evolution/datasets/<skill_id>/golden.jsonl`

| 技能 | 覆盖场景 |
|------|----------|
| memory-protocol | 记忆、偏好、每日日志 |
| sp-tuning | 横向/纵向/MADS |
| engage-troubleshooting | 无法 Engage、Panda、SecOC |
| longitudinal-tuning | 跟车手感 |
| vehicle-adaptation | 新车适配 |
| health-check | 体检、OTA 预检 |
| post-tune-validation | A/B、快照回滚 |

每行一条用户原话 + 期望行为 rubric，便于社区 PR 增补。

索引说明：[datasets/README](https://github.com/mouxangithub/ai/blob/main/evolution/datasets/README.md)

## 与 Hermes 自进化仓库的关系

设计对齐 [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)；本机实现位于 `ai/evolution/`。

长文：[HERMES_EVOLUTION.md](https://github.com/mouxangithub/ai/blob/main/docs/HERMES_EVOLUTION.md)

## 安全

- 改参、刷机、重启类工具仍走 **确认卡**  
- GEPA 产出为 **提案**，不直接写车机 Params  
- 评测含启发式 + golden，不保证道路安全，封闭场地验证仍必需
