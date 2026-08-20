# 技能（Skill）编写指南

技能是 `ai/skills/<id>/SKILL.md`，在 `registry.json` 注册后注入系统提示。

## 新增技能步骤

1. 创建 `ai/skills/my-skill/SKILL.md`（何时触发、工具顺序、常见坑）
2. 在 `ai/skills/registry.json` 增加条目：
   ```json
   {"id": "my-skill", "name": "...", "path": "my-skill/SKILL.md", "default_enabled": true, "requires_tools": ["tool_a", "tool_b"]}
   ```
3. 若有新工具，优先放在 `ai/plugins/builtin/` 或 `sp_tool_extensions.py`
4. 可选：在 `ai/tools/workflows.py` 增加工作流 ID
5. 运行 `sync_knowledge_from_docs` 或更新 `rag_seed.py` 摘要

## requires_tools

技能仅在用户启用的工具全部可用时加载。不要把未实现的工具写进 `requires_tools`。

## 与 Workflow 关系

- **Skill**：领域知识与推荐顺序（软约束）
- **Workflow**：用户点击卡片或 `workflow_id` 时的硬步骤（`workflows.py`）

## 品牌技能

`sp-brand-*` 在 `registry.json` 可带 `"brands": ["toyota"]`，由车型自动过滤。

## 版本

修改 `registry.json` 时递增顶层 `"version"` 便于 Web 缓存失效。
