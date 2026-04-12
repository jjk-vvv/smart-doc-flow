# Module2 File Parsing Optimization Regression Round 4

## Scope

This round continues the `xlsx/native` structured extraction optimization path after the `md/txt` stabilization slices.

Goal:

- keep the current FastAPI + native parser chain unchanged
- improve real Excel schema recall without degrading the existing workflow
- avoid broad code expansion
- make rule-backed `xlsx` fields survive the current capped schema selection flow

## Changes Landed

### 1. Expanded `xlsx` rule-rich schema selection

File:

- `backend/module2/app/assets/schema_selection_rules_v1.json`

Changes:

- added more `rule_candidate_templates` for real `xlsx` domains
- added `xlsx_rule_rich_trigger_count`
- added `xlsx_rule_rich_max_fields`

Effect:

- table-heavy `xlsx` files are no longer always forced back to the base 6-field cap
- when rule-backed signal is strong, the schema can expand up to 12 fields

### 2. Added environment-monitoring domain field coverage

File:

- `backend/module2/app/assets/field_naming_rules_v1.json`

New environment-monitoring fields include:

- `监测时间`
- `城市`
- `区县`
- `站点编码`
- `站点名称`
- `空气质量指数`
- `二氧化硫监测值`
- `二氧化氮监测值`
- `一氧化碳监测值`
- `臭氧监测值`
- `首要污染物`
- `污染类型`

Effect:

- real air-quality monitoring sheets now activate a much richer rule-backed schema set

### 3. Prevented rule-backed fields from being dropped during merge

File:

- `backend/module2/app/runtime/main_schema_resolution_bundle.py`

Changes:

- `xlsx/table_heavy` rich-rule dynamic cap stays active
- `_merge_candidate_sources(...)` now preserves rule-backed generic-looking labels during merge
- low-value filtering is still applied to heuristic and LLM candidates, but no longer mis-removes first-source rule candidates such as `城市`

Effect:

- fixes the previous issue where `城市` was recognized by rules but silently removed before final selection

### 4. Tuned environment-monitoring field priority

File:

- `backend/module2/app/runtime/main_schema_selection_bundle.py`

Changes:

- added `environment_monitoring_report` scoring branch
- boosts contextual fields such as `城市`, `监测时间`, `站点编码`, `站点名称`, `空气质量指数`
- slightly lowers lower-priority descriptive fields under a capped selection window

Effect:

- when the final selection is capped at 12 fields, context-defining fields are retained before lower-priority descriptive fields

### 5. Added regression coverage

File:

- `backend/module2/tests/test_xlsx_schema_and_prefill.py`

New tests:

- rich epidemic sheet should no longer be truncated to the base table cap
- environment-monitoring sheet should activate domain-specific rules and keep the critical contextual fields

## Verification

### Targeted tests

Command:

```powershell
pytest tests/test_xlsx_schema_and_prefill.py
```

Result:

- `10 passed`

### Adjacent regression tests

Command:

```powershell
pytest backend/tests/test_module2_field_naming_rule_inference.py backend/tests/test_module2_plain_text_parser.py backend/tests/test_module2_main_schema_pipeline_bundle.py backend/tests/test_module2_xlsx_runtime.py backend/tests/test_module2_xlsx_parse_runtime.py backend/tests/test_module2_xlsx_table_runtime.py
```

Result:

- `23 passed`

## Real Excel Regression

Dataset:

- `datasets/Excel/*.xlsx`

### 1. `2025山东省环境空气质量监测数据信息.xlsx`

Template:

- `environment_monitoring_report`

Current output:

- `rule_field_count = 13`
- `field_count = 12`

Selected fields:

- `PM10浓度`
- `PM2.5浓度`
- `站点名称`
- `站点编码`
- `空气质量指数`
- `监测时间`
- `城市`
- `一氧化碳监测值`
- `二氧化氮监测值`
- `二氧化硫监测值`
- `臭氧监测值`
- `首要污染物`

Before this round:

- only 6 fields were surfacing
- `城市` was being recognized upstream but lost during merge/filtering

Current assessment:

- major improvement
- contextual dimension fields are now retained
- one lower-priority field such as `污染类型` may still be trimmed under the current 12-field cap

### 2. `COVID-19全球数据集（节选）.xlsx`

Template:

- `epidemic_surveillance_dataset`

Current output:

- `rule_field_count = 9`
- `field_count = 12`

Selected fields:

- `每日检测数`
- `死亡数`
- `病例数`
- `国家/地区`
- `每千人医生数`
- `每千人医院床位数`
- `大洲`
- `日期`
- `65岁及以上人口占比`
- `人均GDP`
- `年平均温度`
- `纬度`

Before this round:

- strong rule hits existed, but final output was still effectively constrained to 6 fields

Current assessment:

- the rich-rule path is working as intended
- core epidemic monitoring fields are now preserved

### 3. `2025年国考职位表（节选）.xlsx`

Template:

- `recruitment_hr_table`

Current output:

- `rule_field_count = 9`
- `field_count = 12`

Selected fields:

- `职位代码`
- `部门代码`
- `招考人数`
- `招考职位`
- `部门名称`
- `面试人员比例`
- `专业`
- `学位`
- `学历`
- `工作地点`
- `政治面貌`
- `机构层级`

Assessment:

- good structured recall
- the schema now covers both key identifiers and recruitment constraints

### 4. `电商销售数据.xlsx`

Template:

- `xlsx_business_ledger`

Current output:

- `rule_field_count = 11`
- `field_count = 12`

Selected fields:

- `订单数`
- `优惠折扣`
- `用户编号`
- `订单编号`
- `订单日期`
- `订单时间`
- `SKU`
- `商品数量`
- `订单来源`
- `订单状态`
- `销售部门`
- `t sale（AF）`

Assessment:

- base ledger coverage is strong
- there is still at least one suspicious dirty or semi-normalized field label: `t sale（AF）`
- this is a good next candidate for targeted cleanup in the business-ledger alias/normalization slice

### 5. `糖尿病患者数据.xlsx`

Template:

- `clinical_patient_dataset`

Current output:

- `rule_field_count = 9`
- `field_count = 12`

Selected fields:

- `就诊ID`
- `住院天数`
- `患者编号`
- `血清葡萄糖最大值`
- `诊断数量`
- `体重`
- `年龄`
- `糖化血红蛋白结果`
- `性别`
- `诊断1`
- `诊断2`
- `诊断3`

Assessment:

- core clinical identifiers and measurement fields are stable
- diagnosis-series fields are still being retained as raw structured outputs, which is acceptable for now

## Conclusion

This round is successful.

What is now confirmed:

- the `xlsx` rich-rule path is functioning on real files
- environment-monitoring sheets no longer collapse to a tiny schema
- epidemic surveillance sheets are no longer truncated to the old 6-field behavior
- the fix did not break the adjacent field-naming, plain-text, or `xlsx` runtime tests

## Recommended Next Slice

Best next step:

- clean business-ledger dirty field labels such as `t sale（AF）`

Reason:

- the structured `xlsx` pipeline is now stable enough
- the next highest-value improvement is not wider recall, but better normalization quality for already-recalled fields
