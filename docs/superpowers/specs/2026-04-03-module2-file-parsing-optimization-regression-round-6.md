# Module2 文件解析优化回归 Round 6

## 本轮目标

补齐 `md/txt` 领域模板的规则激活链路，并解决“规则字段已经命中，但最终 auto schema 仍被脏 heuristic 字段挤占”的问题。

本轮聚焦的真实问题样本：

- `datasets/md/2023年文化和旅游发展统计公报.md`
- `datasets/md/第三次全国工业普查主要数据公报.md`
- `datasets/txt/2024年药品流通行业运行统计分析报告.txt`

同步补齐但暂未单独做真实样本回归的模板：

- `human_resources_social_security_report`

## 根因拆解

### 第一层根因

`backend/module2/app/assets/schema_selection_rules_v1.json` 中的 `rule_candidate_templates` 缺少以下 plain-text 模板：

- `culture_tourism_statistical_bulletin`
- `industrial_census_bulletin`
- `pharmaceutical_distribution_report`
- `human_resources_social_security_report`

导致 `resolve_effective_schema()` 在这些模板下不会启用 `infer_rule_backed_schema_fields(...)`，即使 `field_naming_rules_v1.json` 里已经定义了领域规则，最终仍主要依赖 heuristics。

### 第二层根因

补齐规则入口后，规则字段已经进入最终链路，但 `resolve_effective_schema()` 仍会继续把 heuristic 候选并入候选池。

对于 `md/txt` 的领域模板文档，如果规则字段数量已经达到该模板的稳定目标，继续引入 heuristics 只会把这些“补位字段”带回来：

- `年末全国平均每 群众文化设施建筑面积`
- `平均每 公共图书馆建筑面积`
- `在 中（总体）`

这类字段的共同问题不是“没有数值意义”，而是“字段名已经退化/破碎，不应该进入最终 schema”。

## 落地修改

### 1. 补齐 plain-text 模板规则激活入口

文件：

- `backend/module2/app/assets/schema_selection_rules_v1.json`

新增到 `rule_candidate_templates`：

- `culture_tourism_statistical_bulletin`
- `industrial_census_bulletin`
- `pharmaceutical_distribution_report`
- `human_resources_social_security_report`

### 2. 对规则已足够丰富的 plain-text 模板，停止 heuristic 补位

文件：

- `backend/module2/app/runtime/main_schema_resolution_bundle.py`

新增策略：

- 当文件是 `txt/md/markdown`
- 且已经识别出明确 `template_hint`
- 且该模板的 `rule_fields` 数量已经达到 `_deterministic_schema_target(...)`

则：

- 不再把 `heuristic_fields` 并入最终 schema 候选池

这样做的目的：

- 保住领域规则主导的稳定 schema
- 防止弱 heuristic 把退化字段名重新塞回最终输出
- 不影响 `common_document`
- 不影响 `xlsx/table_heavy`
- 不影响规则字段不足时的 heuristic 补充能力

## 回归测试

### 新增/增强测试

文件：

- `backend/module2/tests/test_plain_text_schema_and_extraction.py`

新增覆盖：

- `culture_tourism_statistical_bulletin` 端到端 schema 解析
- `industrial_census_bulletin` 端到端 schema 解析
- `pharmaceutical_distribution_report` 端到端 schema 解析
- `human_resources_social_security_report` 规则激活校验

### 本轮执行通过的测试

在 `2026-04-03` 本地执行通过：

- `backend/module2: pytest tests/test_plain_text_schema_and_extraction.py`
- `backend: pytest tests/test_module2_field_naming_rule_inference.py`
- `backend: pytest tests/test_module2_main_schema_resolution_bundle.py`
- `backend/module2: pytest tests/test_xlsx_schema_and_prefill.py`
- `backend: pytest tests/test_module2_main_schema_pipeline_bundle.py`

## 真实样本回归结果

### 1. 文化和旅游统计公报

文件：

- `datasets/md/2023年文化和旅游发展统计公报.md`

模板识别：

- `culture_tourism_statistical_bulletin`

规则字段数：

- `7`

最终字段：

- `国内观众人次`
- `演出场次`
- `发布日期`
- `文化和旅游单位数量`
- `艺术表演团体数量`
- `演出收入`
- `文化和旅游单位从业人员`

说明：

- 之前会混入 `年末全国平均每 群众文化设施建筑面积`
- 之前会混入 `平均每 公共图书馆建筑面积`
- 当前最终 schema 已被规则字段稳定占满

### 2. 工业普查公报

文件：

- `datasets/md/第三次全国工业普查主要数据公报.md`

模板识别：

- `industrial_census_bulletin`

规则字段数：

- `6`

最终字段：

- `工业从业人员`
- `工业企业和工业生产单位数量`
- `工业产品销售收入`
- `工业增加值`
- `工业总产值`
- `资产总额`

说明：

- 之前会混入 `在 中（总体）`
- 当前最终 schema 已回到领域主指标集合

### 3. 药品流通统计分析报告

文件：

- `datasets/txt/2024年药品流通行业运行统计分析报告.txt`

模板识别：

- `pharmaceutical_distribution_report`

规则字段数：

- `8`

最终字段：

- `平均毛利率`
- `七大类医药商品销售总额`
- `药品批发市场销售额`
- `药品零售市场销售额`
- `主营业务收入`
- `利润总额`
- `执业药师人数`
- `应收账款回款天数`

说明：

- 长物流/电商统计句没有再污染最终字段集

## 影响评估

### 正向收益

- plain-text 领域模板开始真正走规则链路
- 规则足够丰富时，最终 schema 更稳定
- 文化旅游、公报统计、医药流通三类文本字段明显更干净
- 不再因为 heuristic 补位把破碎字段名带回最终输出

### 风险控制

本轮策略只在以下场景触发：

- `txt/md/markdown`
- 有明确领域模板
- 规则字段数量已达到模板稳定目标

因此不会影响：

- `common_document`
- `xlsx` 规则补全
- 表格重文档
- 规则字段数量不足时的 heuristic 兜底

## 下一步建议

下一刀最适合继续做的是“plain-text 领域模板的规则覆盖面扩展”，重点不是再调选择器，而是继续补充模板级字段规则本身：

- `culture_tourism_statistical_bulletin`
  - 可追加图书馆/群众文化机构的高价值指标规则
- `industrial_census_bulletin`
  - 可追加税金、利润、资产负债类规则
- `pharmaceutical_distribution_report`
  - 可追加物流、电商、费用率、净利润率等规则

这样后续如果你把 `max_auto_fields` 调大，新增出来的字段也会继续保持“规则主导”，而不是重新回到 heuristic 噪声。
