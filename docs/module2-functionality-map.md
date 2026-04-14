# Module 2 完整功能地图

## 1. 遍历范围与阅读口径

这份文档基于对 `backend/app/modules/module2` 的逐文件遍历整理而成，重点覆盖：

- `323` 个 Python 源文件
- `1` 个 SQL 初始化脚本
- `6` 个 schema / field 规则 JSON 资产
- 模块自带 `README.md` 与 `requirements.txt`

本次分析明确排除了以下运行期目录，因为它们属于运行产物而不是源码本体：

- `__pycache__/`
- `runtime-data/`
- `workspaces/`

因此，本文描述的是模块二的“真实代码能力边界”，不是某次运行留下来的缓存结果。

## 2. 模块定位

模块二是项目中的“非结构化文档解析与可溯源抽取中台”。它不是单一的 OCR 服务，也不是单一的字段抽取服务，而是一整条从上传、解析、结构化抽取、预览、原文定位、助手问答到模块四同步的完整链路。

从代码结构上看，模块二承担了 7 类核心职责：

1. 文档接入与任务编排
2. 多格式解析与格式归一化
3. PDF / 视觉链路 / 表格链路 / 图像链路的内容抽取
4. Schema 推理、字段抽取、质量门控与结果后处理
5. 预览、Office 转 PDF、artifact 生成与 trace 定位
6. Assistant 1 文档助手与知识检索
7. 向模块四推送可入图谱的文档结果

## 3. 模块二能做什么

### 3.1 上传与任务控制

模块二支持把解析拆成“创建任务”和“直接批处理”两条路径：

- 创建异步任务：`/extract/jobs/create`
- 查询任务状态：`/extract/jobs/status/{job_id}`
- 对单个文件取消解析：`/extract/jobs/{job_id}/cancel-file`
- 直接执行批量抽取：`/extract/batch`

对应代码主要在：

- `api/endpoints/extraction.py`
- `api/v1/endpoints/extraction_request.py`
- `core/module2_request_runtime.py`
- `runtime/extraction_requests.py`
- `runtime/extraction_jobs.py`
- `services/extraction/request.py`
- `services/extraction/job.py`

这说明模块二不是“上传即同步跑完”的简单服务，而是支持显式任务状态机和文件级取消控制的。

### 3.2 多格式输入处理

模块二对输入格式做了专门分层，覆盖 PDF、Word、Excel、纯文本、Markdown、图片等多类文档：

- PDF：`core/pdf/*`
- Word / Office：`core/format/docx_*`、`core/format/office_pdf.py`、`core/format/word_input_preparation_runtime.py`
- Excel：`core/format/xlsx_runtime.py`、`core/format/xlsx_artifact_io.py`
- TXT / MD / 纯文本：`core/format/plain_text_parser.py`
- 图片：`core/format/image_document_runtime.py`
- 通用非 PDF 预算与内容抽取：`core/format/nonpdf_*`

这里的重点不是“支持打开这些格式”，而是针对不同输入使用不同解析策略：

- PDF 有原生解析与视觉解析双链路
- Word 既支持原生内容增强，也支持转 PDF 后走视觉链路
- Excel 不只是读取文本，还会生成工作簿 / sheet / 表格 artifact
- TXT / MD 会做标题、键值、列表、表格、图像 cue 的文本级解析

### 3.3 视觉优先与表格理解

模块二非常强调“视觉语义”能力，代码上主要体现在以下目录：

- `core/visual/*`
- `core/table/*`
- `core/pdf/pdf_visual_parse_runtime.py`
- `core/integration/mineru_layout.py`
- `core/integration/gemini_native_transport_runtime.py`

它并不是只做 OCR，而是在视觉层面拆成多个阶段：

1. 页面版面 / ROI / object 规划
2. 表格区域检测与表头处理
3. 图像 / 图表对象抽取
4. Gemini / Vision 请求与响应归一化
5. 视觉结果落回结构化 extraction graph

这也是为什么模块二能输出的不只是字段，还包括：

- 表格截图
- 图表摘要
- 图片说明
- trace hit artifact
- 原文定位结果

### 3.4 Schema 推理与结构化抽取

模块二不是把文档内容“原样返回”，而是围绕 schema 做结构化抽取。相关代码集中在：

- `services/schema/*`
- `core/schema/*`
- `assets/*.json`
- `agent/graph.py`
- `core/pipeline/extraction_graph_runtime.py`

这一层做的事情包括：

- schema primitives 与 request bundle 组织
- schema selection / semantics / resolution
- field naming 与字段类型规则
- 内容归一化与 reference 对齐
- 低质量自动 schema 结果过滤
- 提取图运行与质量快照

也就是说，模块二实际上包含一套“文档抽取 schema 引擎”，不是把大模型回答直接当最终结果。

### 3.5 质量门控、降级与恢复

模块二代码里非常明显的一条设计原则是：允许复杂链路，但必须配套降级与恢复。

关键代码：

- `core/pipeline/document_parse_recovery_runtime.py`
- `core/pipeline/document_postprocess_runtime.py`
- `core/format/nonpdf_budget_runtime.py`
- `core/format/docx_native_recovery_runtime.py`
- `core/integration/cached_extraction_restore_runtime.py`
- `services/extraction/quality_builder.py`
- `services/extraction/quick_extract_builder.py`

它处理的问题包括：

- 视觉解析超时后的回退
- 非 PDF 文档的预算压缩
- Word 转换失败后的策略决策
- 快速表格 fallback 的过滤与质量门
- 缓存恢复与 runtime 级复用

这让模块二更像一个“工业级抽取工作流”，而不是一次性脚本。

### 3.6 预览、artifact 与 trace 溯源

模块二的另一个核心能力，是把“抽取结果”和“原文证据”重新连接起来。

对应代码：

- `core/artifact_runtime.py`
- `core/summary_runtime.py`
- `services/document/tools.py`
- `runtime/document_trace_hits_runtime.py`
- `runtime/document_trace_runtime.py`
- `services/preview/office.py`
- `runtime/xlsx_workbook_artifact_runtime.py`

这一层提供：

- Office 预览 PDF 生成
- artifact 文件写入与 URL 映射
- trace locate
- summarize
- xlsx workbook / sheet artifact 读取
- 表格 / 图片 /图表 trace 支撑

这也是模块二前端能做“点击字段 -> 回到原文位置”的后端基础。

### 3.7 Assistant 1 文档助手

模块二内部带了一套相对独立的文档助手子系统 `assistant_1/`，它不是简单聊天包装，而是一套带检索、工具路由、SQL、Web Search 的 grounded assistant。

核心组件：

- 运行时：`assistant_1/agent_runtime.py`
- 输入/输出模型：`assistant_1/api_models.py`
- 检索：`assistant_1/retrieval_pipeline.py`、`assistant_1/retrieval_reranker.py`
- 知识单元构建：`assistant_1/knowledge_units.py`、`assistant_1/ingest_pipeline.py`
- 向量存储：`assistant_1/pgvector_store.py`
- 工具路由：`assistant_1/tool_router.py`
- SQL 能力：`assistant_1/sql/*`、`assistant_1/sql_tools.py`
- Web Search：`assistant_1/tavily_client.py`、`assistant_1/web_search_strategy.py`
- 流式输出：`assistant_1/streaming.py`、`assistant_1/stream_runtime.py`

助手工具定义显示它至少支持：

- `search_knowledge_base`
- `search_knowledge_base_grouped`
- `ingest_document`
- `web_search_tavily`
- `inspect_database_schema`
- `design_schema_draft`
- `draft_sql_from_nl`

因此模块二的助手不是附属件，而是一个文档知识交互层。

### 3.8 模块四同步

模块二和模块四之间不是前端直接桥接，而是模块二后端在抽取完成后向模块四递送文档。

对应代码：

- `core/integration/module4_sync_config_runtime.py`
- `core/integration/module4_sync_metrics_runtime.py`
- `core/integration/module4_sync_outbox_runtime.py`
- `core/integration/module4_sync_task_runtime.py`
- `repositories/module4_sync_outbox_repository.py`
- `api/v1/endpoints/sync.py`
- `api/v1/endpoints/module4_sync.py`

它的设计重点是：

- Outbox 持久化
- 重试与失败标记
- 同步指标统计
- 后台递送

这意味着模块二已经具备比较成熟的“解析完成 -> 可入图谱文档 -> 异步投递”闭环。

## 4. 端到端主链路

模块二的完整链路可以概括为：

1. API 层接收上传、校验 schema、读取文件流
2. `module2_request_runtime` 规范化请求头、schema、缓存清理 scope
3. `module2_execution_facade` 选择执行模式
4. 进入 `services/extraction/*` 组装的 workflow bundle
5. `core/pipeline/*` 决定输入预算、解析会话、fallback、graph 执行
6. `core/format/*`、`core/pdf/*`、`core/visual/*`、`core/table/*` 执行格式解析
7. `core/schema/*` 和 extraction graph 生成结构化结果
8. `document_postprocess_runtime` 做质量门控、artifact 上下文与最终响应整理
9. `summary_runtime` / `document tools` 提供摘要与原文定位
10. `assistant_1` 消费抽取产物做文档问答
11. `module4_sync_outbox_runtime` 在需要时把结果投递给模块四

## 5. 模块二的 API 面

### 5.1 抽取与支持接口

- `GET /healthz`
- `POST /extract/jobs/create`
- `GET /extract/jobs/status/{job_id}`
- `POST /extract/jobs/{job_id}/cancel-file`
- `POST /extract/batch`
- `POST /extract/preview/office/start`
- `GET /extract/preview/office/status/{job_id}`
- `POST /extract/summarize`
- `POST /extract/trace/locate`
- `POST /extract/cache/clear`

### 5.2 助手接口

- `POST /extract/assistant1/chat/stream`
- `GET /extract/assistant1/sessions/{session_id}`
- 兼容聊天接口：`GET /api/chat/health`、`POST /api/chat`

### 5.3 模块四同步接口

- `GET /module4-sync/outbox`
- `GET /module4-sync/outbox/{outbox_id}`

## 6. 存储与状态管理

模块二底层的 `db/storage.py` 显示它至少落库或缓存了以下对象：

- 文档 extraction 缓存
- recent document caches
- assistant session / message / tool invocation
- graph sync outbox
- 字段 staging 表
- 表格 staging 表

重要特征：

- PostgreSQL 可用时走数据库
- 数据库不可用时可降级到内存模式
- 但内存模式只适合开发，不适合作为正式运行形态

这也解释了模块二为什么既能做缓存命中，又能做多轮助手会话，还能做模块四同步恢复。

## 7. 模块二的核心特点

### 特点一：不是单格式解析器，而是多格式统一抽取平台

模块二同时容纳了 PDF、Word、Excel、文本、图片五条主要输入链路，并通过统一的 extraction graph 与 postprocess 把结果收敛到同一输出形态。

### 特点二：不是单一路径，而是“原生解析 + 视觉增强 + fallback 恢复”的组合式架构

从 `core/format`、`core/pdf`、`core/visual` 到 `document_parse_recovery_runtime` 可以看出，模块二被设计成允许复杂链路失败，但必须给出恢复路径和质量降级说明。

### 特点三：前端体验能力很强，因为后端内建了 preview / artifact / trace 支撑

模块二不仅返回字段值，还返回预览、artifact、定位、摘要、图表/表格/图片信息，这是它能支撑复杂工作台前端的关键。

### 特点四：assistant_1 让模块二从“抽取工具”升级成“文档工作台”

助手子系统拥有检索、向量存储、SQL、schema 设计、Web Search 能力，使模块二不仅能出结果，还能围绕结果做交互。

### 特点五：代码中保留了大量兼容层，说明它正处在迁移与标准化阶段

`bootstrap/*`、`runtime/*`、`composition/*`、`module2_*_runtime.py` 这些目录表明：模块二并不是从零设计的纯净系统，而是在兼容旧链路、抽离 bundle、接入统一后端的过程中逐步演化出来的。

## 8. 关键源码文件讲解

| 文件 | 作用 |
| --- | --- |
| `composition/application.py` | 模块二 FastAPI 应用装配中心，把 foundation / repository / support / platform / service / workflow bundle 组装成可运行服务。 |
| `core/config.py` | 抽取超时、并发、执行模式、Office 转换、模块四同步等环境变量入口。 |
| `core/module2_execution_facade.py` | 决定抽取是走 subprocess worker、upstream，还是自动回退。 |
| `core/module2_request_runtime.py` | 处理 schema JSON、上传文件读取、上下文 header 转发、cache clear scope。 |
| `services/extraction/extraction_builder.py` | 生成主抽取 bundle，是 extraction runtime 指纹和逻辑拼装核心。 |
| `services/extraction/request.py` | 抽取请求服务入口，承接 API 对 extraction runtime 的调用。 |
| `services/extraction/executor.py` | 任务执行服务，负责把文件级工作流真正跑起来。 |
| `core/pipeline/document_flow_runtime.py` | 文档执行与工作流组织核心。 |
| `core/pipeline/document_pipeline_runtime.py` | 输入计划、解析会话、schema bundle、graph bundle 的中枢。 |
| `core/pipeline/document_postprocess_runtime.py` | 质量门控、artifact 构造、最终响应整理。 |
| `core/format/office_pdf.py` | Office 到 PDF 预览转换、缓存、singleflight 与 backend 顺序控制。 |
| `core/summary_runtime.py` | 摘要和 trace locate 的核心实现。 |
| `services/document/tools.py` | trace 语义、定位 payload、多态链接支持。 |
| `services/preview/office.py` | Office 预览任务服务。 |
| `assistant_1/agent_runtime.py` | 文档助手主运行时。 |
| `assistant_1/tool_router.py` | 工具能力路由层，定义知识库检索、入库、Web Search、SQL 等工具。 |
| `assistant_1/retrieval_pipeline.py` | 基于向量检索做文档知识召回。 |
| `db/storage.py` | 模块二持久化核心，覆盖缓存、助手会话、outbox、staging 等。 |

## 9. 源码目录清单（按目录分组）

### 9.1 Python 源文件

```text
[.]
__init__.py, main.py

[agent]
graph.py

[api]
__init__.py, deps.py, router.py

[api/endpoints]
__init__.py, assistant.py, extraction.py

[api/v1]
__init__.py, router_bundle.py

[api/v1/endpoints]
__init__.py, extraction_assistant.py, extraction_request.py, extraction_support.py, module4_sync.py, sync.py

[assistant_1]
__init__.py, agent_runtime.py, answer_contracts.py, api_models.py, bundle_builder.py, chat_completions_codec.py, config.py, embedder_gemini.py, frontend_grounding.py, ingest_pipeline.py, intent_router.py, knowledge_units.py, markdown_cleaner.py, markdown_renderer.py, matcher.py, models.py, path_resolver.py, persistence.py, pgvector_store.py, prompt_blocks.py, ref_table_parser.py, response_planner.py, responses_provider.py, retrieval_pipeline.py, retrieval_reranker.py, source_loader.py, sql_tools.py, stream_feedback.py, stream_runtime.py, streaming.py, task_policy.py, tavily_client.py, text_utils.py, tool_router.py, warmup_runtime.py, web_search_strategy.py

[assistant_1/scripts]
build_bundle.py, chat_agent.py, chat_stream.py, ingest_document.py, query_vector.py

[assistant_1/sql]
__init__.py, common.py, drafting.py, execution.py, introspection.py, schema_design.py

[bootstrap]
__init__.py, document_io.py, document_io_builder.py, entry.py, entry_builder.py, extraction.py, extraction_builder.py, foundation.py, foundation_builder.py, geometry.py, geometry_builder.py, nonpdf.py, nonpdf_builder.py, platform.py, platform_builder.py, policy.py, policy_builder.py, progress.py, progress_builder.py, quality.py, quality_builder.py, quick_extract.py, quick_extract_builder.py, result_filter.py, result_filter_builder.py, schema_context.py, schema_context_builder.py, schema_fields.py, schema_fields_builder.py, schema_inference.py, schema_inference_builder.py, schema_llm.py, schema_llm_builder.py, schema_pipeline.py, schema_pipeline_builder.py, schema_primitives.py, schema_primitives_builder.py, schema_resolution.py, schema_resolution_builder.py, schema_selection.py, schema_selection_builder.py, schema_semantics.py, schema_semantics_builder.py, service.py, service_builder.py, support.py, support_builder.py

[composition]
__init__.py, app_callback_bundle.py, application.py, cache_clear.py, foundation.py, http_runtime_bundle.py

[core]
__init__.py, artifact_runtime.py, assistant1_runtime.py, assistant1_upstream_runtime.py, cache_runtime.py, config.py, layout_mineru.py, llm_provider.py, module2_compat_worker.py, module2_execution_facade.py, module2_request_runtime.py, module2_shadow_runtime.py, module2_sidecar_runtime.py, module2_upstream_runtime.py, module2_worker_runtime.py, parser.py, summary_runtime.py

[core/format]
__init__.py, docx_document_runtime.py, docx_enrichment.py, docx_native_recovery_runtime.py, image_document_runtime.py, nonpdf_budget_runtime.py, nonpdf_content_runtime.py, office_pdf.py, plain_text_parser.py, word_input_preparation_runtime.py, xlsx_artifact_io.py, xlsx_runtime.py

[core/integration]
__init__.py, app_support_runtime.py, artifact_file_runtime.py, cached_extraction_restore_runtime.py, gemini_native_transport_runtime.py, mineru_layout.py, mineru_warmup_runtime.py, module2_bootstrap_runtime.py, module4_sync_config_runtime.py, module4_sync_metrics_runtime.py, module4_sync_outbox_runtime.py, module4_sync_task_runtime.py

[core/parsers]
__init__.py, native_document_parser.py, parser_bootstrap_runtime.py, parser_config_runtime.py, parser_document_table_bootstrap_runtime.py, parser_docx_bootstrap_runtime.py, parser_image_bootstrap_runtime.py, parser_initialization_runtime.py, parser_pdf_bootstrap_runtime.py, parser_semantic_bootstrap_runtime.py, parser_state_runtime.py, parser_vision_transport_bootstrap_runtime.py, parser_visual_context_bootstrap_runtime.py, parser_visual_execution_bootstrap_runtime.py, parser_visual_payload_bootstrap_runtime.py

[core/pdf]
__init__.py, ocr_engine_runtime.py, pdf_fitz_table_runtime.py, pdf_native_parse_runtime.py, pdf_ocr_runtime.py, pdf_parse_runtime.py, pdf_visual_parse_runtime.py, pdf_visual_profile.py

[core/pipeline]
__init__.py, block_index_runtime.py, document_flow_runtime.py, document_parse_recovery_runtime.py, document_pipeline_runtime.py, document_pipeline_stages_runtime.py, document_postprocess_runtime.py, document_process_pool_runtime.py, extraction_graph_runtime.py, stream_router_runtime.py

[core/schema]
__init__.py, content_normalization_runtime.py, field_naming.py, prompt_assets.py, reference_runtime.py, schema_rule_assets.py, schema_session_runtime.py

[core/table]
__init__.py, ocr_table_inference.py, ocr_table_utils.py, table_header_runtime.py, table_merge_runtime.py, table_metadata.py, table_payload_runtime.py, table_pruning_runtime.py, table_vision_payload.py

[core/visual]
__init__.py, figure_inference.py, figure_semantics.py, figure_vision_payload.py, roi_cropper.py, vision_extractor.py, vision_request_runtime.py, vision_response_runtime.py, visual_execution_runtime.py, visual_parse_orchestrator.py, visual_payload_builder.py, visual_pdf_bootstrap.py, visual_planning_runtime.py

[db]
storage.py

[domain]
__init__.py

[integrations]
__init__.py

[integrations/llm]
__init__.py, provider.py

[integrations/module4]
__init__.py

[integrations/office]
__init__.py

[integrations/search]
__init__.py

[repositories]
__init__.py, assistant_session_repository.py, bundle.py, extraction_cache_repository.py, module4_sync_outbox_repository.py, runtime_state_repository.py

[resources]
__init__.py, paths.py

[runtime]
__init__.py, app_callback_bundle.py, artifact_support_runtime.py, cache_clear.py, document_trace_hits_runtime.py, document_trace_runtime.py, extraction_executor.py, extraction_jobs.py, extraction_requests.py, http_runtime_bundle.py, main_document_io_bundle.py, main_entry_bundle.py, main_extraction_bundle.py, main_foundation_bundle.py, main_geometry_bundle.py, main_nonpdf_bundle.py, main_platform_bundle.py, main_policy_bundle.py, main_progress_bundle.py, main_quality_bundle.py, main_quick_extract_bundle.py, main_result_filter_bundle.py, main_schema_context_bundle.py, main_schema_fields_bundle.py, main_schema_inference_bundle.py, main_schema_llm_bundle.py, main_schema_pipeline_bundle.py, main_schema_primitives_bundle.py, main_schema_resolution_bundle.py, main_schema_selection_bundle.py, main_schema_semantics_bundle.py, main_service_bundle.py, main_support_bundle.py, main_workflow_bundle.py, module4_sync_callback_bundle.py, office_preview.py, sync_callback_bundle.py, xlsx_workbook_artifact_runtime.py

[schemas]
__init__.py, assistant.py, cache.py, contracts.py, extraction.py, summarize.py, trace.py

[services]
__init__.py, assistant_service.py, document_tools_service.py, extraction_executor_service.py, extraction_job_service.py, extraction_request_service.py, extraction_service.py, office_preview_service.py

[services/document]
__init__.py, tools.py

[services/extraction]
__init__.py, document_io_builder.py, entry_builder.py, executor.py, extraction_builder.py, foundation_builder.py, geometry_builder.py, job.py, nonpdf_builder.py, platform_builder.py, policy_builder.py, progress_builder.py, quality_builder.py, quick_extract_builder.py, request.py, service_builder.py, support_builder.py, workflow_builder.py

[services/preview]
__init__.py, office.py

[services/schema]
__init__.py, result_filter_builder.py, schema_context_builder.py, schema_fields_builder.py, schema_inference_builder.py, schema_llm_builder.py, schema_pipeline_builder.py, schema_primitives_builder.py, schema_resolution_builder.py, schema_selection_builder.py, schema_semantics_builder.py

[utils]
__init__.py
```

### 9.2 规则 / 配置 / 依赖资产

```text
assistant_1/sql/001_assistant1_pgvector.sql
assets/field_naming_rules_v1.json
assets/field_type_rules_v1.json
assets/schema_coverage_profiles_v1.json
assets/schema_noise_rules_v1.json
assets/schema_selection_rules_v1.json
assets/schema_semantic_rules_v1.json
README.md
requirements.txt
```

