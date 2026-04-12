## Module 2 File Parsing Optimization Regression Round 2

Date: 2026-04-03

Status: passed for current plain-text cleanup and macro-field recall slice

### Scope

This round continues the non-PDF optimization track after regression round 1.

Current validation focus:

- plain text line cleanup for `txt`
- removal of low-value footnote-only noise lines
- normalization of spaced short headings such as `综 合 -> 综合`
- stronger government bulletin macro-field recall for local and national
  statistical bulletins
- protection against dimension over-splitting such as:
  - `城镇调查失业率 -> 调查失业率（城市）`
  - `常住人口城镇化率 -> 常住人口 化率（城市）`

### Landed Changes

#### 1. Plain text line cleanup

File:

- `backend/module2/app/core/format/plain_text_parser.py`

Changes:

- added inline footnote stripping for bracketed numeric refs
- added noise-line filtering for bare year/footnote lines and page-number-like
  fragments
- normalized spaced short headings and dates in plain text lines

Expected effect:

- reduces low-value text blocks
- keeps heading semantics cleaner
- improves downstream field-rule matching quality

#### 2. Dimension over-splitting control

File:

- `backend/module2/app/core/schema/field_naming.py`

Changes:

- added `_prune_dimensions_covered_by_label(...)`
- if a canonical/base label already contains the dimension semantics, the
  dimension is no longer appended again

Expected effect:

- prevents false label deformation for government bulletin fields

#### 3. Government bulletin macro field expansion

File:

- `backend/module2/app/assets/field_naming_rules_v1.json`

Added macro-field support for:

- `人均国内生产总值`
- `常住人口`
- `户籍人口`
- `常住人口城镇化率`
- `城镇调查失业率`

Also strengthened GDP aliases with:

- `生产总值`
- `全年生产总值`
- `生产总值（GDP）`
- `GDP`

### Automated Test Results

#### Root-level parser and field tests

Command:

```powershell
pytest backend/tests/test_module2_plain_text_parser.py `
  backend/tests/test_module2_field_naming_rule_inference.py
```

Result:

- `12 passed`

#### Wider root-level regression subset

Command:

```powershell
pytest backend/tests/test_module2_main_nonpdf_bundle.py `
  backend/tests/test_module2_plain_text_parser.py `
  backend/tests/test_module2_field_naming_rule_inference.py `
  backend/tests/test_module2_main_schema_pipeline_bundle.py
```

Result:

- `16 passed`

#### Module 2 cross-format protection tests

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

### Real Regression Highlights

#### National government statistical bulletin

`datasets/txt/2024年国民经济和社会发展统计公报（节选）.txt`

Current recalled fields now include:

- `城镇调查失业率`
- `常住人口城镇化率`
- `人均国内生产总值`
- `国内生产总值`
- `新增就业（城市）`

This is better than the previous round because the macro-field coverage is
closer to the actual bulletin body and not limited to a smaller legacy set.

#### Local government statistical bulletin

`datasets/txt/合肥市2024年国民经济和社会发展统计公报.txt`

Current recalled fields now include:

- `常住人口城镇化率`
- `户籍人口`
- `国内生产总值`
- `人均国内生产总值`
- `新增就业（城市）`
- `居民消费价格涨幅`

This is the main quality win for round 2:

- local bulletin metrics are now being recalled more explicitly
- the old malformed labels caused by dimension splitting are gone

#### Other validated files remained stable

Still correct after this round:

- culture/tourism bulletin
- healthcare bulletin
- industrial census bulletin
- pharmaceutical distribution report

### Current Quality Assessment

#### Confirmed improvements

- plain text cleanup is more robust for noisy `txt` sources
- macro-field recall for government bulletins is broader and more useful
- dimension over-splitting no longer corrupts certain city/economic labels
- cross-format tests still pass, so the current slice did not damage `xlsx` or
  visual schema inference

#### Residual issues still worth addressing later

- some local bulletin fields still use national-style canonical labels such as
  `全国居民人均可支配收入`
- some local finance labels may still remain nationally phrased, such as
  `全国一般公共预算收入`
- those are not workflow blockers, but they are semantic-cleanliness issues for
  future refinement

### Recommended Next Slice

Best next move after this round:

- continue refining government/local bulletin semantic normalization
- distinguish national-scope labels and local-scope labels without breaking
  canonical stability
- then proceed to the next planned optimization slice for `xlsx/native`
  structured extraction
