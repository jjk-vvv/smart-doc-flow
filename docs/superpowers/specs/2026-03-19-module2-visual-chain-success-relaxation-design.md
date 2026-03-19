# Module 2 Visual Chain Success Relaxation Design

Date: 2026-03-19

## Summary

This design redefines the success criteria of the Module 2 visual parsing mainline.

The approved direction is:

- keep the mandated mainline as `DOCX -> PDF -> MinerU -> artifacts` and `PDF -> MinerU -> artifacts`
- treat MinerU artifact completion as the primary success signal
- treat Gemini Vision as a conditional enhancement layer for image-like artifacts, not as the gatekeeper of mainline success
- allow valid empty extraction results when the source document truly contains no extractable structured content
- remove overly strict image-quality and chart-only gates that currently convert valid-but-sparse documents into false failures

This spec does not weaken the required mainline.
It weakens the wrong success criteria.

Today the codebase often behaves as if the visual mainline is only successful when:

- MinerU runs
- MinerU emits enough usable `table` and `image` objects
- those objects survive selection
- ROI crops succeed
- Gemini Vision returns good payloads
- confidence thresholds are satisfied
- final `table_blocks` or `figure_blocks` are non-empty

That definition is too strict for the intended product.

The corrected definition in this spec is:

- the mainline succeeds when the document enters the required visual route and MinerU completes with persisted baseline artifacts
- downstream enrichment may be sparse or empty
- final extraction may also be sparse or empty
- only hard failures in conversion, routing, MinerU execution, or required artifact persistence should fail the mainline

## Why This Spec Exists

Recent analysis showed that Module 2 instability is no longer dominated by Word-to-PDF conversion.
That layer has already improved significantly through cache reuse and warm Word COM handling.

The current instability is instead caused by a mismatch between:

- the product goal
- and the code's hidden success gates

The product goal is operational:

- route the file into the right parsing chain
- produce MinerU artifacts consistently
- enrich image-like assets when available
- return structured output when possible
- accept that some documents naturally yield little or no useful extracted content

The current code goal is narrower and harsher:

- demand a usable visual-first result
- demand selected visual objects
- demand non-empty visual blocks
- sometimes implicitly equate sparse output with pipeline failure

That mismatch creates false negatives.

Examples of false negatives include:

- text-dominant PDFs where MinerU runs correctly but yields few or no `table/image` objects
- files whose image artifacts exist but do not survive chart-only gating
- files whose Gemini Vision output is empty or weak even though the baseline MinerU chain completed normally
- files that should be classified as `valid empty result` but are currently surfaced as pipeline degradation or failure

This design fixes the success model so the system can become stable on the mainline without pretending that every document must contain rich structured content.

## Goals

- Keep the required visual parsing route for PDF and Word-derived PDF inputs.
- Define mainline success around conversion completion, MinerU execution, and required artifact persistence.
- Allow sparse or empty downstream extraction results without classifying the parse as failed.
- Send all relevant image-like MinerU artifacts to Gemini Vision when available:
  - ordinary images
  - table images
  - formula images
- Remove image-quality thresholds as hard rejection gates for image artifact processing.
- Preserve source-backed traceability so image and table cards still originate from MinerU/PDF artifacts.
- Make parse status more explicit so the system can distinguish:
  - hard failure
  - success with enrichment
  - success with empty extraction
- Keep the frontend and downstream contracts as stable as possible while improving the semantics of status reporting.

## Non-Goals

- Do not replace MinerU with a different PDF parser.
- Do not redesign the assistant extraction logic in this spec.
- Do not redesign Module 4 in this spec.
- Do not force every document type to yield tables, figures, or formulas.
- Do not hide true runtime failures behind fake success states.
- Do not make Gemini Vision mandatory for baseline parse success.

## Current State Snapshot

### What Is Working

- Word upload can now reuse cached PDF conversion artifacts and avoid repeated cold conversions.
- The strict upload path already routes Word files through PDF parsing when configured.
- MinerU runtime binaries and required local pipeline models are present in the current environment.
- MinerU can produce valid `content_list`, markdown, and image directories for many PDFs.
- Some PDFs already produce good visual objects and downstream artifacts.

### What Is Not Working Well

- The code still treats downstream visual sparsity as a near-failure condition in too many cases.
- Image candidate selection is biased toward chart-like figures only.
- Image and figure quality thresholds still reject artifacts that the user wants processed.
- Formula-like image assets are not modeled as a first-class enhancement target.
- Parse semantics do not cleanly distinguish:
  - hard chain failure
  - successful parse with low artifact density
  - successful parse with empty business extraction

## The Core Product Interpretation

The user's requirement should be interpreted as an artifact-first pipeline, not a dense-result pipeline.

That means the system is expected to answer these questions in order:

1. Did the file enter the required mainline?
2. Did the mainline complete its baseline work?
3. Which baseline artifacts were produced?
4. Which image-like artifacts were eligible for Gemini Vision?
5. Which enrichments were produced?
6. Did the final business extraction contain useful content?

The system should not skip directly to question 6 and use that to redefine the answers to questions 1 through 5.

## Approved Mainline Definition

### Required Parsing Routes

For the target formats in scope:

- `DOCX -> PDF -> MinerU -> artifacts`
- `PDF -> MinerU -> artifacts`

The Word path remains strict:

- Word files must be converted to PDF
- the converted PDF becomes the actual parse input
- the original Word bytes may still be passed as source hints for chart XML, provenance, and runtime heuristics

### Baseline Artifact Contract

For a visual parse to count as baseline success, Module 2 must persist enough MinerU output to support later reasoning.

The required baseline artifact set is:

- a parse record showing the file entered the visual route
- the MinerU run metadata
- a resolved `content_list` artifact when MinerU produced one
- markdown output when MinerU produced one
- image asset directory or image references when MinerU produced them
- merged page text context or equivalent text-bearing output for later extraction stages

Not every file must produce every artifact subtype.
For example:

- a text-heavy PDF may produce no useful image assets
- a copyright page may produce almost no structured output
- a simple memo may have only text and markdown

That is still a valid success path if the mainline completed normally.

## New Success Model

### Layer 1: Chain Execution Status

This layer answers whether the required route executed correctly.

Allowed statuses:

- `success`
- `failed`

It should only be `failed` for hard reasons such as:

- Word-to-PDF conversion failure on a required Word input
- MinerU runtime unavailable
- MinerU command execution failure
- required baseline artifacts missing after a supposedly successful MinerU run
- unrecoverable parse-time exceptions

### Layer 2: Artifact Completeness Status

This layer answers what MinerU actually produced.

Recommended statuses:

- `artifact_rich`
- `artifact_sparse`
- `artifact_text_only`
- `artifact_empty`

Interpretation:

- `artifact_rich`: multiple useful layout objects or image assets exist
- `artifact_sparse`: artifacts exist but are limited
- `artifact_text_only`: text-bearing artifacts exist but layout objects are absent or negligible
- `artifact_empty`: MinerU completed but yielded almost no usable baseline content

`artifact_empty` is not automatically a failed parse.
It is valid when the source document itself is low-yield.

### Layer 3: Vision Enrichment Status

This layer answers what happened to eligible image-like artifacts.

Recommended statuses:

- `not_needed`
- `skipped_no_assets`
- `attempted_empty`
- `attempted_partial`
- `attempted_success`
- `failed_nonfatal`

This layer must not redefine chain success unless the failure was caused by a hard runtime error that should have failed the parse anyway.

### Layer 4: Business Extraction Status

This layer answers whether the final business extraction contains meaningful structured content.

Recommended statuses:

- `nonempty`
- `empty_valid`
- `failed`

`empty_valid` is the correct terminal state for documents that contain little or no extractable business content.

## Required Behavioral Changes

## 1. Relax Visual-First Success Criteria

The parser must stop treating these states as hard visual-chain failure by default:

- `no_layout_objects`
- `no_selected_objects`
- `no_visual_blocks`

Instead, those states should downgrade artifact richness and downstream extraction expectations.
They should only become hard failure when the baseline artifact contract itself was not satisfied.

Examples:

- If MinerU ran and produced `content_list` plus usable text context, return success with `artifact_text_only` or `artifact_sparse`.
- If MinerU ran and produced image assets but Gemini returned empty outputs, return success with `vision_attempted_empty`.
- If final structured extraction is empty, return `empty_valid` rather than pipeline failure.

## 2. Make MinerU Artifact Persistence the Primary Gate

The parse should be considered baseline-successful when:

- the file entered the required visual route
- MinerU ran successfully enough to persist baseline outputs
- the parse state includes clear metadata about what was or was not produced

This means the mainline contract should be keyed to artifact existence and parse state, not to the downstream density of selected blocks.

## 3. Remove Chart-Only Figure Gating From Mainline Success

Current figure selection is overly chart-biased.
That is useful for some optimization paths, but it should not define whether image artifacts are processed at all.

The new rule is:

- if MinerU yields an image-like artifact, it is eligible for Gemini Vision unless an explicit operational limit prevents it

Image-like artifacts include:

- generic images
- figure screenshots
- table screenshots
- formula screenshots

Chart-likeness may remain a ranking hint for budgets, but not a hard eligibility gate for the mainline.

## 4. Remove Image Quality Thresholds As Rejection Gates

Image quality scores may still be recorded for diagnostics.
They should not be used to reject image artifacts from the mainline result.

The new rule is:

- low-confidence image enrichment is acceptable as long as provenance is preserved
- empty or weak Gemini results should be represented as sparse enrichment, not as dropped artifacts that erase the processing attempt

Table quality thresholds may also need to be softened, but table handling still has one practical distinction:

- a table block with no parseable headers or rows may remain structurally empty

Even in that case, the artifact handling itself should still be recorded as a successful attempt if the crop and Vision pass were executed.

## 5. Promote Formula Images To First-Class Vision Targets

The system currently reasons mainly in terms of tables and figures.
The revised design treats formula images as a first-class artifact subtype.

This does not require MinerU to become a mathematical formula parser.
It requires Module 2 to:

- recognize formula-like image assets from MinerU output or ROI crops
- send them through the same image enhancement pipeline when present
- preserve their provenance and returned text payload

Formula enrichment can later be normalized into:

- figure-like descriptive payloads
- dedicated formula artifact cards
- downstream textual evidence for assistant extraction

The exact frontend representation can be staged later, but the backend routing and artifact persistence should be added now.

## 6. Preserve Provenance Even For Empty Enrichment

The user explicitly wants trace images and table images to come from MinerU/PDF artifacts.

Therefore the system must preserve provenance independently of enrichment success.

For each processed image-like artifact, the backend should preserve:

- source page
- source bbox
- source artifact path or crop identity
- artifact subtype
- Gemini attempt status
- Gemini payload if any

This is important because the UI and downstream reasoning should still be able to say:

- the artifact exists
- it came from the PDF/MinerU chain
- enrichment was attempted or skipped

even when the semantic extraction is empty.

## Architecture Changes

### Parsing Orchestration

`main.py` should continue enforcing the strict required route for Word and PDF inputs.

What changes is the interpretation of parser output:

- do not fail the route merely because visual blocks are empty
- do fail the route when baseline artifact persistence is missing
- return explicit multi-layer parse status in the response metadata

### Parser Core

`parser.py` should be updated so that:

- MinerU object sparsity downgrades richness instead of failing the parse
- selected-object sparsity downgrades richness instead of failing the parse
- missing `table_blocks` and `figure_blocks` downgrades enrichment instead of failing the parse
- text-only recovery is treated as a valid visual-chain output mode
- image-like artifact routing no longer depends on chart-only gating
- image-confidence thresholds are recorded, not used as hard rejections

### MinerU Layout Extraction

`layout_mineru.py` should remain responsible for:

- stable command execution
- cache reuse
- content list parsing
- normalized object construction
- run metadata persistence

But its result should now feed a broader artifact classification layer rather than a narrow `usable visual objects or failure` interpretation.

### Vision Enhancement Routing

Gemini Vision routing should be refactored to operate on `artifact candidates` rather than on narrowly accepted `selected visual blocks`.

Candidate classes should include:

- text-bearing tables
- general images
- diagram/chart images
- formula-like images

The routing layer should capture attempt status and payload density separately from parse success.

## Status And Metadata Contract

The parse metadata should explicitly report:

- `chain_status`
- `artifact_status`
- `vision_status`
- `business_extraction_status`

It should also report counts such as:

- `mineru_item_count`
- `mineru_object_count`
- `mineru_image_asset_count`
- `selected_table_candidate_count`
- `selected_image_candidate_count`
- `vision_attempted_count`
- `vision_empty_count`
- `vision_success_count`

And it should preserve mode flags such as:

- `visual_mode`
- `visual_text_only`
- `visual_text_only_recovery`
- `word_pdf_cache_hit`
- `office_pdf_cache_hit`

These fields must allow the system to distinguish:

- valid sparse parse
- valid empty parse
- true failure

without forcing downstream code to infer that from missing arrays alone.

## Error Handling Policy

### Hard Failures

These should still fail the parse request:

- required Word-to-PDF conversion failure
- required visual-route timeout before baseline artifacts are produced
- MinerU runtime unavailability
- MinerU command failure
- missing required artifact persistence after apparent success
- corrupted or unreadable source input

### Non-Fatal Sparse Outcomes

These should no longer fail the parse request:

- zero layout objects with text-bearing content present
- zero selected objects with text-bearing content present
- zero final table or figure blocks
- empty Gemini result on a real artifact
- document has no business-useful extractable fields

### Diagnostic Warnings

Warnings should remain, but they should become descriptive instead of fatal.

Examples:

- `artifact_sparse`
- `artifact_text_only`
- `vision_attempted_empty`
- `business_extraction_empty_valid`
- `formula_assets_detected`
- `no_image_like_assets_detected`

## Implementation Phases

### Phase 1: Success Model Refactor

- introduce the new four-layer status model in parse stats
- stop mapping sparse visual outcomes directly to failure
- preserve existing response contracts while extending metadata

### Phase 2: Candidate Routing Relaxation

- remove chart-only gating from mainline eligibility
- soften or remove image rejection by confidence threshold
- classify image-like artifacts into generic, table-like, and formula-like subtypes

### Phase 3: Provenance-First Artifact Recording

- persist provenance even when Vision returns empty content
- ensure empty enrichment attempts still have traceable artifact records
- standardize source fields for downstream trace rendering

### Phase 4: Extraction Semantics Cleanup

- distinguish `empty_valid` from true extraction failure
- ensure assistant and summary layers can consume the new status model
- keep soft warnings human-readable and non-misleading

### Phase 5: Regression Certification

- re-run DOCX and PDF mainline regressions with cache-aware controls
- include low-yield and text-only PDFs explicitly
- validate that valid-empty documents no longer trip chain-failure semantics

## Regression Matrix

The regression suite for this spec should include at least four sample classes.

### Class A: Rich PDF With Tables And Figures

Expected:

- chain success
- artifact rich
- vision attempted
- non-empty business extraction

### Class B: Text-Dominant PDF With Few Or No Visual Objects

Expected:

- chain success
- artifact text-only or sparse
- Vision skipped or attempted-empty
- business extraction may be non-empty or empty-valid

### Class C: Low-Yield PDF Such As Copyright Or Legal Boilerplate

Expected:

- chain success
- artifact sparse or text-only
- business extraction empty-valid
- no false pipeline-failure classification

### Class D: DOCX Routed Through PDF Mainline

Expected:

- Word-to-PDF conversion success
- parse input is converted PDF
- MinerU artifact persistence succeeds
- chart/image/table/formula assets are routed through Vision when present

## Acceptance Criteria

This design is considered implemented correctly when all of the following are true:

- PDF and DOCX-required visual routes still remain enforced
- baseline parse success no longer depends on non-empty final visual blocks
- Gemini Vision is no longer a hard success gate for image-like artifacts
- low-yield documents can complete with `empty_valid` instead of parse failure
- provenance is preserved for processed image-like artifacts even when enrichment is empty
- regression evidence shows at least one text-only or low-yield PDF completing as a successful mainline parse
- regression evidence shows DOCX continuing to parse through the converted PDF path

## Risks And Mitigations

### Risk 1: Too Much Relaxation Could Hide Real Failures

Mitigation:

- keep hard failures strict at conversion, MinerU execution, and baseline artifact persistence boundaries
- separate sparse status from failed status explicitly

### Risk 2: Downstream Code May Assume Non-Empty Arrays Mean Success

Mitigation:

- add explicit parse status fields
- update downstream consumers to rely on status metadata rather than inferred array presence

### Risk 3: Vision Costs May Increase Once More Image Assets Are Eligible

Mitigation:

- keep operational budgets and page limits
- use ranking and throttling as performance controls
- do not use semantic quality rejection as a correctness gate

### Risk 4: Formula Routing Could Blur Existing Figure Handling

Mitigation:

- introduce formula-like classification as an additive subtype first
- preserve a stable artifact envelope even if the frontend initially renders formulas using the figure presentation path

## Recommendation

The approved recommendation is to shift Module 2 from a `dense visual block success model` to an `artifact-first success model`.

That is the most faithful interpretation of the user requirement because it preserves the strict required mainline while removing the wrong notion of failure.

The implementation should start with status-model and failure-semantics refactoring before touching any UI-facing trace refinements.
