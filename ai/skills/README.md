# Agent Skills

Markdown 技能包，供 op助手在系统 prompt 中加载领域知识。

- **注册表**：`registry.json`  
- **加载器**：`loader.py` → `build_skills_prompt()`  
- **Param 分级**：`params_catalog.json`（供未来 `write_params` 白名单）  
- **路线图**：`../docs/AI_AGENT_ROADMAP.md`
- **Comma 设备 / pandad**：`../docs/COMMA_DEVICES.md`（C3/C3X/C4 与 `panda_connect.py`）
- **CP 迁移对照**：`carrot-legacy/` + 内置 RAG（`tools/rag_seed.py`）
- **车辆适配**：`vehicle-adaptation/`（指纹、DBC、草稿导出）

新增技能：新建 `<id>/SKILL.md`，在 `registry.json` 登记即可。
