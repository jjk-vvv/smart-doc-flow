# Document Intelligence Assistant Design

Date: 2026-03-15

## Summary

This design defines the first full platform-grade version of the Module 2 information extraction assistant.

The approved scope is:

- use `gemini-3.1-pro` as the primary assistant model
- accept uploaded documents and images as assistant context
- preserve multi-turn conversation state
- support natural-language directed extraction
- support controlled database write-back into PostgreSQL database `Data_Extraction`
- support optional web search and tool calling
- design a broad rule library that can handle general-purpose documents and multiple domains

The approved database target is:

`MODULE2_DATABASE_DSN=postgresql://postgres:postgres@localhost:5433/Data_Extraction`

The approved naming constraint is:

- table names must not contain `module2`

This design intentionally separates:

1. document understanding and extraction
2. assistant conversation and tool orchestration
3. canonical fact storage
4. domain-specific business projections

This avoids turning the assistant into a monolithic black box and keeps each layer understandable, testable, and evolvable.

## Goals

- Turn the current lightweight extraction helper into a real document intelligence assistant.
- Allow uploaded files and images to participate in assistant reasoning as first-class context.
- Preserve session-level context across multiple user turns.
- Let users ask for targeted extraction in natural language.
- Persist accepted extraction results into PostgreSQL `Data_Extraction`.
- Build a reusable rule library that covers both common office formats and multiple business domains.
- Provide a path for web search and function calling without coupling the whole system to one prompt.
- Keep strong evidence grounding from the current Module 2 parsing and trace pipeline.
- Make the design suitable for future database query and update capabilities without enabling unsafe free-form SQL in phase one.

## Non-Goals

- Do not implement unrestricted natural-language-to-SQL write operations in phase one.
- Do not let the model directly execute arbitrary SQL against production tables.
- Do not replace the current parsing pipeline with model-only extraction.
- Do not depend on true supervised fine-tuning of `gemini-3.1-pro` because that path is not supported for this model.
- Do not store large document binaries as the long-term primary storage payload inside PostgreSQL tables.
- Do not redesign unrelated Module 4 graph workflows as part of this design.

## Key Decisions

### 1. Model Strategy

Primary model:

- `gemini-3.1-pro`

Use cases:

- multi-turn dialogue
- intent understanding
- tool selection
- structured extraction planning
- cross-document summarization inside a user session
- optional web-assisted grounding

Important boundary:

- the system should treat `gemini-3.1-pro` as an orchestration and reasoning model
- the model does not replace OCR, layout parsing, trace localization, or deterministic validation

### 2. No True Fine-Tuning Path In Phase One

The design uses "soft tuning" rather than true model fine-tuning:

- versioned system prompts
- prompt profiles by document family
- few-shot examples
- strict tool schemas
- golden evaluation cases
- user feedback capture
- regression scoring loops

This is the correct path for the chosen primary model and keeps the assistant adaptable without locking the system to unsupported tuning infrastructure.

### 3. Provider Access Must Use An Adapter Layer

The current codebase directly uses Google Gemini integrations and direct Gemini HTTP calls.
The approved deployment target uses a third-party OpenAI-compatible endpoint:

- base URL: `https://hiapi.online/v1`

This means the assistant cannot safely assume official Google-only SDK semantics.
We therefore need a provider adapter that normalizes:

- model invocation
- file inputs
- tool calling
- optional web search
- response parsing
- retries
- usage logging

Without this layer, the assistant would become fragile and provider-specific.

### 4. Hybrid Storage Model Is Required

The best fit for this system is not:

- pure `JSONB` document dumping
- or pure domain-specific business tables only

The approved storage model is:

- rule metadata layer
- normalized document core layer
- assistant/session layer
- canonical fact layer
- domain projection layer
- evaluation layer

This supports broad document coverage while preserving SQL friendliness and auditability.

## Current State

Current Module 2 already provides useful foundations:

- parsing pipeline with PDF, Office, OCR, and MinerU support
- field extraction graph
- trace localization
- staging tables for fields and table cells
- lightweight assistant endpoint
- PostgreSQL fallback to in-memory mode when unavailable

Current storage is intentionally small and not enough for the approved assistant scope.
Today it mainly supports:

- extraction cache
- field staging
- table staging
- assistant interaction history

This is good as a bootstrap layer but insufficient for:

- multi-turn sessions
- reusable rule packs
- evidence-backed canonical facts
- domain projections
- evaluation loops
- web/tool execution audit trails

## Design Principles

### Evidence First

Every accepted extracted fact must remain traceable to one or more document anchors:

- `ref_id`
- page number
- bounding box
- snippet
- source object

The assistant can explain and summarize, but stored facts must remain evidence-grounded.

### Normalize Late, Not Early

Raw extraction candidates should be stored before the system finalizes canonical facts.
This preserves:

- alternative candidates
- review ability
- explainability
- post-hoc rule improvements

### Generic Core, Specialized Projection

The platform must be able to ingest many document types before it knows which ones deserve dedicated business tables.
So the system stores everything first in the generic core and canonical fact model, then projects stable document families into dedicated marts.

### Assistant Actions Must Be Whitelisted

The model may suggest or call tools, but every side effect must pass through controlled server-side functions.
This applies to:

- extraction
- write-back
- search
- future SQL generation

### Table Names Must Stay Clean

No table in this design includes `module2` in its name.
Because the target database is already a dedicated extraction database, the structure should rely on schemas and clear nouns rather than product-prefixed table names.

## Database Layout

Recommended database:

- database name: `Data_Extraction`

Recommended schemas:

- `rule`
- `core`
- `assist`
- `mart`
- `eval`

Rationale:

- `rule` isolates reusable extraction configuration
- `core` stores normalized document and fact primitives
- `assist` stores conversation and tool state
- `mart` stores domain-specific business views and tables
- `eval` stores regression and quality data

Multi-tenant rule:

- all tables in `core`, `assist`, `mart`, and `eval` should carry `tenant_id` as a physical column even when it could be derived through joins
- `rule` may remain global if the deployment is single-governance, but the implementation plan should still leave room for tenant-scoped overrides

## System Units And Interfaces

The implementation should be divided into clear units with explicit responsibilities.

### `Parser Runtime`

Does:

- file parsing
- OCR
- layout analysis
- trace anchor generation
- document chunk generation

Does not do:

- conversation state
- tool orchestration
- database routing decisions

Input:

- uploaded file or artifact reference

Output:

- normalized document primitives for `core`

### `Classification And Schema Selector`

Does:

- document family detection
- type scoring
- schema pack selection

Does not do:

- canonical fact acceptance
- business table write-back

Input:

- parsed document metadata and content features

Output:

- `document_type_code`
- `schema_pack_id`
- candidate type rankings

### `Provider Adapter`

Does:

- normalize calls to the configured LLM provider
- translate file, tool, and response semantics into a stable internal interface

Does not do:

- business validation
- SQL execution

Input:

- provider-neutral assistant request

Output:

- provider-neutral assistant response
- usage metrics
- provider capability flags

### `Assistant Orchestrator`

Does:

- manage session state
- choose tools
- assemble prompt profile and context
- record messages and tool calls

Does not do:

- direct database side effects outside approved service functions

Input:

- session id
- user message
- bound document ids

Output:

- assistant message
- tool invocation plan

### `Fact Service`

Does:

- store candidates
- normalize values
- validate facts
- accept canonical facts
- open review tasks when needed

Does not do:

- user-facing conversation

Input:

- extraction outputs
- rule pack metadata

Output:

- canonical facts
- evidence links
- review tasks

### `Projection Service`

Does:

- project accepted facts into `mart` tables using routing rules
- record write-back audit trails

Does not do:

- candidate generation
- free-form SQL execution

Input:

- accepted facts
- routing rules

Output:

- mart upserts
- writeback logs

### `Evaluation Service`

Does:

- run golden cases
- compare outputs against expected values
- score prompt profiles and extraction behavior

Does not do:

- production write-back

## Rule Library Design

The rule library is the control plane of the assistant.
It decides how a document should be interpreted before the model is allowed to improvise.

### Rule Execution Order

1. format routing
2. pre-processing policy
3. document-type detection
4. schema pack selection
5. extraction policy selection
6. normalization
7. validation
8. storage routing
9. assistant context updates

### Rule Tables

#### `rule.format_rule`

Purpose:

- define how file formats and MIME types should be handled

Suggested columns:

- `format_rule_id`
- `name`
- `mime_pattern`
- `extension_pattern`
- `container_kind`
- `requires_unpack`
- `requires_pdf_conversion`
- `requires_ocr`
- `requires_layout_analysis`
- `preferred_parser_chain_json`
- `max_size_mb`
- `priority`
- `enabled`
- `created_at`
- `updated_at`

#### `rule.document_type`

Purpose:

- master list of supported document types

Suggested columns:

- `document_type_code`
- `family_code`
- `name`
- `description`
- `parent_type_code`
- `standard_ref`
- `status`
- `created_at`
- `updated_at`

#### `rule.type_signature`

Purpose:

- classify documents using titles, labels, patterns, table headers, structural cues, and metadata

Suggested columns:

- `type_signature_id`
- `document_type_code`
- `match_kind`
- `pattern`
- `locale`
- `weight`
- `source_standard`
- `enabled`

#### `rule.schema_pack`

Purpose:

- define the extraction schema for a document type

Suggested columns:

- `schema_pack_id`
- `document_type_code`
- `version`
- `name`
- `json_schema`
- `extraction_mode`
- `confidence_floor`
- `active`
- `created_at`
- `updated_at`

#### `rule.field_definition`

Purpose:

- define one field inside a schema pack

Suggested columns:

- `field_definition_id`
- `schema_pack_id`
- `field_code`
- `label`
- `description`
- `data_type`
- `cardinality`
- `required`
- `unit_family`
- `currency_applicable`
- `enum_json`
- `standard_path`
- `sensitivity_level`
- `sort_order`

#### `rule.alias_lexicon`

Purpose:

- capture field aliases, bilingual labels, abbreviations, table header variants, and regex hints

Suggested columns:

- `alias_id`
- `field_definition_id`
- `locale`
- `alias_text`
- `alias_kind`
- `regex_pattern`
- `weight`
- `enabled`

#### `rule.normalization_rule`

Purpose:

- define how values should be normalized

Suggested columns:

- `normalization_rule_id`
- `schema_pack_id`
- `target_field_code`
- `normalization_kind`
- `expression_json`
- `locale`
- `enabled`

#### `rule.validation_rule`

Purpose:

- define deterministic checks and cross-field consistency rules

Suggested columns:

- `validation_rule_id`
- `schema_pack_id`
- `rule_code`
- `severity`
- `predicate_json`
- `message_template`
- `standard_ref`
- `enabled`

#### `rule.routing_rule`

Purpose:

- control how canonical facts are projected into business tables

Suggested columns:

- `routing_rule_id`
- `schema_pack_id`
- `target_schema`
- `target_table`
- `when_expr_json`
- `upsert_key_json`
- `review_policy`
- `enabled`

#### `rule.tool_policy`

Purpose:

- define which tools can be called for a schema pack and under what safety constraints

Suggested columns:

- `tool_policy_id`
- `schema_pack_id`
- `tool_name`
- `allow_read`
- `allow_write`
- `approval_required`
- `input_schema_json`
- `enabled`

#### `rule.prompt_profile`

Purpose:

- hold versioned system prompts and response policies for pseudo-tuning

Suggested columns:

- `prompt_profile_id`
- `schema_pack_id`
- `model_family`
- `name`
- `system_prompt`
- `response_schema_json`
- `tool_policy_json`
- `active`
- `created_at`
- `updated_at`

#### `rule.fewshot_example`

Purpose:

- store reusable examples for specific packs and prompt profiles

Suggested columns:

- `fewshot_example_id`
- `prompt_profile_id`
- `title`
- `tags`
- `input_json`
- `expected_output_json`
- `quality_score`
- `enabled`

#### `rule.golden_test_case`

Purpose:

- maintain regression cases for extraction quality

Suggested columns:

- `golden_test_case_id`
- `schema_pack_id`
- `title`
- `doc_uri`
- `expected_json`
- `metric_json`
- `difficulty`
- `active`

## Supported Document Families

The system should start with a broad but realistic first-wave rule library.

### Generic Families

- general office document
- scanned image document
- PDF report
- spreadsheet-like tabular document
- mixed text-image presentation document
- form-like document

### Domain Families

- invoice
- purchase order
- receipt
- contract and agreement
- bank statement
- identity and certificate document
- insurance document
- shipping and trade document
- medical report
- laboratory and diagnostic report
- financial report and regulatory filing
- academic article
- legal and policy document

### Initial Schema Packs

#### `generic_core`

Use for:

- unknown or mixed-format documents
- initial broad extraction

#### `invoice_ubl`

Use for:

- invoices
- e-invoices
- billing documents aligned with UBL and Peppol concepts

#### `purchase_order_ubl`

Use for:

- purchase orders
- supply order forms

#### `contract_generic`

Use for:

- contracts
- agreements
- addenda
- terms documents

#### `diagnostic_report_fhir`

Use for:

- medical reports
- lab reports
- diagnostic summaries

#### `financial_fact_xbrl`

Use for:

- financial statements
- regulatory disclosures
- XBRL-like fact extraction

#### `article_jats`

Use for:

- academic papers
- journal articles
- metadata-rich research documents

#### `legal_doc_akoma_ntoso`

Use for:

- policy documents
- legal acts
- structured legal materials

Important boundary:

- not every domain has a strong universal standard
- `contract_generic`, `bank_statement`, and `general_form` should therefore be modeled as practical extraction packs rather than pretending they have a single universal schema

## Core Data Model

The `core` schema stores normalized document, extraction, and evidence primitives.

### `core.ingestion_job`

Purpose:

- track upload and processing lifecycle

Columns:

- `ingestion_job_id`
- `tenant_id`
- `user_id`
- `source`
- `status`
- `submitted_at`
- `started_at`
- `finished_at`
- `error_summary`
- `metadata_json`

### `core.file_asset`

Purpose:

- store file metadata and external storage references

Columns:

- `file_asset_id`
- `ingestion_job_id`
- `sha256`
- `original_name`
- `mime_type`
- `size_bytes`
- `storage_uri`
- `parent_file_asset_id`
- `page_count`
- `metadata_json`
- `created_at`

### `core.document`

Purpose:

- represent one logical document regardless of source representation

Columns:

- `document_id`
- `tenant_id`
- `root_file_asset_id`
- `document_key`
- `document_family`
- `document_type_code`
- `title`
- `primary_language`
- `issuer_name`
- `recipient_name`
- `document_date`
- `status`
- `created_at`
- `updated_at`

### `core.document_variant`

Purpose:

- store alternate representations such as original, PDF-converted, OCR text, and normalized markdown

Columns:

- `document_variant_id`
- `document_id`
- `variant_kind`
- `storage_uri`
- `checksum`
- `version_no`
- `metadata_json`
- `created_at`

### `core.document_page`

Purpose:

- store page-level geometry and quality metadata

Columns:

- `document_page_id`
- `document_id`
- `page_no`
- `width_pt`
- `height_pt`
- `rotation`
- `text_coverage`
- `ocr_confidence`
- `preview_uri`
- `metadata_json`

### `core.content_block`

Purpose:

- store paragraph-level and layout-level text units

Columns:

- `content_block_id`
- `document_page_id`
- `block_type`
- `reading_order`
- `text`
- `normalized_text`
- `bbox_json`
- `ref_id`
- `confidence`
- `attrs_json`
- `search_tsv`

### `core.table_object`

Purpose:

- store detected tables

Columns:

- `table_object_id`
- `document_page_id`
- `ref_id`
- `title`
- `bbox_json`
- `row_count`
- `col_count`
- `table_json`
- `markdown_text`
- `confidence`
- `attrs_json`

### `core.table_cell`

Purpose:

- store normalized table cells for precise table-based extraction

Columns:

- `table_cell_id`
- `table_object_id`
- `row_idx`
- `col_idx`
- `row_span`
- `col_span`
- `cell_text`
- `normalized_text`
- `bbox_json`
- `ref_id`
- `header_role`
- `unit_text`
- `search_tsv`

### `core.figure_object`

Purpose:

- store non-table visual objects such as images, charts, signatures, and stamps

Columns:

- `figure_object_id`
- `document_page_id`
- `ref_id`
- `figure_type`
- `bbox_json`
- `caption_text`
- `ocr_text`
- `preview_uri`
- `attrs_json`

### `core.document_chunk`

Purpose:

- store semantic retrieval chunks for assistant context and recall

Columns:

- `document_chunk_id`
- `document_id`
- `document_page_id`
- `chunk_type`
- `text`
- `normalized_text`
- `ref_ids_json`
- `token_count`
- `source_rank`
- `search_tsv`

### `core.chunk_embedding`

Purpose:

- store embeddings separately from the chunk text row so embedding model changes do not force content-table redesign

Columns:

- `chunk_embedding_id`
- `tenant_id`
- `document_chunk_id`
- `provider`
- `model_name`
- `embedding`
- `created_at`

### `core.classification_run`

Purpose:

- store document classification decisions

Columns:

- `classification_run_id`
- `document_id`
- `classifier_name`
- `model_provider`
- `model_name`
- `top_document_type_code`
- `top_score`
- `candidate_types_json`
- `rule_pack_version`
- `created_at`

### `core.extraction_run`

Purpose:

- track one extraction attempt under one schema pack and prompt profile

Columns:

- `extraction_run_id`
- `document_id`
- `schema_pack_id`
- `prompt_profile_id`
- `model_provider`
- `model_name`
- `run_mode`
- `status`
- `input_tokens`
- `output_tokens`
- `raw_response_json`
- `started_at`
- `finished_at`

### `core.value_candidate`

Purpose:

- preserve candidate values before final acceptance

Columns:

- `value_candidate_id`
- `extraction_run_id`
- `field_code`
- `entity_key`
- `occurrence_no`
- `raw_value`
- `normalized_value_json`
- `data_type`
- `confidence`
- `source_object_type`
- `source_object_id`
- `source_ref_id`
- `page_no`
- `bbox_json`
- `reasoning_json`
- `needs_review`
- `created_at`

### `core.canonical_fact`

Purpose:

- store accepted and normalized facts

Columns:

- `canonical_fact_id`
- `document_id`
- `schema_pack_id`
- `field_code`
- `entity_key`
- `occurrence_no`
- `value_text`
- `value_json`
- `normalized_numeric`
- `normalized_date`
- `unit_code`
- `currency_code`
- `language_code`
- `confidence`
- `status`
- `source_value_candidate_id`
- `created_at`
- `updated_at`

### `core.fact_evidence`

Purpose:

- connect a canonical fact to one or more evidence anchors

Columns:

- `fact_evidence_id`
- `canonical_fact_id`
- `evidence_type`
- `object_table`
- `object_id`
- `ref_id`
- `page_no`
- `char_start`
- `char_end`
- `bbox_json`
- `snippet`
- `confidence`

### `core.fact_relation`

Purpose:

- represent structured relationships between accepted facts

Columns:

- `fact_relation_id`
- `document_id`
- `relation_type`
- `source_fact_id`
- `target_fact_id`
- `attrs_json`
- `confidence`

### `core.review_task`

Purpose:

- track human review of low-confidence or conflicting outputs

Columns:

- `review_task_id`
- `document_id`
- `extraction_run_id`
- `severity`
- `reason_code`
- `status`
- `assigned_to`
- `resolution_json`
- `created_at`
- `resolved_at`

### `core.writeback_log`

Purpose:

- audit projections into target business tables

Columns:

- `writeback_log_id`
- `document_id`
- `extraction_run_id`
- `target_schema`
- `target_table`
- `target_pk_json`
- `payload_json`
- `status`
- `error_text`
- `executed_at`

### `core.audit_event`

Purpose:

- provide immutable operational audit history

Columns:

- `audit_event_id`
- `tenant_id`
- `actor_id`
- `object_type`
- `object_id`
- `action`
- `detail_json`
- `created_at`

## Assistant Data Model

The `assist` schema stores conversation context and tool execution history.

### `assist.session`

Purpose:

- represent one assistant conversation workspace

Columns:

- `session_id`
- `tenant_id`
- `user_id`
- `title`
- `model_provider`
- `model_name`
- `prompt_profile_id`
- `memory_policy`
- `status`
- `created_at`
- `last_active_at`

### `assist.session_document`

Purpose:

- bind documents to a session

Columns:

- `session_id`
- `document_id`
- `role`
- `pinned`
- `added_at`

### `assist.message`

Purpose:

- store conversation messages

Columns:

- `message_id`
- `session_id`
- `turn_no`
- `role`
- `content_text`
- `content_json`
- `token_count`
- `parent_message_id`
- `created_at`

### `assist.tool_invocation`

Purpose:

- audit tool calls made by the assistant

Columns:

- `tool_invocation_id`
- `session_id`
- `message_id`
- `tool_name`
- `input_json`
- `output_json`
- `status`
- `latency_ms`
- `created_at`

### `assist.memory_item`

Purpose:

- store durable memory summaries and user preferences

Columns:

- `memory_item_id`
- `session_id`
- `memory_type`
- `content_json`
- `source_message_id`
- `salience`
- `expires_at`
- `created_at`

### `assist.web_search_cache`

Purpose:

- cache optional web search results

Columns:

- `web_search_cache_id`
- `session_id`
- `query_text`
- `provider`
- `result_json`
- `ttl_until`
- `created_at`

### `assist.feedback_event`

Purpose:

- record user corrections and preference signals

Columns:

- `feedback_event_id`
- `session_id`
- `message_id`
- `canonical_fact_id`
- `feedback_type`
- `feedback_text`
- `label`
- `created_at`

## Domain Projection Tables

The `mart` schema stores stable business-facing tables derived from canonical facts.
These are projections, not the source of truth.

### Initial Mart Tables

- `invoice_header`
- `invoice_line`
- `purchase_order_header`
- `purchase_order_line`
- `contract_header`
- `contract_party`
- `contract_clause`
- `medical_report`
- `clinical_observation`
- `financial_fact`
- `article_metadata`
- `article_contributor`
- `article_reference`
- `legal_segment`

Rule:

- only validated canonical facts are allowed to project into mart tables
- the assistant may request write-back, but the service decides final projection using routing rules

## Evaluation Tables

The `eval` schema closes the loop for pseudo-tuning and regression control.

### `eval.run`

Purpose:

- store one evaluation batch

Columns:

- `eval_run_id`
- `name`
- `prompt_profile_id`
- `model_provider`
- `model_name`
- `dataset_ref`
- `started_at`
- `finished_at`
- `summary_json`

### `eval.result`

Purpose:

- store one case result inside an evaluation batch

Columns:

- `eval_result_id`
- `eval_run_id`
- `golden_test_case_id`
- `document_id`
- `score_json`
- `error_json`
- `raw_output_json`
- `created_at`

## Indexing Strategy

### B-Tree Indexes

Use for:

- foreign keys
- tenant and status filtering
- document and field lookup
- session and turn ordering

Important examples:

- `(tenant_id, document_type_code, created_at desc)`
- `(document_id, field_code, status)`
- `(session_id, turn_no)`
- `(schema_pack_id, active)`

### GIN On `JSONB`

Use for:

- `json_schema`
- `value_json`
- `normalized_value_json`
- `metadata_json`
- `raw_response_json`
- `payload_json`

### `tsvector` Full-Text Search

Use for:

- `content_block.search_tsv`
- `table_cell.search_tsv`
- `document_chunk.search_tsv`

### `pg_trgm`

Use for:

- fuzzy alias lookup
- organization names
- document titles
- noisy OCR text matching

### `pgvector`

Use for:

- `chunk_embedding.embedding`

This supports:

- retrieval-augmented assistant context
- cross-document recall
- related snippet selection

## Partitioning Strategy

Use time-based partitioning for the highest-volume append tables:

- `assist.message`
- `assist.tool_invocation`
- `core.audit_event`
- `core.value_candidate`
- `core.fact_evidence`

Recommended partition granularity:

- monthly

## Error Handling And Edge Cases

### Provider Capability Mismatch

If the configured provider endpoint does not support one of the assumed capabilities such as file inputs, web search, or strict tool calling:

- the provider adapter must expose a capability flag
- the orchestrator must degrade gracefully
- unsupported tools must be hidden from the active prompt profile

### Database Unavailable

If PostgreSQL is unavailable:

- parsing may continue only in explicitly allowed degraded mode
- assistant write-back and canonical fact acceptance must be marked unavailable
- the UI must clearly distinguish "temporary assistant response" from persisted facts

### Rule Pack Missing Or Ambiguous

If no confident schema pack can be selected:

- the system should fall back to `generic_core`
- no mart projection should occur automatically
- the assistant should ask a clarification or remain in generic extraction mode

### Context Overflow

If the document and conversation context exceed model-safe limits:

- the orchestrator should summarize older turns into `assist.memory_item`
- retrieval should prefer evidence-bearing chunks and recent accepted facts
- raw full-document replay should be avoided

### Conflicting Candidate Values

If multiple strong candidates exist for the same field:

- store all strong candidates in `core.value_candidate`
- mark the field for validation or review
- only one canonical fact may remain accepted at a time for the same uniqueness boundary

### Sensitive Documents

If a document matches a high-sensitivity class:

- web search should be disabled by rule unless explicitly allowed
- tool policies should restrict write actions more aggressively
- audit logging should remain mandatory

## Security Strategy

### Row-Level Security

All multi-tenant tables should include `tenant_id` and use PostgreSQL row-level security.

### Side-Effect Safety

The model may never directly execute arbitrary SQL.
All write operations must go through whitelisted tool handlers.

### Secrets

Secrets must never be stored in example files with live values.
The design assumes:

- runtime environment variables for secrets
- masked logging
- no key material in committed spec examples

### Auditability

Every write path must produce:

- tool invocation record
- writeback log
- audit event

## File And Format Handling Rules

### General Rule

Preserve the current parser-first approach:

1. native parser when strong
2. PDF conversion when layout matters
3. OCR when text is weak
4. layout analysis when structure matters
5. model reasoning after deterministic signals are available

### Recommended Format Policies

#### PDF

- primary document format for layout-aware processing
- use page geometry, OCR, tables, and figures directly

#### DOCX / DOC

- parse native text and structure
- convert to PDF when layout or embedded visual understanding matters

#### XLSX / XLS

- prioritize sheet and cell extraction
- use table-focused extraction rules before general LLM extraction

#### PPTX

- treat slide text and image regions as mixed layout content
- convert to PDF if page-like visual navigation is needed

#### Images

- run OCR and image object understanding
- preserve image-level evidence anchors

#### XML / HTML

- map to standards when possible
- preserve source paths and structured tags

## Assistant Workflow

### Session Workflow

1. user uploads document or image
2. system creates `ingestion_job`
3. parser populates core document structures
4. classifier selects candidate document types
5. schema pack is chosen
6. assistant session binds document
7. user asks extraction question
8. assistant invokes extraction tools
9. system stores candidates and canonical facts
10. if user confirms, routing rules project data into mart tables

### Tool Set For Phase One

Recommended tools:

- `get_document_context`
- `get_trace_evidence`
- `classify_document_type`
- `extract_fields`
- `normalize_candidate_values`
- `validate_candidates`
- `accept_canonical_facts`
- `write_projected_records`
- `search_web`
- `list_session_documents`
- `summarize_session_state`

Rule:

- every tool should have strict input schema
- write tools should be allowed only after validation and routing checks

## Configuration Strategy

The design should not hardcode live secrets.

Recommended runtime configuration groups:

- PostgreSQL DSN
- LLM provider mode
- LLM model name
- provider base URL
- provider API key
- optional web search enablement
- tool enablement flags
- RAG and embedding settings

The current codebase should migrate from single-provider assumptions to:

- provider adapter interface
- request/response normalization
- provider capability flags

## Migration Strategy

### Phase 1

- preserve existing tables
- add new schemas and new tables
- keep current cache and staging writes alive

### Phase 2

- route the assistant endpoint through the new session and tool orchestration layer
- mirror accepted outputs into canonical facts

### Phase 3

- add mart projections
- add evaluation loops
- add search and memory retrieval

### Phase 4

- optionally deprecate old lightweight assistant history table after migration is proven stable

## Testing Strategy

### Unit Tests

- rule selection
- document type classification routing
- normalization logic
- validation logic
- write-back routing
- provider adapter behavior

### Integration Tests

- upload to parse to classification
- extraction to canonical facts
- canonical facts to mart projections
- session conversation with tool calls
- PostgreSQL persistence behavior

### Evaluation Tests

- golden set accuracy
- candidate recall
- fact precision
- evidence completeness
- tool call success rate

### Safety Tests

- blocked arbitrary SQL path
- RLS isolation
- secret masking
- invalid tool input rejection

## Risks

### Risk: Third-Party Compatibility Gap

The chosen base URL is not the official Google Gemini endpoint.
Some capabilities may differ from official Gemini semantics.

Mitigation:

- provider adapter
- capability detection
- integration smoke tests before rollout

### Risk: Over-Specialization Too Early

Creating too many mart tables too early will slow delivery.

Mitigation:

- keep canonical fact model as the main source of truth
- only project high-value domains in phase one

### Risk: Model Overreach

If the system lets the assistant invent facts or bypass evidence, trust will collapse.

Mitigation:

- evidence-backed fact acceptance only
- deterministic validation
- review tasks for weak outputs

### Risk: Operational Complexity

This design is broader than the current lightweight assistant.

Mitigation:

- phased rollout
- retain current pipeline during migration
- introduce new schemas without breaking current endpoints

## Success Criteria

The design is successful when:

- uploaded documents and images can participate in multi-turn assistant context
- assistant actions are session-aware and evidence-grounded
- accepted facts are stored in normalized core tables
- phase-one domain projections can be written into `Data_Extraction`
- rule packs can cover both generic and domain-specific documents
- the system can evolve through prompt profiles and evaluation loops instead of unsupported fine-tuning
- no table names include `module2`
- future SQL-oriented capabilities can be added safely on top of the controlled tool layer

## Source Notes

This design is based on official or primary references for:

- PostgreSQL JSON, indexing, text search, row-level security, and partitioning
- pgvector
- Gemini document processing, function calling, file search, and OpenAI-compatible access
- Apache Tika document handling concepts
- Azure Document Intelligence input guidance
- UBL and Peppol billing concepts
- HL7 FHIR document and diagnostic structures
- XBRL financial fact structures
- JATS article metadata structure
- Akoma Ntoso legal document structure

The standards inform the schema-pack model and domain projections.
They do not require the system to force every document into a rigid standard when no realistic standard exists.
