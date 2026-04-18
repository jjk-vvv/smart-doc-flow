# 项目文件命名规范化进度记录

Date: 2026-04-03

Status: applied

## 本轮目标

在不影响模块二、模块四和统一网关工作流的前提下，继续推进前端目录与文件命名规范化。

本轮只做低风险语义迁移：

- 调整前端内部文件和目录名
- 同步更新 import 引用
- 保持后端接口路径不变
- 保持 `data-testid` 不变
- 保持 localStorage key 不变

## 已落地内容

### 1. 前端共享状态目录收口

- `frontend/lib/extractionStore.ts` 已迁移为 `frontend/shared/state/extractionDocuments.ts`
- `frontend/lib/workbenchSession.ts` 已迁移为 `frontend/shared/state/workbenchSession.ts`

这样处理后，和“抽取结果持久化 / 工作台会话持久化”相关的前端状态不再混在泛化的 `lib/` 目录里，而是明确归到 `shared/state/`。

### 2. DeepRead 助手目录语义化

- `frontend/pages/deepread/assistant1/` 已迁移为 `frontend/pages/deepread/assistant/`
- `frontend/pages/deepread/assistant/useAssistant1Stream.ts` 已迁移为 `frontend/pages/deepread/assistant/useAssistantStream.ts`

这样处理后，DeepRead 页面下的助手子模块目录名不再暴露历史编号语义，目录职责更直接。

### 3. 相关引用已同步更新

已同步更新以下前端引用：

- `frontend/pages/deepread/DeepReadWorkbench.tsx`
- `frontend/features/platform-assistant/components/PlatformAssistant.tsx`
- `frontend/pages/dashboard/Dashboard.tsx`
- `frontend/pages/fusion/FusionGrid.tsx`
- `frontend/pages/knowledge-nexus/KnowledgeNexusNeo4j.tsx`
- `frontend/features/knowledge-graph/utils.ts`

## 本轮故意不改动的兼容面

以下内容本轮保持不变，避免影响现有工作流和回归脚本：

- `/extract/assistant1/chat/stream`
- 所有 `module2-*` / `module4-*` 的 `data-testid`
- 浏览器本地存储键，例如：
  - `module2_last_documents`
  - `module2_last_updated`
  - `module2_workbench_session_v1`
  - `module2_assistant_session_map_v1`

原因是这些已经属于前后端协议、E2E 测试依赖或历史状态兼容层，不适合和目录规范化一起混改。

## 验证结果

已执行：

```bash
npm --prefix frontend run build
```

结果：

- 前端生产构建通过
- 说明本轮重命名没有引入前端编译回退

## 当前剩余命名债务

本轮之后，仍然保留但暂不建议立即处理的内容包括：

- `backend/module2/app/assistant_1/` 及其运行产物目录
- `assistant_1_source/` 这类已进入运行时和测试链路的历史产物名
- 前端样式类名和测试标识中的 `module2` / `module4` 前缀
- localStorage 兼容键名中的 `module2_*`

这些都属于“需要兼容方案和回归验证”的高风险层，应该单独分批处理。
