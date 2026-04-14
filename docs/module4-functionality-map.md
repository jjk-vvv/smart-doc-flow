# Module 4 完整功能地图

## 1. 遍历范围与阅读口径

这份文档基于对 `backend/app/modules/module4` 的逐文件遍历整理而成，重点覆盖：

- `58` 个 Python 源文件
- `1` 个 SQL 初始化脚本
- `12` 个 GraphRAG Prompt 模板
- 模块自带 `README.md` 与 `requirements.txt`

本次分析排除了：

- `__pycache__/`
- `workspaces/`

这里排除 `workspaces/` 的原因很重要：该目录存放的是模块四的工作空间、索引产物、lancedb、报告和缓存，它们体现“运行结果”，不等于“模块四源码能力”。

## 2. 模块定位

模块四是项目中的“知识图谱与风险智能层”。如果说模块二负责把文档解析成结构化内容，那么模块四负责把这些结构化结果继续提升成：

- 文件级图谱
- 图查询
- GraphRAG 问答
- 风险规则命中
- 告警与证据
- Explain / Simulate 智能分析
- Neo4j 下游投影

从 README 和运行时代码可以明确看出，模块四已经被设计成“GraphRAG-first”的图谱服务，而不是一个普通的图数据库 API。

## 3. 模块四能做什么

### 3.1 接收模块二或文本语料的图谱入库请求

模块四不再接受原始文件直接上传，而是只接受：

- 模块二同步过来的 `documents[]`
- 直接提供的 `text_corpus`
- `source_texts[]` 聚合文本

核心代码：

- `api/v1/endpoints/module4.py`
- `core/application.py`
- `services/ingestion/runtime.py`
- `services/ingestion/text_corpus.py`

这说明模块四的前提是“输入内容已经是可入图的文本 / 文档抽取结果”，它不是模块二的替代品，而是模块二之后的图谱增强层。

### 3.2 创建工作空间并运行 GraphRAG

模块四的图谱构建主线是：

1. 构建 workspace
2. 写入 settings / env / source 文件
3. 调用 GraphRAG indexer
4. 校验 artifacts
5. 导入图谱数据

关键代码：

- `services/graphrag/workspace.py`
- `services/graphrag/indexer.py`
- `services/graphrag/validator.py`
- `services/graphrag/importer.py`
- `services/graphrag/prompts.py`

这表示模块四并不是直接把节点边写进数据库，而是先走一条标准化 GraphRAG artifact 生产链，再把结果导入自己的存储模型。

### 3.3 图谱导入与文件级图版本管理

模块四在 `db/storage.py` 中维护了完整的图谱状态模型：

- ingest job
- ingest batch
- graph file
- graph version
- document
- node
- edge
- evidence
- alert
- rule

这意味着模块四不是一张“大图”粗暴叠加，而是明确做了：

- 租户隔离
- 文件级 graph scope
- active version / version history
- 证据与告警绑定

### 3.4 Graph 查询与 GraphRAG 搜索

模块四对外既支持“结构化图查看”，也支持“GraphRAG 搜索”。

图查询相关：

- 文件列表：`/module4/graph/files`
- 文件详情：`/module4/graph/files/{file_hash}`
- 文件图视图：`/module4/graph/files/{file_hash}/view`
- 文件邻域：`/module4/graph/files/{file_hash}/neighborhood/{node_id}`
- 文件节点详情：`/module4/graph/files/{file_hash}/node/{node_id}`
- 全局图：`/module4/graph`
- 全局邻域：`/module4/graph/neighborhood/{node_id}`

GraphRAG 查询相关：

- `POST /module4/query/search`

对应代码：

- `services/graphrag/query_service.py`
- `services/graphrag/query_adapter.py`
- `services/query/runtime.py`

这里的重点是：查询依赖的是 GraphRAG artifacts，而不是传统数据库 fallback。README 已明确指出：query runtime 已经是 artifact-only。

### 3.5 风险规则、告警与证据

模块四不只是“看图”，还提供“规则命中 -> 告警 -> 证据”的风险智能能力。

关键代码：

- `services/ingestion/rules.py`
- `schemas/rules.py`
- `schemas/alerts.py`
- `schemas/evidence.py`
- `services/query/runtime.py`
- `db/storage.py`

默认规则在 `db/storage.py` 中可见，包括：

- `RULE_LOW_CONFIDENCE`
- `RULE_DOC_ERRORS`
- `RULE_QUALITY_DEGRADED`
- 若干业务语义信号规则

这说明模块四把模块二的质量信息、错误信息、字段置信度都提升成了规则引擎可消费的风险上下文。

### 3.6 Explain / Simulate

模块四还内建了分析型接口：

- `POST /module4/explain`
- `POST /module4/simulate`

对应代码：

- `services/insights/runtime.py`

能力包括：

- 对告警做解释
- 对节点做解释
- 基于上下文和规则做模拟命中
- 输出 reasoning steps 与 evidence

这让模块四不只是图谱存储服务，而是具备“分析与推演”能力。

### 3.7 Neo4j 下游投影

模块四支持把已经 ready 的文件图谱向 Neo4j 下游投影。

对应代码：

- `services/query/neo4j.py`
- `core/application.py`
- `core/app_runtime.py`

这个投影是 best-effort：

- 主入库成功不依赖 Neo4j 一定成功
- Neo4j 不可用不会打断主 ingest 成功路径
- 但会记录 projection 状态与失败原因

### 3.8 Sidecar 与运行时探测

模块四有一套比较完整的 runtime readiness / upstream probe 体系：

- `core/module4_sidecar_runtime.py`
- `core/app_runtime.py`
- `api/endpoints/gateway.py`
- `healthz` deep / basic probe

这说明模块四不仅关注业务逻辑，也关注运行环境是否满足 GraphRAG 与 Neo4j 的执行前提。

## 4. 端到端主链路

模块四的标准运行主线可以概括为：

1. API 收到 ingest 请求
2. storage 创建 ingest batch 与 job
3. ingestion runtime 过滤 graph-eligible 文件或合成 text corpus 文档
4. workspace builder 生成每个文件的工作空间
5. text_corpus 组装最终入图文本
6. GraphRAG indexer 执行索引流程
7. validator / importer 校验并导入 artifacts
8. storage 写入 graph file、graph version、nodes、edges、evidence
9. rules engine 生成 alerts
10. 查询层暴露 graph / neighborhood / query / evidence / explain / simulate
11. ready 状态下尝试 Neo4j 投影

## 5. 模块四的 API 面

### 5.1 Gateway 与运行健康

- `GET /gateway/info`
- `GET /gateway/health`
- `GET /gateway/ready`
- `GET /module4/healthz`

### 5.2 Ingest / Rebuild / Job

- `POST /module4/ingest`
- `GET /module4/jobs/{job_id}`
- `POST /module4/rebuild`

### 5.3 图谱文件与图视图

- `GET /module4/graph/files`
- `GET /module4/graph/files/{file_hash}`
- `GET /module4/graph/files/{file_hash}/view`
- `GET /module4/graph/files/{file_hash}/neighborhood/{node_id}`
- `GET /module4/graph/files/{file_hash}/node/{node_id}`
- `GET /module4/graph`
- `GET /module4/graph/neighborhood/{node_id}`

### 5.4 搜索、证据、规则、告警、分析

- `POST /module4/query/search`
- `GET /module4/alerts`
- `POST /module4/alerts/{alert_id}/ack`
- `POST /module4/alerts/{alert_id}/resolve`
- `GET /module4/evidence`
- `GET /module4/evidence/edge/{edge_id}`
- `GET /module4/rules`
- `PUT /module4/rules/{rule_id}`
- `POST /module4/explain`
- `POST /module4/simulate`

## 6. 存储模型与状态管理

`db/storage.py` 是模块四最核心的状态中心，它管理的对象远多于一个普通图数据库写入器：

- Job
- Ingest Batch
- Graph File
- Graph Version
- Document
- Node
- Edge
- Evidence
- Alert
- Rule

几个很关键的特点：

- 模块四采用 strict database mode，数据库不可用时启动失败
- 租户是一级作用域
- 文件 hash 是图谱文件级作用域的关键索引
- Rule / Alert / Evidence 与 graph 数据同处一个统一存储域

## 7. 模块四的核心特点

### 特点一：GraphRAG-first，而不是数据库-first

模块四的设计重心是 GraphRAG workspace、prompt、indexer、artifact validator、artifact importer。这说明它的核心不在“直接写点边”，而在“按 GraphRAG 流程构图并消费产物”。

### 特点二：强调文件级图谱与版本化管理

从 `graph_file`、`graph_version`、`active_version_id` 可以看出，模块四把每个文件都当作可演进的图谱单元，而不是把所有内容揉进一张不可分辨来源的大图。

### 特点三：不仅能建图，还能做风险智能

默认规则、告警、证据、Explain、Simulate 一整套能力说明模块四是“图谱 + 风险分析平台”，不是纯展示层。

### 特点四：与模块二是上下游关系，而不是并列重复关系

README 已明确指出：模块四不直接处理原始上传文件，它依赖模块二的文档抽取结果或等价文本语料。因此两个模块的分工非常清晰：

- 模块二：解析与结构化
- 模块四：图谱化与风险智能

### 特点五：对生产运行更严格

模块四在数据库、runtime readiness、GraphRAG python 环境、Neo4j 投影等方面明显更偏“生产系统约束”，不像模块二那样保留了较多兼容层和开发期降级模式。

## 8. 关键源码文件讲解

| 文件 | 作用 |
| --- | --- |
| `core/application.py` | FastAPI 应用装配中心，负责 job 调度、ingest/rebuild 生命周期和 router 装配。 |
| `core/app_runtime.py` | 模块四运行时总成，封装 tenant、CORS、batch key、query helpers、insight helpers 等。 |
| `db/storage.py` | 模块四的统一持久化核心，承载 job/batch/graph/version/node/edge/evidence/alert/rule。 |
| `api/v1/endpoints/module4.py` | 对外主 API 面，涵盖 ingest、graph、query、alerts、rules、evidence、healthz。 |
| `services/ingestion/runtime.py` | 文档 ingest 主流程、GraphRAG 索引失败分类、部分导入、fallback 与 rebuild 支撑。 |
| `services/ingestion/text_corpus.py` | 将模块二 artifact、文本语料、source_texts 合成为可入图文本。 |
| `services/ingestion/rules.py` | 规则表达式求值与风险分数计算。 |
| `services/graphrag/workspace.py` | 构建 GraphRAG workspace、settings.yaml 与环境文件。 |
| `services/graphrag/indexer.py` | 执行 GraphRAG 索引流程、工作流控制与输出布局识别。 |
| `services/graphrag/importer.py` | 把 GraphRAG artifacts 导入模块四自己的 graph storage。 |
| `services/graphrag/query_service.py` | 执行 local/global/drift/basic 四类 GraphRAG 查询。 |
| `services/graphrag/query_adapter.py` | 读取 artifact snapshot，适配查询和图视图所需结构。 |
| `services/query/runtime.py` | 图查询、节点/边归一化、graph file view、evidence/alert/rule API 支撑。 |
| `services/query/neo4j.py` | 下游 Neo4j 投影逻辑。 |
| `services/insights/runtime.py` | explain 与 simulate 的分析逻辑。 |
| `core/module4_sidecar_runtime.py` | 上游 / sidecar 解析与探测。 |
| `tools/nonpdf_alignment_eval.py` | 针对 datasets 非 PDF 文件做对齐评估的工具脚本。 |

## 9. 源码目录清单（按目录分组）

### 9.1 Python 源文件

```text
[.]
__init__.py, composition.py, main.py

[api]
__init__.py, deps.py, router.py

[api/endpoints]
__init__.py, gateway.py

[api/v1]
__init__.py, router.py

[api/v1/endpoints]
__init__.py, graph.py, module4.py

[core]
__init__.py, app_runtime.py, application.py, module4_sidecar_runtime.py, runtime.py

[db]
__init__.py, storage.py

[domain]
__init__.py

[integrations]
__init__.py

[integrations/graphrag]
__init__.py

[integrations/neo4j]
__init__.py

[repositories]
__init__.py

[resources]
__init__.py

[schemas]
__init__.py, alerts.py, common.py, contracts.py, evidence.py, graph.py, health.py, ingest.py, insights.py, query.py, rules.py

[services]
__init__.py

[services/graphrag]
__init__.py, importer.py, indexer.py, prompts.py, query_adapter.py, query_service.py, settings.py, validator.py, workspace.py

[services/ingestion]
__init__.py, artifacts.py, rules.py, runtime.py, text_corpus.py

[services/insights]
__init__.py, runtime.py

[services/query]
__init__.py, neo4j.py, runtime.py

[tools]
nonpdf_alignment_eval.py
```

### 9.2 Prompt / SQL / 依赖资产

```text
sql/init.sql
assets/prompts/basic_search_system_prompt.txt
assets/prompts/community_report_graph.txt
assets/prompts/community_report_text.txt
assets/prompts/drift_search_reduce_prompt.txt
assets/prompts/drift_search_system_prompt.txt
assets/prompts/extract_claims.txt
assets/prompts/extract_graph.txt
assets/prompts/global_search_knowledge_system_prompt.txt
assets/prompts/global_search_map_system_prompt.txt
assets/prompts/global_search_reduce_system_prompt.txt
assets/prompts/local_search_system_prompt.txt
assets/prompts/question_gen_system_prompt.txt
assets/prompts/summarize_descriptions.txt
README.md
requirements.txt
```

