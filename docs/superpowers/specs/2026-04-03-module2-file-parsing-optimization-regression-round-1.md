## Module 2 File Parsing Optimization Regression Round 1

Date: 2026-04-03

Status: passed for current `md/txt` optimization slice

### Scope

This regression round validates the first landed optimization slice from
`2026-04-03-module2-file-parsing-optimization-implementation-plan.md`.

Current validation focus:

- `MD/TXT` non-PDF profile routing
- domain template detection quality
- rule-backed schema field recall quality
- cross-template leakage prevention
- no regression on `xlsx` and visual schema inference tests

### Landed Changes

#### 1. Non-PDF profile routing refinement

File:

- `backend/module2/app/runtime/main_nonpdf_bundle.py`

Changes:

- added `figure_cue_lines` signal
- prevented `.txt` files from being upgraded to heavier profiles only because
  they contain chart/figure keywords
- `.txt` now upgrades to `mixed` or `chart_heavy` only when table-like
  structure is also present

Expected effect:

- pure text statistical bulletins remain on the light text path
- avoids unnecessary heavy-path follow-up cost

#### 2. Field rule leakage control

File:

- `backend/module2/app/core/schema/field_naming.py`

Changes:

- upgraded ruleset version to `field-naming-rules-v1.6`
- made explicit `templates` on a field rule strict
- a matching pack can support a rule, but can no longer bypass template
  binding

Expected effect:

- government bulletins no longer pick healthcare/environment/recruitment fields
  just because packs overlapped

#### 3. Domain template and field pack expansion

File:

- `backend/module2/app/assets/field_naming_rules_v1.json`

New/strengthened template coverage:

- `government_statistical_bulletin`
- `culture_tourism_statistical_bulletin`
- `industrial_census_bulletin`
- `pharmaceutical_distribution_report`
- `human_resources_social_security_report`

New/strengthened pack coverage:

- `culture_tourism_report`
- `industrial_census_report`
- `pharmaceutical_distribution`
- `human_resources_social_security`

Expected effect:

- current `datasets/md` and `datasets/txt` no longer collapse into generic or
  wrong templates

### Automated Test Results

#### Root-level tests

Command:

```powershell
pytest backend/tests/test_module2_main_nonpdf_bundle.py `
  backend/tests/test_module2_field_naming_rule_inference.py `
  backend/tests/test_module2_plain_text_parser.py
```

Result:

- `11 passed`

#### Module 2 plain text schema tests

Command:

```powershell
pytest tests/test_plain_text_schema_and_extraction.py
```

Working directory:

- `backend/module2`

Result:

- `8 passed`

#### Cross-format protection tests

Command:

```powershell
pytest tests/test_xlsx_schema_and_prefill.py tests/test_visual_schema_inference.py
```

Working directory:

- `backend/module2`

Result:

- `10 passed`

### Real Dataset Regression

Validated files:

- `datasets/md/2023年文化和旅游发展统计公报.md`
- `datasets/md/2024年卫生健康事业发展统计公报.md`
- `datasets/md/第三次全国工业普查主要数据公报.md`
- `datasets/txt/2024年国民经济和社会发展统计公报（节选）.txt`
- `datasets/txt/2024年药品流通行业运行统计分析报告.txt`
- `datasets/txt/合肥市2024年国民经济和社会发展统计公报.txt`

Regression runner checked:

- preflight profile
- plain text parse latency
- detected template
- rule-backed field recall
- table block count
- figure block count

#### Result Summary

| File | Profile | Template | Parse ms | Rule ms | Key Result |
| --- | --- | --- | ---: | ---: | --- |
| `2023年文化和旅游发展统计公报.md` | `text_heavy` | `culture_tourism_statistical_bulletin` | 3.44 | 12.71 | culture/tourism fields recalled correctly |
| `2024年卫生健康事业发展统计公报.md` | `text_heavy` | `healthcare_statistical_bulletin` | 1.25 | 12.63 | healthcare fields remained correct |
| `第三次全国工业普查主要数据公报.md` | `chart_heavy` | `industrial_census_bulletin` | 8.60 | 17.51 | industrial census fields recalled correctly |
| `2024年国民经济和社会发展统计公报（节选）.txt` | `text_heavy` | `government_statistical_bulletin` | 5.27 | 30.33 | pure text bulletin stayed on light path and recalled macro indicators |
| `2024年药品流通行业运行统计分析报告.txt` | `text_heavy` | `pharmaceutical_distribution_report` | 1.78 | 10.38 | pharma report no longer falls back to recruitment template |
| `合肥市2024年国民经济和社会发展统计公报.txt` | `text_heavy` | `government_statistical_bulletin` | 5.09 | 16.77 | local bulletin stays on text path and recalls macro bulletin fields |

### Confirmed Improvements

Compared with the pre-optimization misclassification pattern observed earlier,
this round confirms:

- culture/tourism bulletin is no longer treated as a generic government document
- industrial census bulletin is no longer falling back to `common_document`
- pharmaceutical distribution report is no longer falling back to
  `recruitment_hr_table`
- government bulletins no longer leak healthcare/environment fields
- pure `.txt` bulletins with figure mentions but without real tables remain
  `text_heavy`

### Current Quality Assessment

#### What is already better

- routing is more accurate for `md/txt`
- wrong domain template fallback has been significantly reduced
- field recall now better matches document domain semantics
- the current changes did not break `xlsx` schema tests or visual schema tests

#### What is still not final

- this round mainly lands the `MD/TXT` optimization slice, not the full
  end-to-end optimization plan
- local statistical bulletins still use some national-style canonical labels
  such as `全国居民人均可支配收入`; this is usable, but semantic localization can
  still be improved later
- this round validates schema/field quality and light parsing path quality;
  broader multi-format end-to-end workflow regression still needs follow-up

### Recommended Next Slice

Highest-value next step:

- continue with `plain_text_parser.py` and plain-text schema filtering
- improve heading/noise pruning and local-bulletin field semantics
- then move to `xlsx` native structured extraction strengthening

Why this is the best next slice:

- it keeps working on the same stabilized non-PDF area
- it has low regression risk
- it directly improves current `datasets` quality
- it avoids mixing `docx/pdf` heavy-chain changes into the same round

### Acceptance For This Round

This round can be considered successful because:

- targeted tests passed
- cross-format protection tests passed
- real dataset regression shows corrected template detection on key files
- `txt` light-path routing is now more stable
- no degradation signal was found in the validated scope
