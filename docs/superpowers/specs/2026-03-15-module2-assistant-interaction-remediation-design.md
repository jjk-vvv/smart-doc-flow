# Module 2 Assistant Interaction Remediation Design

Date: 2026-03-15

## Summary

This design turns the earlier interaction-quality assessment into an implementation-ready remediation spec for the Module 2 information extraction assistant.

The approved direction is `Approach B`:

- keep a compatibility path for the current single-turn endpoint
- make the formal user path session-based
- make assistant output truly streaming
- make evidence citations first-class in the conversation
- make side effects explicit, previewable, and auditable

This spec is intentionally narrower than the broader platform design in:

- `docs/superpowers/specs/2026-03-15-document-intelligence-assistant-design.md`

It does not redefine the entire assistant platform.
Instead, it focuses on the highest-value current gap:

`the shipped assistant interaction is weaker than the actual underlying capability, and the formal frontend/backend path is not yet aligned with the intended multimodal assistant model`

This remediation design converts that gap into:

- a priority-ordered correction plan
- concrete acceptance criteria
- a redesigned interaction model
- a bounded implementation plan

## Why This Spec Exists

The current Module 2 assistant has crossed the threshold from prototype to useful tool, but it is not yet a stable task assistant.

Observed strengths:

- table-grounded extraction can now answer row-specific questions well
- trace localization UI is already richer than a normal document chat sidebar
- the parser and provider layers already contain key building blocks for streaming, multimodal enhancement, and tool-driven flows

Observed weaknesses:

- the formal frontend path still uses a single-turn request
- the formal backend schema still models a lightweight helper rather than a session-based assistant
- evidence exists, but is not yet integrated into the assistant answer experience strongly enough
- database write semantics are too ambiguous
- image and figure reasoning is not consistently surfaced in the final answer path

The result is a system that feels `better than a rule-based helper` but `less reliable than a true assistant`.

This spec addresses that exact middle state.

## Goals

- Unify the shipped assistant path and the intended assistant architecture.
- Make the assistant feel responsive through streaming output.
- Preserve multi-turn context per document session.
- Make evidence grounding visible in the answer itself, not only in a side panel.
- Support multimodal document reasoning with explicit routing for tables, figures, images, and general extraction.
- Make database side effects safe, reviewable, and auditable.
- Provide a clean path for web search and function calling without turning the assistant into an opaque black box.
- Define a bounded rollout plan that can ship in stages.

## Non-Goals

- Do not rebuild the entire Module 2 parsing stack from scratch.
- Do not replace the existing parser with a model-only solution.
- Do not introduce unrestricted free-form SQL execution.
- Do not promise full autonomous planning across unrelated modules in this remediation phase.
- Do not redesign the entire workbench shell or unrelated Module 1 or Module 4 workflows.
- Do not collapse all future assistant capabilities into one massive service class.

## Design Principles

### 1. Formal User Path Must Equal Real Capability

The biggest product-quality risk is when regression tooling proves a capability exists, but the normal UI path still uses a weaker path.

This remediation treats that as a first-order defect.
The assistant is only considered "available" when the formal frontend route, formal backend contracts, and formal persistence model all support it.

### 2. Evidence Must Be Visible At The Moment Of Trust

Users decide whether to trust an answer while reading the answer, not after manually opening a separate trace region.

The assistant response must therefore carry:

- answer text
- evidence bundle
- object lock context
- action preview when relevant

The right-side evidence area remains valuable, but it becomes a companion surface, not the sole trust surface.

### 3. Every Side Effect Must Be Explicit

Any write, update, delete, or external action must move through:

`intent -> preview -> user confirmation -> execution -> audit result`

The assistant must never imply that "database write completed" when it only saved a conversation artifact.

### 4. Multimodal Questions Need Type-Specific Handling

A question about:

- "that row"
- "this figure"
- "the chart trend"
- "store these values"
- "search the latest policy"

cannot be handled by one generic field-match template without hurting quality.

The assistant must classify the request and route it to the right internal flow.

### 5. Boundaries Beat Cleverness

The system should be split into units that remain understandable and testable:

- session layer
- stream transport
- assistant orchestration
- tool routing
- citation building
- action gating
- storage and audit

No unit should require reading unrelated internals to understand its responsibility.

## Current State Snapshot

The remediation plan assumes the following current realities:

### Frontend Reality

- the assistant panel already supports conversation-style rendering
- the shipped request path is still one-shot
- the assistant shows loading animation but not token streaming
- evidence appears mainly in the separate trace area
- document switch currently clears assistant dialog state

### Backend Reality

- the formal backend exposes a single-turn assistant endpoint
- the formal request and response schemas are lightweight
- assistant persistence is currently interaction-history oriented
- provider code already supports stream-capable OpenAI-compatible responses
- parser code already contains multimodal enhancement work for images and figures

### Runtime Consistency Reality

- some stronger assistant functionality has been exercised through regression tooling
- the current workspace has shown source/runtime drift risks
- therefore the first phase must prioritize formalizing the runtime path before adding major new behavior

## Product Problems To Solve

### Problem 1: The Assistant Feels Slower Than It Really Is

Today the assistant appears to think silently, then returns a complete answer.
This creates avoidable anxiety and masks tool usage.

What users should see instead:

- immediate acknowledgement
- staged activity updates
- streaming answer text
- structured evidence attachments when ready

### Problem 2: Trust Is Split Across Two Surfaces

Today the answer and the evidence are separated.
This means a user can read a plausible answer without immediately seeing why it is grounded.

What users should see instead:

- a clear answer
- inline evidence cards
- a visible current object lock
- a one-click path into deep trace detail

### Problem 3: "Save To Database" Means Too Many Different Things

Today the product can blur:

- save session record
- save extraction result
- write to business tables

These are materially different actions and must not share one vague "written to database" message.

### Problem 4: The Assistant Overfits To Field Questions

The current behavior is noticeably stronger on field/value retrieval than on figure overview or image reasoning.
That is acceptable for the current prototype state but not for the intended assistant product.

### Problem 5: Context Exists But Is Not Formal Enough

Follow-up success in regression is valuable, but it is not enough.
The formal system needs explicit session, message, and locked-object handling so that follow-up behavior is deterministic and inspectable.

## Remediation Priority Model

The work is divided into `P0`, `P1`, and `P2`.

### P0: Make The Assistant Path Correct

This phase is required before claiming the assistant is production-grade.

Deliverables:

- formal session-based assistant API
- formal streaming chat API
- formal message and action persistence
- explicit action preview and confirmation flow
- evidence bundle included in formal assistant responses
- unified source/runtime assistant service path

What P0 fixes:

- path inconsistency
- lack of streaming
- vague write semantics
- low observability of tool/action stages

### P1: Make The Multimodal Experience Strong

This phase upgrades depth and reliability, especially for images and figures.

Deliverables:

- question-type classifier and router
- stronger figure overview path
- stronger chart/image answer templates
- explicit current-object locking
- improved evidence rendering in chat

What P1 fixes:

- figure questions falling back to field-style failure
- unstable image/chart detail surfacing
- weak follow-up clarity for "that row" and "this figure"

### P2: Make The Assistant Operationally Powerful

This phase adds controlled web search and controlled NL-to-SQL operations on top of the corrected interaction model.

Deliverables:

- tool-visible web search flow
- approved SELECT-style NL-to-SQL flow
- gated write/update/delete action flow
- full audit trail for tool and SQL actions

What P2 fixes:

- missing external knowledge access
- lack of database action transparency
- unsafe future expansion risk

## Target Architecture

The remediation architecture is intentionally layered.

### 1. Frontend Conversation Layer

Responsibility:

- render session history
- send new user messages
- receive stream events
- show tool status and action previews
- attach citations and evidence cards to messages

Must not own:

- tool routing logic
- SQL generation logic
- evidence extraction logic

Primary UI state:

- `activeSessionId`
- `streamState`
- `messages`
- `currentObjectLock`
- `pendingActionPreview`
- `evidenceSelection`

### 2. Stream Transport Layer

Responsibility:

- carry server-sent or chunked assistant events
- normalize event order
- support cancellation
- expose reconnect-safe terminal states

Recommended event families:

- `assistant_start`
- `assistant_delta`
- `tool_status`
- `citation_bundle`
- `action_preview`
- `assistant_done`
- `assistant_error`

### 3. Assistant Orchestration Layer

Responsibility:

- build the reasoning context for a request
- classify request type
- select tools
- maintain locked-object context
- produce the final structured answer package

Must not directly:

- execute unsafe writes
- emit UI-only formatting assumptions
- bypass action approval

### 4. Tool Router Layer

Responsibility:

- provide typed, whitelisted tools
- log invocation metadata
- map tool outputs into a normalized assistant-friendly format

Initial tool families:

- `locate_table_cells`
- `inspect_figure`
- `read_figures`
- `locate_trace`
- `web_search`
- `sql_preview`
- `sql_execute_confirmed`

### 5. Citation Builder Layer

Responsibility:

- convert raw trace, table, figure, and parser artifacts into user-facing evidence bundles
- generate answer-ready citations
- attach preview metadata such as row index, page, `ref_id`, preview rows, screenshot URLs, and explanation labels

### 6. Action Gate Layer

Responsibility:

- validate side-effect requests
- produce an execution preview
- await user approval
- execute the action if approved
- return audit metadata

### 7. Persistence Layer

Responsibility:

- persist assistant sessions
- persist assistant messages
- persist tool calls
- persist action previews and action results
- persist extracted payload snapshots needed for replay and audit

## Formal Interaction Model

The assistant should move from a plain chat bubble model to a richer typed-message model.

### Message Types

The frontend should support at least the following message types:

- `user_message`
- `assistant_text`
- `assistant_streaming_text`
- `tool_status`
- `citation_bundle`
- `action_preview`
- `action_result`
- `system_notice`

This is a key remediation decision.
Without typed message handling, every advanced capability gets flattened into prose and becomes harder to trust.

### Conversation Stages

Each user turn should follow this lifecycle:

1. user sends message
2. assistant acknowledges and starts stream
3. system emits tool-status events if tools are used
4. assistant emits text deltas
5. system emits citations and/or action preview
6. assistant emits final completion event

If side effects are requested:

1. assistant interprets the request
2. assistant returns preview instead of execution
3. user confirms or cancels
4. action result is emitted and audited

### Current Object Lock

After a successful answer, the assistant should store a visible `current object lock`.

Examples:

- `xlsx_t1 / row 3 / original row 4`
- `figure image_caption_f1 / page 1`
- `field invoice_amount / ref_id xxx`

This lock must be:

- shown in the UI
- stored in session state
- reusable for follow-up interpretation
- resettable by the user

## API Contract Changes

This spec does not freeze exact code, but it does require the following contract families.

### Session Creation

`POST /extract/assistant/session`

Purpose:

- create or resume an assistant session for a document context

Required output:

- `session_id`
- document identity
- summary snapshot
- current object lock if restorable
- recent message summary

### Streaming Chat

`POST /extract/assistant/chat/stream`

Required input:

- `session_id`
- `document`
- `summary`
- `user_message`
- optional current object lock
- optional extracted payload snapshot reference
- optional capability flags such as `enable_web_search`

Required streamed outputs:

- text deltas
- tool status updates
- citation bundle payload
- action preview payload
- completion event with final metadata

### Action Confirmation

`POST /extract/assistant/action/confirm`

Purpose:

- confirm execution of a previewed side-effect action

Required input:

- `session_id`
- `action_id`
- `approved: true|false`
- optional user comment

Required output:

- action execution result
- audit identifier
- affected row count or explicit no-op result

## Compatibility And Cutover Strategy

The current single-turn helper path should remain only as a temporary compatibility layer during migration.

### Compatibility Rules

- `/extract/assistant/query` may remain available during transition
- it must be treated as legacy compatibility, not as the preferred formal assistant path
- new frontend work must target the session + stream path
- regression tooling must be moved onto the same formal assistant service path as the frontend

### Cutover Rules

The migration is complete only when:

- the formal UI no longer depends on the one-shot helper endpoint
- the formal backend assistant source path is the same one used by regression tooling
- session, citation, and action semantics are available through the formal path

### Legacy Endpoint Scope After Cutover

After cutover, the legacy endpoint may remain only for:

- narrow compatibility fallback
- short-lived operational rollback
- explicit internal diagnostics

It must not keep receiving new feature work.

## Storage Model For Interaction Remediation

This spec narrows the storage design to the interaction-critical tables needed for the remediation.

Recommended schema:

- `assist`

Recommended tables:

- `assist_session`
- `assist_message`
- `assist_tool_call`
- `assist_action`
- `assist_action_execution`

Table names intentionally avoid `module2`.

### `assist_session`

Purpose:

- one row per assistant conversation context

Core fields:

- `session_id`
- `file_hash`
- `file_name`
- `summary_text`
- `current_object_lock_json`
- `metadata_json`
- `created_at`
- `updated_at`

### `assist_message`

Purpose:

- durable conversation history

Core fields:

- `message_id`
- `session_id`
- `role`
- `message_type`
- `content_text`
- `payload_json`
- `created_at`

### `assist_tool_call`

Purpose:

- observable tool execution trail

Core fields:

- `tool_call_id`
- `session_id`
- `message_id`
- `tool_name`
- `input_summary_json`
- `output_summary_json`
- `status`
- `latency_ms`
- `created_at`

### `assist_action`

Purpose:

- previewable action proposal before execution

Core fields:

- `action_id`
- `session_id`
- `action_type`
- `target_kind`
- `preview_json`
- `approval_status`
- `created_at`
- `updated_at`

### `assist_action_execution`

Purpose:

- post-confirmation execution audit

Core fields:

- `execution_id`
- `action_id`
- `session_id`
- `executor_type`
- `result_status`
- `result_json`
- `affected_rows`
- `error_text`
- `created_at`

## Frontend Interaction Redesign

The redesign should preserve the overall workbench structure and focus on the assistant interaction surface.

### Target Layout

Recommended high-level layout:

- left: document and rule rail
- center: preview stage
- right: tabbed console with `Results` and `Assistant`

This respects the current workbench mental model while upgrading the assistant experience.

### Assistant Tab Structure

The assistant tab should be organized into five visible regions:

1. `Session Header`
2. `Current Context Strip`
3. `Conversation Timeline`
4. `Pending Action Drawer`
5. `Composer`

### Session Header

Shows:

- assistant title
- document name
- session status
- reconnect or restore hint if needed

### Current Context Strip

Shows:

- summary badge
- current object lock
- enabled capabilities such as `联网` and `数据库操作需确认`

This strip helps users understand how follow-up references will be interpreted.

### Conversation Timeline

Must support:

- streaming text
- tool-status rows
- inline citation bundles
- action previews
- action results

It must feel like a working assistant log, not only a decorative chat window.

### Pending Action Drawer

This drawer appears only when a previewable side-effect action exists.

It must show:

- action type
- target table or target system
- preview content
- estimated impact
- risk level
- confirm button
- cancel button

### Composer

The composer must support:

- Enter to send
- Shift+Enter for newline
- stop generation
- visible disabled states
- optional suggestion chips

Recommended starter prompts:

- `提取这张表里站点名称为 XX 的 PM10 值，并给出处`
- `概述这张图片里的图表，并列出关键要点`
- `把已确认的抽取结果保存到事实表`
- `联网搜索最新政策变化，并说明是否影响当前字段解释`

## Evidence Presentation Redesign

This is a core remediation area.

### Evidence Must Exist In Two Levels

Level 1: `inline citation bundle`

- compact
- attached directly below the answer
- optimized for trust-at-a-glance

Level 2: `deep evidence panel`

- richer preview
- trace details
- screenshot or table preview
- copy and open actions

### Table Citation Bundle

Must include:

- table id
- page
- row index
- original row index when available
- `ref_id`
- cell preview

### Figure Citation Bundle

Must include:

- `figure_id`
- page
- caption or title
- key points if available
- explicit statement when key points or dataframe are unavailable

### Database Action Citation

When a write or SQL-related answer is produced, the assistant must cite:

- whether this is preview only or executed
- target table or data source
- affected rows estimate or actual result
- audit identifier after execution

## Multimodal Routing Design

The assistant should classify each user turn into one primary route, with optional secondary routes.

### Route Types

- `field_lookup`
- `table_lookup`
- `figure_overview`
- `figure_value_read`
- `document_summary`
- `database_action`
- `web_research`
- `clarification_needed`

### Route Behavior

#### `field_lookup`

Best for:

- direct field extraction
- label-to-value questions
- ref-backed value explanation

#### `table_lookup`

Best for:

- row-specific table questions
- follow-up questions like "that row"
- row and column grounded evidence

#### `figure_overview`

Best for:

- "概述图表"
- "列出 figure_id 和页码"
- "这个图主要说明了什么"

This route must not fail with a field-name clarification message when figures are already present in parse output.

#### `figure_value_read`

Best for:

- chart values
- axis interpretation
- trend extraction
- "有没有 dataframe 或具体数值"

#### `database_action`

Best for:

- save result
- insert/update/delete intent
- natural-language-to-SQL preview

Must always flow through preview and confirmation for side effects.

#### `web_research`

Best for:

- current policy
- latest regulations
- external reference lookups

Must expose source attribution and search-stage status.

## Action Safety Model

This remediation requires a strict action model.

### Allowed Action Tiers

Tier 1:

- no side effects
- safe automatic execution

Examples:

- field lookup
- evidence lookup
- figure inspection
- summary generation

Tier 2:

- external information access
- safe with visibility

Examples:

- web search
- source fetch

These require visible tool status and source reporting.

Tier 3:

- potentially destructive or state-changing
- requires explicit approval

Examples:

- SQL write
- business-table insert
- update or delete
- canonical fact save with overwrite semantics

### SQL Safety Rules

For remediation scope:

- `SELECT` may be previewed and optionally auto-run after guard checks
- `INSERT`, `UPDATE`, and `DELETE` require confirmation
- all SQL must be generated against a whitelist of schemas, tables, and columns
- all SQL must be logged with preview and execution records
- the assistant must never run arbitrary raw SQL from user text without validation

## Error Handling Design

The assistant must move from generic failure messages to typed failure communication.

### Error Families

- `document_not_ready`
- `no_matching_object`
- `figure_data_insufficient`
- `tool_timeout`
- `tool_failed`
- `web_search_failed`
- `sql_validation_failed`
- `action_not_approved`
- `stream_interrupted`

### User-Facing Error Rules

- explain what failed
- explain what still succeeded if anything
- explain the next best action
- do not claim completion if a required tool failed

Example:

Bad:

- `助手处理失败，请重试`

Good:

- `已识别到图表对象和标题，但未从图中稳定读出关键数值，因此当前只能返回 figure_id、页码和标题概述。你可以继续要求“只列出图表对象”或“尝试读取图中坐标轴与数据点”。`

## Acceptance Criteria

The assistant is considered remediated for a phase only if it passes the following user-visible criteria.

### P0 Acceptance Criteria

#### Session And Streaming

- user can open an assistant session for the active document
- first visible token appears within 1.5 seconds for normal responses
- stop-generation works
- tool usage emits visible status updates
- session history persists across multiple turns for the same document
- switching documents does not mix message history or object locks across sessions
- page refresh can restore the latest active session for the same document when recoverable

#### Trust And Evidence

- every factual answer includes either a citation bundle or an explicit insufficiency statement
- table answers expose row/page/ref grounding when available
- action answers distinguish preview from execution

#### Action Safety

- "save to database" does not directly execute a write without preview
- user can confirm or cancel previewed actions
- action result includes audit identifier or clear failure information

### P1 Acceptance Criteria

#### Table Follow-Up

Scenario:

- ask for PM10 value in a specific row
- follow up with "that row's pollution type"

Expected:

- second turn reuses row lock
- answer includes row/page/ref grounding

#### PDF Figure Overview

Scenario:

- ask for document figure overview

Expected:

- assistant lists figure objects when figure parse output exists
- answer does not default to field-name clarification
- if key points are missing, assistant says that explicitly

#### Image Chart Reasoning

Scenario:

- ask for image chart overview and whether dataframe or numeric values exist

Expected:

- answer includes figure id and page
- answer states whether key points and dataframe exist
- insufficiency is explicit, not hidden behind generic failure

### P2 Acceptance Criteria

#### Web Research

Scenario:

- ask for latest external policy information related to a field

Expected:

- assistant shows search-stage progress
- answer contains source attribution
- final answer distinguishes document evidence from web evidence

#### NL-to-SQL

Scenario:

- ask for a database query in natural language

Expected:

- assistant returns validated SQL preview
- if read-only and safe, it may execute after validation
- if write-oriented, it requires explicit confirmation

## Quality Gates And Metrics

### Experience Metrics

- `first_token_latency_p95 < 1500 ms` for ordinary assistant turns
- `answer_completion_p95 < 12 s` for non-heavy multimodal turns
- `stop_response_ack < 1 s`

### Accuracy And Helpfulness Metrics

- table-grounded answer accuracy for golden set >= 90%
- follow-up context retention for golden set >= 85%
- figure overview success when figures exist in parse output >= 85%
- explicit insufficiency reporting for incomplete figure/image cases >= 95%

### Safety Metrics

- side-effect execution without preview = 0
- ambiguous "database write completed" messages for non-business writes = 0
- unaudited SQL executions = 0

## Rollout Plan

### Phase 0: Path Alignment

Ship:

- session persistence primitives
- streaming chat endpoint
- typed message rendering
- action preview skeleton
- legacy one-shot endpoint marked as compatibility-only

Do not ship yet:

- full web search
- full NL-to-SQL writes

### Phase 1: Multimodal Upgrade

Ship:

- request-type routing
- figure overview answer path
- image chart evidence improvements
- current object lock UI

### Phase 2: Operational Tools

Ship:

- web search tool exposure
- safe NL-to-SQL preview
- auditable confirmation flow for writes

## Testing Strategy

### Unit Tests

- route classification
- citation bundle formatting
- current object lock updates
- action preview validation
- SQL validation rules

### Integration Tests

- session creation and restore
- streaming event order
- tool-status emission
- action confirm lifecycle
- storage writes for session/message/tool/action tables

### End-To-End Tests

- upload document -> ask field question -> receive stream -> inspect evidence
- ask follow-up using pronoun or implicit object reference
- ask figure overview on PDF
- ask image chart summary
- trigger save or SQL preview -> confirm/cancel -> observe result

### Real-Media Regression

The existing real-media regression set should be expanded into the formal acceptance suite.

Minimum required scenario families:

- Excel table row lookup
- Excel follow-up row question
- PDF figure overview
- image chart overview
- web research scenario
- SQL preview scenario

## Implementation Plan

This section provides the implementation-plan baseline required before coding.

### Workstream 1: Contracts And Storage

Tasks:

- add formal session and streaming schemas
- add storage methods for session/message/tool/action persistence
- create migration or initialization DDL for `assist_*` tables
- preserve compatibility with the current helper history table during transition

Exit criteria:

- backend can create, persist, and resume a session
- a streamed turn and its messages are durably recorded

### Workstream 2: Backend Assistant Service Unification

Tasks:

- define a formal assistant service entrypoint in source, not runtime-only fallback
- route both regression tooling and frontend through the same service
- move tool status, citations, and action preview into normalized assistant outputs

Exit criteria:

- no formal user path depends on pyc-only assistant loading
- one service path serves frontend and regression

### Workstream 3: Frontend Streaming Conversation

Tasks:

- replace one-shot assistant request flow with stream consumption
- add typed timeline rendering
- add stop button and recovery handling
- add current object lock strip
- render inline citation bundles and action previews

Exit criteria:

- user sees streaming text and tool status
- evidence appears inline in the assistant timeline

### Workstream 4: Multimodal Routing

Tasks:

- implement question-type classification
- route figure and image prompts away from field-only fallback
- attach figure-aware answer templates
- preserve insufficient-data honesty

Exit criteria:

- PDF figure overview and image chart overview meet the P1 acceptance criteria

### Workstream 5: Action Safety And SQL Preview

Tasks:

- create action preview model
- add confirm/cancel API
- add SQL preview validation path
- add audit identifiers and execution reporting

Exit criteria:

- no side-effect action executes without approval
- SQL preview and audited execution path work end-to-end

## Open Implementation Notes

- Existing assistant-related design docs should remain valid for long-term platform direction.
- This remediation spec should be treated as the active bridge between current shipped behavior and the longer-term assistant architecture.
- If future implementation discovers that the current right-panel composition is too constrained for citation bundles and action previews, the assistant tab may expand vertically before any larger shell redesign is considered.

## Approval State

Approved by user for design direction:

- `Approach B`

Design status:

- ready for spec review
- ready for implementation planning after user review of the written spec
