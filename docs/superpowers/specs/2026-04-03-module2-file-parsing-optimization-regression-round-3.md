## Module 2 File Parsing Optimization Regression Round 3

Date: 2026-04-03

Status: passed for scope-neutral government bulletin label unification

### Scope

This round focuses on semantic cleanup for `government_statistical_bulletin`
fields after round 2.

Goal:

- remove remaining national-scope wording from canonical labels when the field
  concept is actually cross-scope and should be reusable across national and
  local bulletins

### Why this round was needed

After round 2, local bulletins were already better, but some labels still
carried national wording such as:

- `全国居民人均可支配收入`
- `全国一般公共预算收入`
- `年末全国人口`
- `国内生产总值`
- `人均国内生产总值`

These labels were usable, but they were not ideal for:

- local government statistical bulletins
- downstream schema stability
- future packaging and field comparison

### Landed Changes

Files:

- `backend/module2/app/assets/field_naming_rules_v1.json`
- `backend/module2/app/core/schema/field_naming.py`
- `backend/tests/test_module2_field_naming_rule_inference.py`

Version bump:

- `field-naming-rules-v1.7`

#### Canonical labels unified to scope-neutral form

Updated government bulletin labels:

- `国内生产总值` -> `生产总值`
- `人均国内生产总值` -> `人均生产总值`
- `年末全国人口` -> `年末人口`
- `全国一般公共预算收入` -> `一般公共预算收入`
- `全国居民人均可支配收入` -> `居民人均可支配收入`

Important note:

- aliases were preserved, so existing source text such as `国内生产总值`,
  `地区生产总值`, `全国居民人均可支配收入` can still match correctly
- this is a semantic cleanup of canonical output, not a recall reduction

### Automated Test Results

#### Root-level tests

Command:

```powershell
pytest backend/tests/test_module2_main_nonpdf_bundle.py `
  backend/tests/test_module2_plain_text_parser.py `
  backend/tests/test_module2_field_naming_rule_inference.py `
  backend/tests/test_module2_main_schema_pipeline_bundle.py
```

Result:

- `16 passed`

#### Module 2 regression subset

Working directory:

- `backend/module2`

Command:

```powershell
pytest tests/test_plain_text_schema_and_extraction.py `
  tests/test_xlsx_schema_and_prefill.py `
  tests/test_visual_schema_inference.py
```

Result:

- `18 passed`

### Real Dataset Regression

Validated files:

- `datasets/md/2023年文化和旅游发展统计公报.md`
- `datasets/md/2024年卫生健康事业发展统计公报.md`
- `datasets/md/第三次全国工业普查主要数据公报.md`
- `datasets/txt/2024年国民经济和社会发展统计公报（节选）.txt`
- `datasets/txt/2024年药品流通行业运行统计分析报告.txt`
- `datasets/txt/合肥市2024年国民经济和社会发展统计公报.txt`

### Key Real Regression Outcome

#### National bulletin now uses scope-neutral canonical labels

`datasets/txt/2024年国民经济和社会发展统计公报（节选）.txt`

Current recalled fields include:

- `城镇调查失业率`
- `常住人口城镇化率`
- `居民人均可支配收入`
- `一般公共预算收入`
- `人均生产总值`
- `生产总值`
- `年末人口`

#### Local bulletin now uses the same stable label family

`datasets/txt/合肥市2024年国民经济和社会发展统计公报.txt`

Current recalled fields include:

- `常住人口城镇化率`
- `户籍人口`
- `居民人均可支配收入`
- `一般公共预算收入`
- `生产总值`
- `人均生产总值`
- `常住人口`

### Assessment

This round improves semantic consistency without reducing functional coverage.

Confirmed benefits:

- national and local bulletins now map to the same reusable field vocabulary
- local bulletins no longer receive obviously nationalized labels
- no regression was observed in culture/tourism, healthcare, industrial census,
  pharma report, `xlsx`, or visual schema inference validation

### Recommended Next Step

Best next move after round 3:

- continue to `xlsx/native` structured extraction strengthening
- keep the current government bulletin semantic set stable for now
- only revisit bulletin labels again if a real downstream conflict appears
