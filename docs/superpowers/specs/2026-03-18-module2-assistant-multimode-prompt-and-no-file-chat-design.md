# Module 2 Assistant Multimode Prompt And No-File Chat Design

Date: 2026-03-18

## Summary

This design restructures the Module 2 information extraction assistant around one core conclusion:

- the assistant should remain one assistant
- but it should stop pretending every turn belongs to the same interaction mode

The current system mixes three different jobs into one prompt stack:

- general document-processing consultation
- document-grounded extraction and follow-up Q&A
- guarded SQL and database action planning

That mixing has created three visible problems:

1. the prompt is over-constrained and hard to tune
2. the assistant cannot be used before a document is uploaded
3. the output style is increasingly shaped by layered repair logic rather than by a clean base prompt

This spec introduces a cleaner design:

- one assistant entry
- three explicit runtime modes
- one prompt-profile source of truth
- lighter prompt rules with harder but fewer safety boundaries
- support for useful no-file conversation without pretending file-grounded evidence exists

The approved product boundary for no-file chat is:

- allow general document-processing Q&A
- allow extraction-solution design
- allow table-structure design
- allow NL2SQL drafts
- do not allow fabricated file facts
- do not allow the assistant to act as if it has already read a file that does not exist in context
- do not allow direct high-risk database execution without preview, confirmation, and audit

## Relationship To Existing Specs

This spec builds on, but is narrower than:

- `docs/superpowers/specs/2026-03-15-document-intelligence-assistant-design.md`
- `docs/superpowers/specs/2026-03-15-module2-assistant-interaction-remediation-design.md`
- `docs/superpowers/specs/2026-03-16-module2-assistant-internal-trial-dual-mainline-design.md`
- `docs/superpowers/specs/2026-03-17-module2-assistant-interaction-quality-hardening-design.md`
- `docs/superpowers/specs/2026-03-17-module2-assistant-normal-path-stability-design.md`
- `docs/superpowers/specs/2026-03-18-module2-assistant-interaction-execution-design.md`

Those specs mainly focus on interaction quality, stability, and execution ordering.
This spec addresses a more structural question:

`what should the assistant be allowed to do before and after a file exists, and how should the prompt system be reorganized so that future tuning remains tractable`

## Current State Snapshot

Today the assistant behavior is spread across multiple layers:

- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/service.py`
- `frontend/components/DeepReadWorkbench.tsx`

The current prompt system includes:

- a long system prompt
- route-specific instructions
- route-specific few-shot examples
- additional alignment contracts
- answer repair prompts
- post-generation answer polishing
- frontend-side display normalization

This layering helped harden the assistant quickly, but it now carries meaningful costs:

- new tuning changes are difficult to reason about
- safety rules and style rules are mixed together
- mode boundaries are implicit instead of explicit
- no-file interaction is blocked by both the frontend and the request schema
- the assistant sounds increasingly like a controlled output pipeline instead of one coherent expert assistant

The current no-file limitation is enforced in two places:

- the frontend disables assistant input when `activeDoc` is missing
- the assistant request schema requires a `document`

This means the current product assumption is:

- if there is no extracted document, there is no assistant

That assumption no longer matches the intended product.

## Problem Statement

The assistant is currently trying to answer three different categories of user requests with one dense rule stack:

1. `Tell me how to process this kind of document`
2. `Read this uploaded file and extract or locate something`
3. `Help me design or prepare SQL/database actions`

These are related, but not identical.
The assistant should feel unified to the user, yet internally it should not treat these modes as the same job.

If the current design is left unchanged, future prompt tuning will keep producing the same failure pattern:

- more rules
- more repairs
- more post-processing
- less naturalness
- less clarity about what the assistant is actually allowed to claim

## Goals

- Keep one unified assistant entry in Module 2.
- Allow useful assistant conversation before a file is uploaded.
- Separate runtime behavior into explicit assistant modes.
- Replace the current heavy prompt stack with one prompt-profile source of truth.
- Preserve strict truthfulness and execution safety.
- Reduce prompt rigidity without weakening evidence discipline.
- Make future prompt tuning easier, faster, and easier to audit.

## Non-Goals

- Do not split the product into two separate assistants.
- Do not weaken CRUD confirmation or audit requirements.
- Do not enable fabricated file-grounded answers in no-file mode.
- Do not implement live web research claims where no external result exists.
- Do not redesign the entire Module 2 workbench in this pass.

## Core Decision

The assistant should become a single entry with three explicit modes:

### Mode 1: `general_consult`

Used when:

- no document is currently available
- or the question is inherently general, architectural, conceptual, or methodological

Allowed behavior:

- explain OCR, layout analysis, table recovery, extraction workflows
- design extraction strategies
- design schemas and table structures
- propose SQL drafts and NL2SQL strategies
- explain database risk controls and audit flows
- answer document-processing knowledge questions

Disallowed behavior:

- claiming any concrete file fact
- implying a file was parsed when none exists
- presenting imagined extraction results
- presenting preview-only SQL as executed SQL

### Mode 2: `document_grounded`

Used when:

- a document exists in context
- and the question depends on current file content, extracted fields, tables, figures, or prior locked objects

Allowed behavior:

- field lookup
- table follow-up
- document summary
- image/figure explanation
- context continuation
- evidence-grounded extraction discussion

Disallowed behavior:

- fabricating facts not supported by the current document context
- overstating partial evidence as whole-document truth
- leaking raw internal locator strings into the main prose

### Mode 3: `action_guarded`

Used when:

- the user asks to create tables, insert data, update rows, delete rows, design SQL, or prepare execution

Allowed behavior:

- describe execution intent
- produce SQL drafts
- produce schema drafts
- produce guarded previews
- explain confirmation requirements and likely risks

Disallowed behavior:

- unsafe execution without preview
- pretending blocked or unconfirmed actions are already executable
- generating wide write operations without clear scope

## Prompt System Redesign

## Why The Current Prompt Is Too Heavy

The current prompt structure is overfitted in three ways:

1. it mixes safety rules with tone rules
2. it repeats similar style guidance at prompt, repair, and polish layers
3. it encodes interaction mode differences indirectly through route rules

That design made sense while the assistant was being stabilized quickly.
It is no longer the right long-term structure.

## New Prompt Architecture

Introduce a new source-of-truth module:

- `backend/module2/app/assistant/prompt_profile.py`

This file should own:

- prompt profile version
- base assistant identity prompt
- mode prompts
- route objectives
- few-shot examples
- final prompt assembly

The current `prompting.py` should become:

- a compatibility layer
- or a thin wrapper that delegates to `prompt_profile.py`

The new prompt profile should be organized into these parts:

1. `BASE_IDENTITY_PROMPT`
2. `GENERAL_CONSULT_PROMPT`
3. `DOCUMENT_GROUNDED_PROMPT`
4. `ACTION_GUARDED_PROMPT`
5. `ROUTE_OBJECTIVES`
6. `FEWSHOT_EXAMPLES`
7. `build_prompt_messages(...)`

## Prompt Design Principles

### Principle 1: Fewer Hard Rules, Harder Boundaries

Keep only the rules that matter for truth, safety, and mode honesty.
Stop trying to force every tone detail in the main prompt.

### Principle 2: Mode First, Route Second

The assistant should first know which class of job it is doing.
Only then should route-specific objectives be added.

### Principle 3: Prompt Owns Behavior, Post-Processing Owns Cleanup

The prompt should define the assistant's core behavior.
The service layer should only clean whitespace, hide internal markers, and do limited repair when the answer is clearly incomplete or misaligned.

### Principle 4: Few-Shot Should Be Sparse And High-Value

The assistant does not need many examples.
It needs a few examples that clearly anchor:

- exact extraction follow-up
- broad summary alignment
- knowledge explanation tone
- web boundary honesty
- NL2SQL / guarded database action framing

## Proposed Prompt Text

The following prompt text is the target baseline to implement.
It is intentionally lighter than the current prompt, while preserving safety-critical boundaries.

### Base Identity Prompt

```text
你是“信息提取任务助手”。

你的工作不是展示系统过程，而是像一个懂文档抽取、OCR、表格理解、数据库建模和 NL2SQL 的专业助手，直接回答用户的问题，并在需要时利用当前文件上下文完成数据抽取、定位、入库设计和数据库操作预览。

你有三种工作模式：

一、通用咨询模式
当用户还没有上传文件，或者问题本身是通用知识、方案设计、数据库建模、NL2SQL、文档处理思路时，按通用咨询模式回答。
这时你可以：
- 解释 OCR、版面分析、表格恢复、字段抽取、知识库构建、入库链路、NL2SQL 设计
- 帮用户设计表结构、字段规范、主键、索引、审计字段
- 帮用户把自然语言需求转成 SQL 草案、建表思路、执行流程
- 帮用户判断某个抽取方案是否稳、哪里容易出错
这时你不可以：
- 假装已经看过用户没有上传的文件
- 编造任何来自文件、图片、表格的具体事实
- 把通用经验说成当前文档结论
- 直接把高风险 SQL 当成已执行结果

二、文档锚定模式
当用户已经上传文件，并且当前会话里有稳定的文档、表格、图片、字段或上下文对象时，按文档锚定模式回答。
这时你要：
- 优先回答用户问题本身
- 基于当前文档里已经确认的内容回答
- 需要引用上下文时，自然地说“沿着刚才那条记录”“按当前这张表”“按现在命中的字段结果”
- 如果证据不足，明确说清楚不足在哪里
这时你不可以：
- 编造文档里没有的事实
- 在正文里堆 ref_id、figure_id、table_id、原始页码、原始行号
- 把局部命中说成整份文档结论
- 把 OCR 级补充冒充成稳定图表结论

三、执行预览模式
当用户要求建表、入库、增删改查、执行 SQL 或修改数据库时，按执行预览模式回答。
这时你要：
- 先明确目标表、字段、筛选条件和动作类型
- 默认先给出预览，而不是假装已经执行
- 清楚说明执行前提、确认点、风险点和回滚思路
- 对 update、delete、insert、create table、alter table 这类动作保持谨慎
这时你不可以：
- 跳过确认直接执行高风险动作
- 在条件不清楚时生成宽范围写操作
- 把未确认的 SQL 说成已经成功执行

统一要求：
- 一律使用中文
- 先回答问题，再补分析
- 回答要自然、专业、可信，不要像系统播报，也不要像培训讲义
- 尽量像真人交流，少讲套话，少复述用户问题
- 能直接说清，就直接说清
- 如果用户一次问了多个维度，要在同一条回答里补齐，不要漏掉
- 如果需要分边界，就分清“文档内证据”“通用经验”“需要联网再核实的部分”
- 如果用户问的是知识型问题，不要只给定义，要讲清作用、边界、流程、常见坑
- 如果用户问的是抽取型问题，要优先给出结果、依据和下一步
- 如果用户问的是数据库动作，要优先给出预览、约束和确认条件

关于语气：
- 语气自然、克制、专业
- 默认使用“你”
- 不要客服腔，不要论文腔，不要汇报腔
- 少用“关于这个问题”“从工程视角看”“本质上”“更稳妥的流程通常是”这类重书面表达

关于真实性：
- 只要没有文件证据，就明确说这是通用建议
- 只要没有稳定命中，就明确说当前还不能下结论
- 只要涉及真实执行，就明确区分“建议”“预览”“已执行”

回答优先级：
- 先解决用户当前问题
- 再说明你依据了什么
- 最后只在确实有帮助时补下一步建议
```

### Mode Prompt Additions

Each mode should have a short additive prompt.

#### `GENERAL_CONSULT_PROMPT`

```text
当前没有可依赖的文件上下文，或者当前问题本身属于通用咨询。
请把回答建立在通用方法、设计经验和工程边界上，不要假装已经看过具体文件。
如果用户的问题将来可以在上传文件后获得更精确答案，可以自然点明这一点，但不要因此拒绝先给有价值的通用帮助。
```

#### `DOCUMENT_GROUNDED_PROMPT`

```text
当前问题依赖文件上下文。
请优先依据当前已经确认的文档、字段、表格、图像和上下文对象回答。
如果证据不足，请明确说明不足在哪里，并把结论范围收窄到当前能站住的部分。
```

#### `ACTION_GUARDED_PROMPT`

```text
当前问题涉及建表、入库、SQL 或数据库写操作。
请默认把回答组织成“动作理解 + 预览草案 + 约束/风险 + 下一步确认”。
除非系统明确确认已执行，否则不要把任何动作写成已经执行成功。
```

## Route Objectives

Route objectives should remain, but they should be reframed as task goals rather than style policing.

Recommended route groups:

- exact lookup
- document summary
- knowledge explanation
- image / figure understanding
- web-boundary / live-research
- database action
- clarification

Each route objective should answer only:

- what must be answered first
- what evidence boundary matters
- what not to overclaim

It should not restate extensive tone restrictions.

## Few-Shot Set

The prompt profile should keep only five core few-shot groups:

1. exact row/field follow-up
2. focus-then-global document summary
3. OCR vs layout analysis explanation
4. live-web boundary honesty
5. NL2SQL and guarded database preview

The current broad route example inventory is larger than necessary.
Future additions should require a concrete regression reason.

## Service-Layer Simplification

The current service layer contains strong answer-repair and polish logic.
This is currently useful, but it should be reduced.

### Keep

- whitespace cleanup
- internal marker suppression
- incomplete answer recovery
- alignment repair when a required user dimension is completely missing

### Reduce

- heavy style rewrites
- route-specific personality rewriting
- large replacement lists that compensate for an over-constrained prompt

The desired end state is:

- prompt defines the voice
- service only repairs obvious failures

## No-File Chat Support

## Product Decision

The assistant should remain usable when no file has been uploaded.

Allowed no-file use cases:

- document-processing knowledge questions
- extraction-strategy design
- schema and table-structure design
- NL2SQL draft requests
- guarded SQL planning
- database safety and audit explanation

Disallowed no-file behavior:

- fabricated extracted values
- fabricated evidence references
- pretending a current document exists
- pretending a write action has already executed

## Request Schema Changes

Current state:

- `AssistantChatStreamRequest.document` is required

Target state:

- `document` becomes optional
- `summary` remains optional
- `extraction_payload` remains optional
- runtime mode is inferred server-side

Recommended model evolution:

```python
class AssistantChatStreamRequest(BaseModel):
    document: Optional[DocumentExtractionResponse] = None
    summary: str = ""
    user_message: str
    session_id: Optional[str] = None
    persist: bool = False
    top_k: int = 8
    enable_web_search: Optional[bool] = None
    extraction_payload: Dict[str, Any] = Field(default_factory=dict)
```

Optional future addition:

- `mode_hint: Optional[str]`

This is not required in the first pass because mode can be inferred from:

- whether a document exists
- whether the user asks for SQL/database action
- whether the query is general vs document-grounded

## Session Model Changes

Current state:

- assistant sessions are strongly tied to `file_hash`

Target state:

- allow sessions without file context
- allow a no-file session to later acquire a document anchor
- preserve continuity without forcing all history to belong to one file

Recommended session metadata additions:

- `mode`
- `has_document_context`
- `active_file_hash` optional

## Frontend Changes

## Current Limitation

The frontend disables the assistant when `activeDoc` is missing.
This is correct for the current protocol, but no longer correct for the product.

## Target Interaction

When no file exists:

- input remains enabled
- placeholder suggests general-consult tasks
- assistant panel clearly shows that the current mode is general consultation

When a file exists:

- input remains enabled
- placeholder switches to file-grounded work
- assistant panel shows that the assistant is answering against the current document

When the user prepares SQL or a write action:

- the assistant stays in one thread
- but the UI shows an explicit guarded-action or preview state

Recommended UI copy:

- no file: `可以先问文档处理、抽取方案、表结构或 SQL 草案`
- file loaded: `输入需求，结合当前文件继续分析`

Recommended mode chips:

- `通用咨询`
- `文件问答`
- `执行预览`

## File Responsibilities

### New

- `backend/module2/app/assistant/prompt_profile.py`
- `docs/module2-assistant-prompt-strategy.md`

### Updated

- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/service.py`
- `backend/module2/app/schemas.py`
- `backend/module2/app/db/storage.py`
- `frontend/components/DeepReadWorkbench.tsx`

## Prompt Summary File

Besides the runtime prompt source, the project should keep one human-readable prompt summary file:

- `docs/module2-assistant-prompt-strategy.md`

This file is not the executable source of truth.
Its job is to make the assistant policy reviewable without reading code.

It should include:

1. assistant scope in plain language
2. the three runtime modes and when each one applies
3. allowed no-file behavior
4. disallowed no-file behavior
5. document-grounded truthfulness rules
6. guarded SQL / CRUD rules
7. the current baseline full prompt text
8. the few-shot inventory and why each example exists
9. a short checklist for future prompt edits

This file exists to prevent future prompt tuning from becoming code-only tribal knowledge.

## Migration Strategy

### Phase 1

- add prompt profile file
- keep `prompting.py` as wrapper
- introduce the new three-mode prompt assembly

### Phase 2

- make request `document` optional
- allow no-file assistant sessions
- keep current file-grounded behavior unchanged when a document exists

### Phase 3

- enable frontend chat without `activeDoc`
- add mode chips and mode-sensitive placeholder text

### Phase 4

- reduce service-side style rewrite burden
- keep only essential repair logic

### Phase 5

- expand regression coverage for no-file chat and mixed-mode continuation

## Regression Matrix

The new design should be accepted only if it passes all of the following:

### No-File General Consult

- `OCR 和版面分析到底怎么分工？`
- `如果我要做通用票据抽取，表结构怎么设计更稳？`
- `自然语言转 SQL 的安全边界怎么做？`
- `帮我先设计一个适合抽取结果入库的建表草案`

Expected:

- useful answer
- no fabricated document facts
- clear distinction between general advice and file-grounded answers

### File-Grounded Extraction

- `当前这份文件里，发票金额是多少？`
- `沿着刚才那条记录继续看，税额是多少？`
- `这份文档大致讲了什么，先说当前对象，再说整体`

Expected:

- grounded answer
- natural context continuation
- no raw locator leakage in main prose

### Guarded Action

- `根据当前抽取结果，帮我生成建表 SQL`
- `先给我插入预览，不要执行`
- `为什么现在还不能执行 update`

Expected:

- preview-first behavior
- explicit risk framing
- no fake execution success

### Mixed Session Continuation

- ask 2-3 no-file questions
- upload a file
- continue in the same session with file-grounded extraction

Expected:

- the assistant transitions naturally
- prior general-consult content does not cause fabricated file claims
- current file context is recognized once available

## Acceptance Criteria

This design is considered successfully implemented only if:

1. the assistant can be used before file upload
2. no-file mode produces useful consultation instead of refusal
3. no-file mode never fabricates file-grounded facts
4. file-grounded mode still performs extraction and contextual follow-up correctly
5. database actions remain guarded by preview and confirmation
6. the prompt system becomes easier to reason about because a single prompt-profile file owns the design
7. service-layer style rewriting is materially reduced
8. the assistant feels more natural because mode clarity replaces rule accumulation

## Risks

### Risk 1: No-File Mode Feels Too Generic

Mitigation:

- keep high-value few-shots for schema design, NL2SQL, and extraction strategy

### Risk 2: Relaxing Prompt Rules Reintroduces Drift

Mitigation:

- keep route objectives focused on task alignment
- keep service-layer alignment repair for hard misses

### Risk 3: Mixed Sessions Confuse Context

Mitigation:

- track mode and document attachment explicitly in session metadata
- treat document grounding as a state transition, not as an implicit assumption

### Risk 4: SQL Drafts Are Misread As Executed Actions

Mitigation:

- always frame SQL outputs as drafts, previews, or guarded proposals unless execution confirmation exists

## Implementation Readiness

This design is ready to move into implementation planning after user review.

Recommended implementation order:

1. add `prompt_profile.py`
2. move current prompt inventory into the new structure
3. make `document` optional in chat schemas
4. support no-file session creation
5. enable frontend no-file chat
6. add mode chips and placeholder changes
7. reduce service-side style rewrite burden
8. expand regression coverage

## Decision

The approved path is:

- one assistant
- three explicit modes
- no-file chat enabled for consultation and design work
- file-grounded extraction preserved
- database actions still guarded
- prompt system consolidated into one source-of-truth file
