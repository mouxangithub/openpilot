# 记忆协议（Memory Protocol）

> Hermes / OpenClaw 风格三层记忆。本技能**每轮固定加载**——遵守协议是硬性要求。

## 三层结构

| 层 | 文件 / 工具 | 写什么 |
|----|-------------|--------|
| **当日 Wiki 页** | `workspace/memory/YYYY-MM-DD.md` · `INDEX.md` | 一天一页；每轮自动注入 prompt |
| **长期** | `MEMORY.md` · `update_workspace_file(key=memory)` | 跨月稳定事实、已解决问题、待跟进 |
| **画像** | `USER.md` · `update_user_profile` | 称呼、车型、沟通偏好 |
| **速记** | Params · `update_agent_memory` | 短备注、标签化事实 |

## 何时必须写（强依赖工具）

在**结束本轮回复之前**，若出现以下任一情况，**必须**调用对应工具（可组合）：

1. 用户明确偏好（「跟车远一点」「少说术语」）→ USER + 可选 daily
2. 调参 / 适配 / 排障结论 → daily + MEMORY「已解决问题」
3. 车型、硬件、fork 事实 → USER「车辆与设备」+ MEMORY「长期事实」
4. 用户说「记住…」→ 按内容选 daily / MEMORY / `update_agent_memory`
5. `/compact` 或长对话摘要后 → daily + MEMORY

**禁止**只在回复里说「我会记住」而不调工具。

## 章节约定（MEMORY.md）

- `## 长期事实` — 稳定配置、车型特性
- `## 已解决问题` — 问题 → 根因 → 修复
- `## 待跟进` — 下次入口
- `## 禁忌与边界` — 用户拒绝的方案

## 章节约定（USER.md）

- `## 称呼与语言`
- `## 车辆与设备（非敏感）`
- `## 工作流偏好`

## 对话后自动闭环

开启 `ai_evolution_auto_memory` 时，服务端会在聊天结束后用 LLM 提炼当日日志并合并 MEMORY/USER。  
**仍应在对话中主动写入**，避免仅靠后台遗漏细节。

## 隐私

不写入：API Key、密码、完整住址、无关第三方隐私。
