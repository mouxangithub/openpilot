# op助手插件开发

插件用于把 **工具元数据 + schema + handler** 打包为可开关模块。

## 目录

```
ai/plugins/
  registry.json          # 插件列表
  loader.py              # 加载与合并
  builtin/
    github_ci.py         # 示例：完整插件（meta + schema + handlers）
    route_analytics.py   # 示例：仅 meta 分组
```

## 最小插件

```python
# ai/plugins/builtin/my_plugin.py
from typing import Any, Callable

TOOL_META: dict[str, dict[str, Any]] = {
  "my_tool": {"label": "我的工具", "group": "read", "default_enabled": True, "driving": True},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  {"type": "function", "function": {"name": "my_tool", "description": "...", "parameters": {"type": "object", "properties": {}, "required": []}}},
]

def make_handlers(ctx: dict) -> dict[str, Callable[..., Any]]:
  p = ctx.get("params")
  def h_my_tool(_a):
    from ai.tools.domains.platform.my_module import my_tool
    return my_tool(p)
  return {"my_tool": h_my_tool}
```

在 `registry.json` 注册：

```json
{"id": "my-plugin", "name": "...", "module": "ai.plugins.builtin.my_plugin", "enabled": true}
```

`extensions.py` 启动时自动 `collect_plugin_*` 合并进 LLM 工具列表。

## ctx 字段

| 键 | 说明 |
|----|------|
| `params` | openpilot Params |
| `get_state_reader` | cereal 状态 |
| `stationary_check` | 写/ shell 前检查离路 |
| `needs_confirm` | 是否需二次确认 |

## 安全

- 写操作走 `stationary_check` + `confirm=true` 或 `write_pending`
- 密钥类 Param 使用 `DONT_LOG`，工具返回值勿包含 token

## 测试

```bash
python -m unittest ai.tests.test_tools.TestExtensionTools.test_plugins_registry -v
```

## P2 增量：Skill manifest 新字段

从 P2 开始，`Skill` 模型支持生命周期字段。注册 skill 时建议填写完整 manifest：

```python
from ai.skill.models import Skill, SkillDependency, SkillParameter

skill = Skill(
  id="my_skill",
  name="My Skill",
  description="示例技能",
  policy="auto",               # auto | confirm | disabled
  parameters=[
    SkillParameter(name="vin", type="string", description="车辆 VIN", required=True),
  ],
  scope="global",              # global | session | project
  version="1.2.3",             # semver
  capabilities=["vehicle_read", "demo"],
  dependencies=[
    SkillDependency(name="vehicle-state", version_constraint=">=1.0.0"),
  ],
  source="builtin:my_skill",   # builtin: | https:// | file://
)
```

HTTP 注册 session scope skill 示例：

```bash
curl -X POST http://localhost:5090/api/ai/skills/session/register \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-42",
    "skill": {
      "id": "demo_session_skill",
      "name": "Demo",
      "description": "仅当前会话可用",
      "policy": "auto",
      "parameters": [],
      "scope": "session",
      "version": "0.1.0"
    }
  }'
```

## P2 增量：Workflow DSL 示例

WorkflowEngine 使用声明式 definition。最小示例如下：

```yaml
# workspace/workflows/greet.yaml
id: greet
name: Greet Workflow
version: "1.0.0"
inputs_schema:
  name: {type: string}
steps:
  - id: log_start
    kind: log
    description: workflow started

  - id: build_greeting
    kind: tool
    inputs:
      tool: echo
      message: "Hello, ${inputs.name}!"

  - id: save
    kind: tool
    inputs:
      tool: echo
      message: "${steps.build_greeting.output.args.message}"

outputs:
  greeting: "${steps.save.output.args.message}"
```

Python 调用：

```python
from ai.core.workflow import WorkflowEngine
import yaml, asyncio

with open("workspace/workflows/greet.yaml") as f:
    definition = yaml.safe_load(f)

async def main():
    engine = WorkflowEngine()
    result = await engine.run(definition, {"name": "openpilot"})
    print(result.output)  # {'greeting': 'Hello, openpilot!'}

asyncio.run(main())
```

常用 step kind：

| kind | 关键字段 | 说明 |
|------|----------|------|
| `tool` | `inputs.tool`、`inputs.*` | 调用平台/代理工具 |
| `agent` | `agent.prompt`、`agent.tools`、`agent.max_rounds` | 调用子代理 |
| `condition` | `condition`、`branches` | 条件分支 |
| `loop` | `for_each`、`branches[0]` | 遍历并收集结果 |
| `parallel` | `parallel: [Step]` | 并发执行分支 |
| `graph` | `graph_id` | 调用现有 GraphExecutor 工作流 |
| `log` | `description` | 写入 workflow 日志 |

变量插值语法：

- `${inputs.x}`：workflow 输入
- `${steps.step_id.output.field}`：某步骤输出
- `${item}`：loop 当前元素
