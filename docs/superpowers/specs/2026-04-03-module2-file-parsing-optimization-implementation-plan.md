# Module 2 文件解析优化详细落地方案

Date: 2026-04-03

Status: execution-ready

## 文档目的

这份文档用于把当前项目中“文件解析优化”相关的讨论、回归结论、架构判断和后续执行动作，整理成一份可以直接落地执行的详细方案。

它不是新的架构重定义文档。
它是在既有统一后端和既有工作流基础上，专门面向 `Module 2 文件解析链路` 的优化执行说明。

这份文档重点回答以下问题：

1. 当前项目里各种文件类型最适合走什么解析链路。
2. 哪些地方已经验证有效，哪些地方仍然是性能或质量瓶颈。
3. 后续优化应该落到哪些真实文件上，而不是泛泛讨论。
4. 如何在不降级功能、不破坏完整工作流的前提下，提高解析效率、字段质量、产物规范性和打包准备度。
5. 如何把“不要硬编码”的要求落实到解析链路里。

建议与以下文档配套阅读：

- `docs/superpowers/specs/2026-03-16-module2-file-parsing-stabilization-design.md`
- `docs/superpowers/specs/2026-03-29-final-optimal-project-architecture-and-directory-blueprint.md`
- `docs/superpowers/specs/2026-03-29-live-workflow-regression-entrypoints.md`
- `docs/superpowers/specs/2026-03-29-migration-execution-baseline-and-acceptance.md`

## 一句话结论

当前项目的最优文件解析方案，不是“所有文件统一强行转 PDF 再解析”，而是：

`按文件类型分轨解析 + 统一任务编排与诊断 + 统一结果语义 + 保留 DOCX -> PDF -> MinerU/Gemini 的高质量视觉链路`

具体落点如下：

- `PDF`：保留 `MinerU + 视觉解析 + Gemini Vision` 主链路。
- `DOC/DOCX`：统一使用 `LibreOffice -> PDF -> PDF 解析主链路`，不再走 `Word COM`。
- `XLS/XLSX/CSV`：走原生结构化表格快路径，不转 PDF。
- `MD/TXT`：走纯文本快路径，不进入重视觉链路。
- 所有格式最终都输出统一的字段结果、trace、artifact 指针、诊断信息。

这套方案兼顾了四个目标：

- 不降级现有完整工作流。
- 保住 DOCX 和 PDF 的高质量解析能力。
- 明显改善 MD/TXT/XLSX 的解析时延。
- 为后续打包、回归、继续开发留出最稳定的结构边界。

## 当前工作流基线

当前项目中，用户真实文件解析工作流的核心主线如下：

1. 前端上传文件。
2. `frontend/pages/deepread/DeepReadWorkbench.tsx` 发起解析任务。
3. `backend/module2/app/main.py` 接收请求并进入统一编排。
4. 根据文件类型进入 `PDF / Office / Spreadsheet / Plain Text` 的不同入口。
5. 解析过程中生成字段、trace、artifact、诊断信息。
6. 结果在前端工作台中展示，用户可查看字段、预览 PDF、查看 Excel 预览、查看 trace、与 assistant1 交互。
7. 需要时结果再同步到 Module 4。

这条主线不能被破坏。
后续所有优化，都只能在这条主线上做“提效、提质、去噪、规范化”，不能把用户已有工作流打散。

## 已有回归结论

基于最近一轮已完成的真实运行记录，当前链路已经得到以下结论：

### 1. DOCX 链路

- `DOCX -> LibreOffice -> PDF -> MinerU/视觉链路` 已经可以完成。
- 已知样本 `2021年民政事业发展统计公报.docx` 曾成功跑通。
- 最近一轮记录中：
  - `office_pdf_elapsed_ms` 约为 `9997`
  - `total_ms` 约为 `189627`
  - `coverage_ratio` 约为 `0.8333`
  - `avg_confidence` 约为 `0.95`

结论：

- DOCX 质量路径是成立的。
- 当前瓶颈主要不在“是否能转 PDF”，而在后续视觉抽取和字段生成总耗时偏长。

### 2. XLSX 链路

- 已知样本 `2025山东省环境空气质量监测数据信息.xlsx` 走 `FastTrack` 成功。
- 最近一轮记录中：
  - `coverage_ratio` 为 `1.0`
  - `avg_confidence` 约为 `0.9133`
  - `total_ms` 约为 `1517`

结论：

- `XLSX` 原生结构化解析链路非常适合当前项目。
- 这类文件不应该被错误并入 PDF 视觉链路。

### 3. MD 链路

- 已知样本 `2023年文化和旅游发展统计公报.md` 可以成功解析。
- 最近一轮记录中：
  - `coverage_ratio` 为 `1.0`
  - `avg_confidence` 约为 `0.9217`
  - `total_ms` 约为 `51238`

结论：

- 质量可接受，但纯文本文件耗时偏高。
- 问题不在文件读取，而在后续 schema、抽取、字段筛选、LLM 调度仍然偏重。

### 4. TXT 链路

- 已知样本 `2024年国民经济和社会发展统计公报（节选）.txt` 可以成功解析。
- 最近一轮记录中：
  - `coverage_ratio` 为 `1.0`
  - `avg_confidence` 约为 `0.915`
  - `total_ms` 约为 `12130`

结论：

- `TXT` 已经明显比 `MD` 更快。
- 说明当前纯文本快路径是有基础的，但仍有进一步收敛和减负空间。

### 5. PDF 链路

- PDF 主链路可以跑通，但复杂 PDF 的“字段语义质量”仍然不稳定。
- 已经做过一些低价值字段过滤优化，尤其针对：
  - 类似 `比 上年增长` 这样的尾部比较噪声字段
  - 类似 `表 4 2021 年社会组织按登记机关分类 单位` 这样的表标题型伪字段

结论：

- PDF 的问题已经不再是“是否通”。
- 当前更核心的问题是：
  - 字段名是否够干净
  - 字段值是否够有业务意义
  - 图表增强和 trace 语义是否闭环

## 当前存在的核心问题

## 1. 文件类型分轨已经存在，但还不够清晰

当前代码实际上已经具备“按类型分流”的能力，但仍然存在以下问题：

- 路由和诊断信息没有完全做到一眼可判断。
- 非 PDF 文件在部分情况下仍会走到偏重的后处理环节。
- 当前主链路读起来仍然偏重 bundle 编排，难以从外部快速判断哪个格式走了哪条路径。

## 2. 纯文本文件仍然偏慢

`MD/TXT` 文件理论上应当是最快的一类，因为它们不需要：

- Office 转 PDF
- MinerU 版面分析
- 图像裁切
- Gemini Vision 图表增强

但当前实测仍然不够快，根因主要在以下几类：

- schema 规划仍然偏重。
- 某些提取和质量门控逻辑对纯文本和视觉文档没有彻底区分。
- 部分字段规则召回、候选筛选、后处理仍然按“重文档”标准执行。
- 纯文本文档的字段抽取仍然可能触发不必要的 LLM 成本。

## 3. 字段质量比“是否抽出来”更重要

当前项目已经验证：

- 只要允许系统宽松抽取，就容易得到“看起来像字段”的脏字段。
- 一旦字段名低价值，后续 assistant1、trace、同步到 Module 4 的价值都会下降。

因此后续优化原则必须是：

`宁可少一点，也不能把明显低价值或误导性的字段放进最终结果`

## 4. 规则资产和代码逻辑仍有混杂

最近已经确认，`backend/module2/app/core/schema/field_naming.py` 中曾存在一类明显的业务规则硬编码：

- 特定模板兜底字段写在 Python 源码里。
- 宏观经济类字段白名单直接写在代码里。

这类问题已经开始配置化处理，但还没有完全做完。

后续需要继续推进：

- 业务模板规则放 JSON 资产。
- 通用引擎逻辑留在 Python。
- 文件名或数据集特例不能进入生产解析主逻辑。

## 5. artifact 目录结构仍可继续规范

当前 artifacts 中仍存在一些对用户价值不高、对打包也不友好的结构问题：

- 历史运行产物容易累积。
- 图像裁切、trace crops、linked 图片目录结构偏碎。
- 有些目录更像运行缓存，而不是长期需要保存的结果资产。

优化目标不是“删光产物”，而是：

- 产物结构按单文档聚合。
- 调试产物与用户结果产物分离。
- 不把不需要的运行垃圾打进最终包。

## 最优目标架构

文件解析优化不应改变当前项目的总体架构判断。
最优结构仍然是：

- `backend/app` 作为统一对外 FastAPI 入口。
- `backend/module2` 作为文档解析主引擎。
- `frontend/pages/deepread/DeepReadWorkbench.tsx` 作为文件解析工作台主界面。

在这个框架下，文件解析的最优内部结构是：

### 输入层

- 文件上传
- 文件类型识别
- 任务创建
- 路由诊断

### 解析层

- PDF 视觉解析
- Office 转换
- Spreadsheet 原生解析
- Plain Text 原生解析

### 语义层

- schema 推断
- 字段命名归一
- 字段值质量过滤
- 领域字段规则召回

### 结果层

- 字段结果
- trace 命中
- artifact 指针
- 图表增强结果
- 统一 diagnostics

### 表现层

- PDF 预览
- Excel 预览
- 字段面板
- trace 面板
- assistant1 grounded 对话

## 各文件类型的最优解析链路

## 1. PDF

最优链路：

`PDF -> MinerU 版面解析 -> 内容块/图表/表格提取 -> Gemini Vision 增强 -> schema/字段抽取 -> trace/artifact 归一`

原则：

- 保留视觉链路。
- 不降级为纯文本。
- 不用为了提速砍掉 MinerU 或 Gemini Vision。

优化重点：

- 减少脏字段。
- 提高字段值业务可用性。
- 提高图表增强命中率和 DataFrame 闭环能力。
- 让 diagnostics 清楚标明用了哪些重链路步骤。

## 2. DOC / DOCX

最优链路：

`DOC/DOCX -> LibreOffice 转 PDF -> 进入 PDF 主链路`

原则：

- 不再使用 `Word COM` 作为生产路径。
- 不做 DOCX 原生抽取和 PDF 视觉链路并行竞争。
- 预览和解析必须共享同一份转换后的 PDF 血缘。

优化重点：

- 把转换耗时、输出 PDF 路径、失败原因写入 diagnostics。
- 降低“转好了但后面超时”的不透明感。
- 控制 Office 转换并发，避免多文件上传时拖垮总吞吐。

## 3. XLS / XLSX / CSV

最优链路：

`Spreadsheet 原生读取 -> 表头识别 -> 字段命名归一 -> 原生结构化抽取 -> trace/预览`

原则：

- 不转 PDF。
- 不进入 MinerU。
- 不用 Gemini Vision 处理本来就有结构的表格。

优化重点：

- 增强表头识别和字段命名归一。
- 处理多 sheet、空列、说明列、合并表头。
- 保持 Luckysheet 前端预览和后端抽取语义一致。

## 4. MD / TXT

最优链路：

`Plain Text 读取 -> 文本分块/清洗 -> 领域模板检测 -> 轻量 schema 规划 -> 字段抽取 -> 质量过滤`

原则：

- 不进入 PDF 视觉链路。
- 不进入图像增强链路。
- 仅在必要时触发轻量 LLM 规划。

优化重点：

- 让“纯文本快路径”真正轻起来。
- 对标题、表标题、比较尾句、段落说明等噪声做前置过滤。
- 在政府统计公报、医疗统计公报、环境监测、招聘表、临床数据等领域中提高规则召回。

## 明确不采用的方案

以下方案不适合当前项目：

### 1. 所有格式统一先转 PDF

不采用原因：

- 会严重拖慢 `XLSX/MD/TXT`。
- 会把结构化文件错误降级为视觉文件。
- 会让纯文本链路平白增加 MinerU 和图片裁切成本。

### 2. 所有格式统一只走纯文本

不采用原因：

- `PDF/DOCX` 的图表、版面、表格、图像语义会明显降级。
- 不符合你当前项目“完整工作流不能降级”的约束。

### 3. 用单一 LLM 直接替代整个解析链路

不采用原因：

- 成本不可控。
- 稳定性和可解释性不足。
- trace、artifact、定位、可回归能力会下降。

## 详细落地范围

后续优化应主要落在以下真实文件上。

| 文件 | 当前职责 | 后续优化重点 |
| --- | --- | --- |
| `backend/module2/app/main.py` | Module 2 组合根与入口 | 保持薄入口，只负责装配，不再堆叠业务硬编码 |
| `backend/module2/app/runtime/main_workflow_bundle.py` | 主工作流编排 | 明确各格式分轨入口与 diagnostics 输出 |
| `backend/module2/app/runtime/main_nonpdf_bundle.py` | 非 PDF 文件路径编排 | 做强分流，区分 spreadsheet 与 plain text，减少重链路误入 |
| `backend/module2/app/core/format/office_pdf.py` | Office 转 PDF | 固化 `LibreOffice` 生产路径，记录转换耗时、失败诊断、输出血缘 |
| `backend/module2/app/core/format/plain_text_parser.py` | 纯文本解析基础 | 做更轻的文本清洗、章节识别、噪声剔除和块级结构化 |
| `backend/module2/app/core/schema/field_naming.py` | 字段命名归一与模板规则应用 | 继续把业务规则从代码挪到资产文件，避免硬编码 |
| `backend/module2/app/assets/field_naming_rules_v1.json` | 领域规则资产 | 继续沉淀模板、字段包、fallback 规则、macro-only 规则 |
| `backend/module2/app/runtime/main_schema_fields_bundle.py` | 自动 schema 字段候选筛选 | 强化低价值字段过滤，减少标题型、比较型、说明型噪声字段 |
| `backend/module2/app/runtime/main_result_filter_bundle.py` | 字段结果后过滤 | 增强低价值结果过滤、阴影字段裁剪、数值语义过滤 |
| `backend/module2/app/runtime/main_schema_pipeline_bundle.py` | schema 管道拼装 | 按格式区分规划强度，给 plain text 更轻的规划路径 |
| `backend/module2/app/runtime/document_trace_runtime.py` | trace 结构归一 | 统一字段、表格、图表、段落 trace 语义 |
| `backend/module2/app/runtime/document_trace_hits_runtime.py` | trace 命中组织 | 保证前端点击字段能稳定回跳到正确位置 |
| `backend/module2/app/runtime/artifact_support_runtime.py` | artifact 支撑 | 收敛 artifact 目录结构与指针语义 |
| `backend/module2/app/assistant_1/agent_runtime.py` | assistant1 grounded runtime | 保证 assistant 消费的字段和 trace 足够干净，不被脏字段污染 |
| `frontend/pages/deepread/DeepReadWorkbench.tsx` | 解析工作台主页面 | 稳定多文件上传、字段展示、trace 展示、格式差异化预览 |
| `frontend/components/PdfJsViewer.tsx` | PDF 预览 | 保证 PDF trace 回跳和页码同步稳定 |
| `frontend/components/LuckysheetPreview.tsx` | Excel 预览 | 与后端表格抽取结构保持一致 |
| `frontend/lib/extractionStore.ts` | 前端结果存储 | 统一不同格式结果缓存和恢复 |
| `frontend/lib/workbenchSession.ts` | 工作台会话恢复 | 保证多轮回归与用户会话恢复稳定 |

## 硬编码治理原则

这部分是本轮优化必须显式遵守的规则。

## 可以接受的配置化内容

- 模板规则
- 字段别名
- 低价值字段词表
- 领域字段包
- 单位归一规则
- 阈值与超时
- 文件大小与并发预算

这些内容可以放在：

- `backend/module2/app/assets/*.json`
- `backend/.env`
- `backend/module2/.env`

## 不可以接受的生产硬编码

- 根据某一个 `datasets/...` 文件名决定走特殊逻辑。
- 根据某个本地绝对路径决定解析策略。
- 把某一类文档的业务字段白名单直接写死在 Python 主逻辑里。
- 把仅为了测试样本加入的特例判断放进生产链路。

## 当前治理方向

当前已经开始推进的方向是：

- `field_naming.py` 中的部分模板兜底规则外置到 `field_naming_rules_v1.json`

下一步继续推进的方向是：

- 将剩余领域规则继续配置化
- 将 `main_nonpdf_bundle.py` 和部分 schema bundle 中的阈值型常量继续抽离
- 保留少量真正属于“引擎级通用逻辑”的常量在代码中

## 详细执行阶段

## 阶段 0：基线冻结

目标：

- 明确优化前基线，防止后续“感觉变快了/变好了”但没有证据。

动作：

- 固化当前单文件基线样本：
  - PDF 至少 4 份
  - DOCX 至少 2 份
  - XLSX/CSV 至少各 1 份
  - MD/TXT 各至少 2 份
- 固化结果采集项：
  - `route`
  - `quality_status`
  - `coverage_ratio`
  - `avg_confidence`
  - `office_pdf_elapsed_ms`
  - `total_ms`
  - `trace_count`
  - `artifact_root`
- 固化回归输出目录，例如：
  - `.runlogs/file-parsing-optimization/<round>/`

验收：

- 后续每次优化都能和同一批样本对比。

## 阶段 1：分轨清晰化

目标：

- 让每个文件类型走哪条链路变得明确、可诊断、可回归。

动作：

- 在 `main_workflow_bundle.py` 和 `main_nonpdf_bundle.py` 中梳理分轨。
- diagnostics 中明确输出：
  - `parse_track`
  - `input_kind`
  - `office_pdf_converted`
  - `word_parse_via_pdf`
  - `used_mineru`
  - `used_gemini_vision`
- 让纯文本、表格、视觉文档三类入口在结构上可区分。

验收：

- 任意一次任务完成后，能从 diagnostics 一眼判断这份文件走了哪条路径。

## 阶段 2：纯文本快路径优化

目标：

- 大幅降低 `MD/TXT` 的不必要耗时。

动作：

- 在 `plain_text_parser.py` 中加强预清洗：
  - 去除无意义空行堆叠
  - 识别文档标题、元信息、正文块
  - 识别明显的表标题、图标题、单位行
- 在 `main_nonpdf_bundle.py` 中为 `MD/TXT` 设置更轻的 schema 规划策略：
  - 更小候选集
  - 更少 LLM 触发
  - 更少视觉相关后处理
- 在 `main_schema_fields_bundle.py` 中增加纯文本场景的噪声过滤：
  - 比较尾句
  - 表标题
  - 标注性括号说明
  - 无业务意义的章节名
- 在 `main_result_filter_bundle.py` 中增强“结果值层面”的低价值过滤。

验收：

- 同机同依赖下，`MD/TXT` 平均耗时显著低于当前基线。
- 输出字段数量可能减少，但业务字段质量提升。

## 阶段 3：Spreadsheet 原生链路增强

目标：

- 提高 `XLS/XLSX/CSV` 的表头识别质量和字段归一质量。

动作：

- 强化多 sheet 处理策略。
- 强化首行、次行、合并表头识别。
- 在 `field_naming_rules_v1.json` 中补充更多业务字段别名。
- 保证 Luckysheet 预览和后端抽取列名尽量一致。
- 对说明列、备注列、统计口径列做更稳的过滤。

验收：

- `XLSX` 不被错误送进 PDF 链路。
- 表头语义更稳定，字段名更干净。

## 阶段 4：DOCX 转换与视觉链路稳定化

目标：

- 保住 `DOCX -> PDF -> MinerU/Gemini` 高质量链路，同时降低不透明耗时。

动作：

- 在 `office_pdf.py` 中进一步规范：
  - 只保留 `LibreOffice`
  - 输出转换耗时
  - 输出输入文件与 PDF 输出文件的血缘映射
  - 明确超时和失败原因
- 控制 Word/PDF 转换并发预算。
- 在 `main_workflow_bundle.py` 中把 Office 转换和后续视觉链路拆成可观测的两个阶段。

验收：

- DOCX 失败时能清楚知道是转换失败、解析失败，还是抽取阶段失败。
- 成功路径中，预览和解析使用同一 PDF 产物。

## 阶段 5：PDF 字段质量与图表闭环

目标：

- 提高 PDF 结果质量，而不是只追求“能跑完”。

动作：

- 在 `field_naming.py` 和 `field_naming_rules_v1.json` 中补领域字段包。
- 在 `main_schema_fields_bundle.py` 中继续增强：
  - 标题型伪字段过滤
  - 比较型伪字段过滤
  - 单位型伪字段过滤
  - 文档大标题误入过滤
- 在 `main_result_filter_bundle.py` 中增加：
  - 低价值结果值过滤
  - 阴影字段裁剪
  - 短字段/弱字段与长字段的优先级裁剪
- 在 `document_trace_runtime.py` 和 `document_trace_hits_runtime.py` 中强化图表与表格 trace 归一。

验收：

- 已知 PDF 硬样本不再退回到脏字段堆。
- trace 中图表、表格、字段的对应关系更清楚。

## 阶段 6：artifact 目录结构优化

目标：

- 让产物结构更适合长期维护、调试和打包排除。

动作：

- 每份文档一个 artifact root。
- 将 linked 图片、trace crops、图表裁切按文档聚合，而不是碎片化散落。
- 区分：
  - 用户结果产物
  - 调试过程产物
  - 临时缓存产物
- 在 `artifact_support_runtime.py` 中统一相对路径指针。

推荐目标结构示意：

```text
backend/module2/artifacts/
  <doc_hash>/
    source/
    preview/
    parse/
      mineru/
      markdown/
      tables/
      figures/
    trace/
    assistant/
    meta/
```

验收：

- 单文档相关产物集中。
- 不再出现大量难以理解的碎目录。
- 打包排除规则更容易维护。

## 阶段 7：前端多文件回归与展示稳定化

目标：

- 保证优化之后前端工作台没有功能回退。

动作：

- 在 `DeepReadWorkbench.tsx` 中验证：
  - 单文件上传
  - 多文件上传
  - 文档切换
  - PDF 回跳
  - Excel 预览
  - 字段搜索
  - trace 面板切换
- 对 assistant1 保持 grounded 结果消费能力，不引入脏字段噪声。
- 优先用真实前端回归。
- `agent-browser` 可用时做浏览器自动化回归。
- 若环境问题阻塞，则保留 Playwright 作为备用回归手段。

验收：

- 同一批文件在前端可顺利完成完整工作流。
- 文档切换、trace 定位、结果展示不出现明显回退。

## 阶段 8：最终验收与打包准备

目标：

- 把解析优化结果转化为“可封装软件”的稳定状态。

动作：

- 清理不应打包的旧 artifacts、trace_rois、测试输出。
- 保留运行所需代码，不预打包运行垃圾。
- 复核 `.env`、路径语义、artifact 根目录、用户数据目录策略。

验收：

- 代码与运行产物边界清楚。
- 打包时不会再把无用历史产物带进去。

## 领域字段规则召回策略

字段规则不能只为当前测试集服务。
后续优化必须避免“只修当前样本”的窄化问题。

建议按以下层次补齐：

### 第一层：通用字段规则

- 标题
- 发布机构
- 发布日期
- 年份
- 地点
- 金额
- 比率
- 数量
- 人数
- 时间

### 第二层：文档模板规则

- 政府统计公报
- 医疗卫生统计公报
- 环境监测报告
- 招聘岗位表
- 临床病例数据
- 流行病监测数据
- 通用业务台账

### 第三层：领域字段包

- 经济类
- 民政类
- 医疗类
- 环境类
- 人力招聘类
- 临床类
- 流行病学类
- 财务类

### 第四层：反噪声规则

- 表标题
- 图标题
- 单位说明
- 比较尾句
- 页眉页脚
- 章节标题
- 无业务意义的说明行

后续所有新增召回规则，优先进入资产文件，而不是散落到 Python 源码里。

## 性能优化原则

性能优化必须在“不降级质量”的前提下进行。

## 可以做的优化

- 降低非必要 LLM 调用次数
- 按格式分配不同预算
- 让纯文本走更轻路径
- 对缓存命中更友好
- 控制 DOCX 转 PDF 并发
- 减少不必要的视觉后处理

## 不能做的优化

- 砍掉 DOCX 的 PDF 视觉主链路
- 砍掉 PDF 的 MinerU/Gemini 核心链路
- 为了速度把字段质量过滤去掉
- 用单个 hardcoded 样本特判换取“看起来更快”

## 回归测试矩阵

后续每轮优化至少要跑以下矩阵：

### 单文件回归

- PDF：4 份
- DOCX：2 份
- XLSX：2 份
- CSV：1 份
- MD：2 份
- TXT：2 份

### 多文件回归

- 2 文件混传
- 3 文件混传
- 5 文件混传

### 关键检查项

- 是否成功完成任务
- 是否走了预期链路
- 是否生成了字段结果
- 是否生成了 trace
- 是否生成了 artifact 指针
- 是否存在明显脏字段
- 前端是否能稳定展示
- assistant1 是否还能稳定消费结果

## 完成定义

当以下条件同时成立时，可以认为本轮“文件解析优化”达到阶段性完成：

1. `PDF/DOCX/XLSX/MD/TXT` 都有稳定的、被明确诊断的解析路径。
2. `DOCX -> LibreOffice -> PDF -> MinerU/Gemini` 链路稳定，不再依赖 `Word COM`。
3. `XLSX/CSV` 始终走原生结构化快路径。
4. `MD/TXT` 时延明显改善，且字段质量没有下降。
5. 低价值字段、标题型伪字段、比较型伪字段被明显收敛。
6. 图表和表格 trace 结构更清晰。
7. artifact 目录结构更规整，打包排除边界更清楚。
8. 多文件上传与文档切换回归通过。
9. 规则配置持续外置，生产解析主逻辑不再新增数据集级硬编码。

## 最终执行原则

本轮文件解析优化必须遵守以下总原则：

`按文件类型走最适合的链路，按结果语义统一输出，按资产文件沉淀规则，按真实工作流做回归，在不降级功能的前提下持续提效。`

这就是当前项目最适合、最完整、也最利于后续继续开发和软件封装的文件解析优化落地方案。
