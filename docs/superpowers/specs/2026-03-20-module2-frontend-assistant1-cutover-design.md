# 模块二前端切换到 assistant_1 设计稿

## 目标

将前端信息提取任务助手从旧的 `assistant` 后端链路切换到新的 `assistant_1` 后端链路，并保留现有前端中的以下 UI 能力：

- 单回答框流式输出
- 证据侧栏
- 动作预览卡片
- 助手运行状态展示

本次切换后，前端不再依赖旧的：

- `POST /extract/assistant/session`
- `POST /extract/assistant/chat/stream`

改为使用新的：

- `POST /extract/assistant1/chat/stream`

## 方案

### 1. 输入侧切换

前端提交助手问题时改为调用 `assistant_1` 的 SSE 接口，请求体使用：

- `message`
- `session_id`
- `file_hash`
- `history`
- `top_k`
- `max_steps`
- `client_caps`

其中 `history` 不再依赖旧后端会话恢复，而是直接从前端当前对话框里的最近消息构造。

### 2. 会话侧切换

去掉旧的 `/extract/assistant/session` 恢复请求。

保留前端本地 `session_id` 存储能力，仅用于把 assistant_1 返回的 `session_id` 继续透传给后续请求；不再依赖旧 assistant 的持久化会话消息恢复。

### 3. SSE 事件协议切换

前端从旧事件协议切换到 assistant_1 新协议，主要消费：

- `stream.open`
- `assistant.start`
- `status`
- `assistant.delta`
- `assistant.replace`
- `evidence.bundle`
- `action.preview`
- `warning`
- `assistant.done`
- `error`

其中：

- `assistant.delta` 继续写入当前 assistant 回答框
- `assistant.replace` 用于最终对齐文本
- `status` 只更新状态，不生成新消息框
- `evidence.bundle` 映射为现有证据侧栏结构
- `action.preview` 映射为现有动作预览卡片

### 4. UI 保留策略

保留现有以下前端结构，不做大改：

- `AssistantDialogMessage`
- `assistantCompanionCitations`
- `assistantCompanionActionPreview`
- `assistantRuntimeEvents`

必要时在前端增加轻量适配函数，把 assistant_1 的事件负载映射为当前 UI 结构。

## 风险与处理

### 1. assistant_1 暂无旧式 session restore

处理方式：

- 使用本地 `history` 维持多轮上下文
- 保留 `session_id` 透传，后续后端若增强会话能力可继续兼容

### 2. 证据事件结构不同

处理方式：

- 将 `evidence.bundle.items` 映射为前端现有 `AssistantCitation`
- 无法直接定位原文时也保留摘要与片段，避免 UI 断裂

### 3. 动作预览结构不同

处理方式：

- 将 assistant_1 的 `action.preview` 负载适配为前端现有 `AssistantActionPreview`
- 优先保留标题、摘要、确认要求、SQL 预览等核心字段

## 验收标准

- 前端助手发送问题后，实际请求落到 `/extract/assistant1/chat/stream`
- 不再调用旧的 `/extract/assistant/session`
- 不再调用旧的 `/extract/assistant/chat/stream`
- 流式回答仍保持单回答框
- 证据侧栏可继续展示
- 动作预览卡片可继续展示
- 多轮提问时上下文可由前端本地历史维持
