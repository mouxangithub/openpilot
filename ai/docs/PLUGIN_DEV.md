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
