# Smart Doc Flow 项目文件命名规范与首批落地方案

Date: 2026-04-03

Status: approved-working-baseline

## 目标

这份文档用于统一 Smart Doc Flow 当前项目的文件命名规则，并约束后续重构迁移时的命名方式。

这次规范化的核心目标不是“大面积重命名所有历史文件”，而是：

- 先消除最影响目录边界和可读性的命名噪音
- 保证前后端与模块链路不因命名调整出现回退
- 为后续目录归并、桌面打包、长期维护提供稳定基线

## 当前命名问题

结合当前仓库结构，命名问题主要集中在四类：

1. 根目录残留历史运行目录，与正式源码目录同名
   - 典型问题：仓库根目录存在历史 `module2/` 运行目录，而正式源码目录是 `backend/module2/`
   - 风险：团队成员和脚本容易误把运行态目录当成源码目录

2. 前端根目录存在泛名文件，文件名无法体现职责
   - 典型问题：`image.png`、`check_tags.cjs`
   - 风险：阅读者无法从文件名判断用途，后续打包与资源管理容易混乱

3. E2E / 调试脚本命名混有临时痕迹
   - 典型问题：`playwright_auth.mjs`、`_debug_upload.mjs`、`tmp_workflow_test.mjs`
   - 风险：正式回归脚本、调试脚本、临时脚本混在一起，职责边界不清

4. 历史迁移文件存在阶段性命名，但已深度嵌入链路
   - 典型问题：`assistant_1/`、`assistant_1_source/`
   - 风险：虽然名字不理想，但直接重命名会牵动大量 import、测试、运行时产物和历史文档引用

## 命名总原则

### 1. 先保证职责清晰，再追求形式统一

文件名首先要回答“这个文件做什么”，而不是只满足某种机械格式。

### 2. 源码目录与运行态目录必须显式区分

- 源码只放在受版本管理的业务目录中
- 运行态产物只允许进入 `runtime-data/`、`.runlogs/`、`.codex-temp/` 等明确边界目录
- 不允许在仓库根目录保留与源码目录同名的运行态目录

### 3. 允许模块内使用标准入口文件名

以下命名在边界清晰的上下文中是允许重复的，不视为命名混乱：

- `main.py`
- `router.py`
- `service.py`
- `repository.py`
- `schemas.py`
- `config.py`
- `__init__.py`

原因是这些文件在 FastAPI 分层 MVC 中属于稳定角色名，问题不在于“同名”，而在于是否位于明确模块边界内。

### 4. 避免无信息量的泛名文件

以下命名应避免直接作为长期正式文件名：

- `image.png`
- `temp.*`
- `tmp_*`
- `_debug_*`
- `misc.*`
- `helper.py`
- `utils.py`

只有在以下情况可以接受：

- 文件明确处于临时目录中
- 文件确实属于短生命周期调试资产
- 文件职责极其通用且已位于明确上下文目录内

### 5. 顶层脚本与测试脚本优先使用 kebab-case

适用范围：

- `.cjs`
- `.mjs`
- Node 侧运维脚本
- 前端 E2E 脚本

推荐格式：

- `auth-session.mjs`
- `debug-upload.mjs`
- `workflow-smoke-debug.mjs`
- `check-svg-tags.cjs`

### 6. Python 业务代码保持 snake_case

适用范围：

- Python 模块文件
- Python 包目录

推荐格式：

- `module2_sidecar_runtime.py`
- `field_naming.py`
- `office_pdf.py`

不推荐继续扩散的格式：

- 多层职责串联式长命名
- 为了拆分而拆分出的碎片化文件名

### 7. React 组件使用 PascalCase，页面目录使用语义化目录名

推荐：

- `DeepReadWorkbench.tsx`
- `Module1PlaceholderPage.tsx`
- `AccountSecurityModal.tsx`

页面目录推荐：

- `pages/deepread`
- `pages/dashboard`
- `pages/knowledge-nexus`

### 8. 文档命名保持“日期 + 主题 + 文档类型”

推荐格式：

- `YYYY-MM-DD-topic-design.md`
- `YYYY-MM-DD-topic-plan.md`
- `YYYY-MM-DD-topic-report.md`
- `YYYY-MM-DD-topic-blueprint.md`

不建议继续增加多重修饰词，避免文件名无限变长。

## 本轮落地范围

这次只做低风险、高收益的命名规范化，不做会影响主链路的大规模 Python 包重命名。

### 本轮直接落地

1. 清理根目录历史 `module2/` 运行目录
   - 目标：只保留 `backend/module2/` 作为源码目录
   - 运行态统一落到 `runtime-data/module2/`

2. 规范前端根目录泛名资源文件
   - `image.png` 改为更能体现用途的资源名
   - `check_tags.cjs` 移入更合理的工具目录并改为语义化名称

3. 规范前端 E2E 工具脚本命名
   - `playwright_auth.mjs` 改为语义更明确的认证辅助脚本名
   - `_debug_upload.mjs` 改为无前缀噪音的调试脚本名

4. 收口仓库根目录临时脚本
   - `tmp_workflow_test.mjs` 不再留在仓库根目录
   - 移入明确的临时或调试目录

### 本轮暂不直接改名

以下对象虽然命名不完美，但当前不适合在这轮直接修改：

1. `backend/module2/app/assistant_1/`
   - 原因：涉及大量 import、测试、历史设计文档、运行产物路径与抽取助手上下文链路
   - 处理策略：后续如要改名，必须走“兼容别名 + 全链路回归 + 运行产物迁移映射”的专门方案

2. `assistant_1_source/` 等历史产物目录名
   - 原因：已经被测试、artifact path、前后端链路消费
   - 处理策略：保持兼容，后续如改名需先提供路径映射层

3. 大量 `main_*_bundle.py`、`*_runtime.py`
   - 原因：这类文件虽偏长，但当前主要问题已不在命名，而在后续是否需要再归并
   - 处理策略：先保证目录边界与职责清晰，再按模块做第二阶段归并

## 规范后的推荐边界

### 顶层目录

- `backend/`：正式后端源码
- `frontend/`：正式前端源码
- `electron/`：桌面壳层
- `scripts/`：正式开发与运维脚本
- `docs/`：设计、迁移、验收文档
- `datasets/`：测试样本
- `runtime-data/`：运行态产物

### 不应该长期出现在仓库根目录的内容

- `tmp_*`
- 临时调试脚本
- 运行态日志目录
- 与正式源码目录重名的运行目录

## 这轮规范化的验收标准

1. 仓库根目录不再存在与正式源码目录同名的历史运行目录
2. 前端根目录不再保留明显无职责含义的泛名工具文件
3. E2E 与调试脚本文件名能够直接体现用途
4. 改名后的引用全部修正
5. 前端构建与关键脚本入口不因命名变更失效
6. 不对 `assistant_1` 这类高风险历史命名做粗暴重命名

## 后续第二阶段建议

当当前链路继续稳定后，再考虑以下高风险命名治理：

1. `assistant_1` 包重命名方案
2. `assistant_1_source` 运行产物目录兼容迁移方案
3. `main_*_bundle.py` 与部分 `*_runtime.py` 的适度归并
4. 历史设计文档文件名的压缩与归档分层

本轮结论：

最优策略不是全仓库一次性大改名，而是先完成“目录边界去噪 + 泛名文件收口 + 调试脚本归位 + 高风险历史命名冻结”。
这能在不影响当前完整工作流的前提下，真正提升项目的可读性、可维护性和后续打包稳定性。
