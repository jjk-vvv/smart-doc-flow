# Module2 File Parsing Optimization Regression Round 5

## Scope

This round focuses on the next safe `xlsx/native` slice after round 4:

- clean `xlsx_business_ledger` dirty labels
- remove false-positive business-ledger schema fields
- keep the current parser and FastAPI chain unchanged
- validate on the real `电商销售数据.xlsx` sample and re-run adjacent regressions

## Root Causes Identified

### 1. `aft_sale -> t sale（AF）`

Root cause:

- short stream dimensions such as `AF` were being matched by raw substring
- `aft_sale` therefore matched `af` inside the identifier itself
- the field was incorrectly normalized into a base label plus dimension suffix

### 2. False `订单数` field

Root cause:

- `order_count` still had a very generic English alias: `orders`
- in rule-backed inference, that alias could over-match other headers such as `order_status`
- this produced a false canonical field `订单数` even when no such header existed

### 3. Dirty but real business-ledger headers were not covered

Examples:

- `ret_policy`
- `aft_sale`
- `cus_evalu`
- `spe_need`
- `pay_type`
- `del_type`
- `promition`
- `order_hand`

These headers were real dataset columns, but previously only surfaced as low-quality raw labels or partial dirty labels.

## Changes Landed

### 1. Tightened short ASCII dimension matching

File:

- `backend/module2/app/core/schema/field_naming.py`

Change:

- short ASCII dimension tokens such as `AF`, `AS`, `SF`, `OF` now require token boundaries
- they no longer match arbitrary substrings inside identifiers like `aft_sale`

Effect:

- `aft_sale` is no longer polluted into `t sale（AF）`

### 2. Expanded business-ledger alias coverage

File:

- `backend/module2/app/assets/field_naming_rules_v1.json`

Added business-ledger field rules for:

- `退换政策`
- `售后政策`
- `客户评价`
- `特殊需求`
- `支付方式`
- `配送方式`
- `促销活动`
- `订单处理人`

Effect:

- real English snake_case headers now map into clean canonical business labels

### 3. Removed the overly generic `orders` alias from `order_count`

File:

- `backend/module2/app/assets/field_naming_rules_v1.json`

Effect:

- the false `订单数` field is no longer injected into the business-ledger schema

### 4. Tuned business-ledger selection priority

File:

- `backend/module2/app/runtime/main_schema_selection_bundle.py`

Changes:

- boosted core transaction and logistics fields:
  - `订单状态`
  - `支付方式`
  - `配送方式`
  - `退换政策`
  - `售后政策`
- slightly lowered secondary service-detail fields:
  - `客户评价`
  - `促销活动`
  - `特殊需求`
  - `订单处理人`

Effect:

- under the current 12-field window, the selected output is now much closer to the actual business transaction spine

## Tests

### New focused regression coverage

Updated files:

- `backend/tests/test_module2_field_naming_rule_inference.py`
- `backend/module2/tests/test_xlsx_schema_and_prefill.py`

Added verification for:

- `aft_sale` normalizes to `售后政策`
- no stray `AF` dimension suffix survives in business-ledger normalization
- rule-backed business-ledger headers are recognized from real English header names
- false `订单数` is not injected
- end-to-end schema resolution no longer outputs `t sale（AF）`

### Targeted test results

Commands:

```powershell
pytest tests/test_module2_field_naming_rule_inference.py
pytest tests/test_xlsx_schema_and_prefill.py
```

Results:

- `8 passed`
- `11 passed`

### Adjacent regression results

Command:

```powershell
pytest tests/test_module2_field_naming_rule_inference.py tests/test_module2_plain_text_parser.py tests/test_module2_main_schema_pipeline_bundle.py tests/test_module2_xlsx_runtime.py tests/test_module2_xlsx_parse_runtime.py tests/test_module2_xlsx_table_runtime.py
```

Result:

- `25 passed`

## Real Excel Regression

Dataset:

- `datasets/Excel/*.xlsx`

### `电商销售数据.xlsx`

Before this round:

- selected output still contained dirty field `t sale（AF）`
- false field `订单数` was also present

Current result:

- `template = xlsx_business_ledger`
- `rule_field_count = 18`
- `field_count = 12`

Current selected fields:

- `优惠折扣`
- `售后政策`
- `支付方式`
- `退换政策`
- `配送方式`
- `用户编号`
- `订单编号`
- `订单日期`
- `订单时间`
- `SKU`
- `商品数量`
- `订单来源`

Assessment:

- dirty labels are gone
- false `订单数` is gone
- selected fields now track the actual business transaction workflow much better

### Other Excel samples

Regression status:

- `2025山东省环境空气质量监测数据信息.xlsx` unchanged and still strong
- `2025年国考职位表（节选）.xlsx` unchanged and stable
- `COVID-19全球数据集（节选）.xlsx` unchanged and stable
- `糖尿病患者数据.xlsx` unchanged and stable

## Conclusion

This round is successful.

What improved:

- business-ledger dirty labels were cleaned
- a real false-positive field was removed
- the 12-field selected schema is now substantially closer to a usable e-commerce transaction schema
- adjacent parsing regressions still pass

## Recommended Next Slice

Best next step:

- continue `xlsx` quality work on domain-specific prioritization and dirty-field cleanup for the remaining non-ledger datasets only when a concrete regression is observed

Reason:

- the current ledger cleanup is already in a good state
- the highest-value remaining work is now likely outside this specific dirty-header issue
