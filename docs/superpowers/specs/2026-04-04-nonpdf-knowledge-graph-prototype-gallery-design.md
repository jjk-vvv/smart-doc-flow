# Non-PDF Knowledge Graph Prototype Gallery Design

Date: 2026-04-04

## Summary

This spec defines a first-round prototype gallery for the best-practice knowledge graph construction of non-PDF documents under `datasets/`.

The prototype gallery will not change Module 4 production behavior yet.
It will create a decision-ready visual reference for three representative non-PDF graph patterns:

- `xlsx` record-oriented graph
- `md/txt` bulletin-oriented graph
- `docx` multimodal narrative graph

The approved direction is:

- use a shared professional workbench shell
- create three distinct prototype pages under one gallery entry
- keep the graph main view semantic-first
- push evidence and dataframe detail into the inspector and reveal layers
- avoid dataset-specific hardcoding in the graph model itself
- design the prototypes so they can later migrate into Module 4 with minimal waste

## Why This Spec Exists

The current Module 4 graph is still too close to a storage-first evidence graph for non-PDF inputs.
It can show `Document`, `Field`, `Table`, and `Figure`, but it does not yet demonstrate the ideal knowledge graph shape for fundamentally different non-PDF structures.

The main current gap is not only rendering quality.
It is the lack of a product-facing answer to this question:

`for each non-PDF document family, what should be the primary graph unit and what should only appear as evidence?`

Without that answer:

- xlsx files collapse into flat field graphs or table-centric evidence views
- md/txt bulletins collapse into chunk-driven graphs instead of claim-driven graphs
- docx files collapse into mixed text/table/figure artifact graphs without a stable observation layer

This prototype gallery exists to make the target shapes visible before deeper implementation work begins.

## Goals

- Produce three decision-ready HTML prototype pages for non-PDF knowledge graphs.
- Use one shared workbench shell and one shared interaction language.
- Demonstrate the correct graph center for each file family.
- Separate semantic, observation, and evidence layers in a way users can understand visually.
- Use mock data derived from real project samples, not invented arbitrary examples.
- Define a prototype structure that can later be migrated into Module 4.

## Non-Goals

- Do not replace the live Module 4 graph page in this phase.
- Do not connect the prototype pages to the live backend or Neo4j yet.
- Do not redesign the whole Module 4 API in this phase.
- Do not implement full graph editing, persistence, search, or export workflows.
- Do not model every possible non-PDF domain in round one.
- Do not hardcode final business logic around specific file names in the implementation.

## In-Scope Document Families

The prototype gallery covers three representative graph families:

1. `xlsx` record-oriented graph
2. `md/txt` bulletin-oriented graph
3. `docx` multimodal narrative graph

These families are chosen because they cover the major structural differences in the current non-PDF dataset:

- table-first structured records
- narrative statistical bulletins
- mixed text, tables, and charts

## Sample Sources

The prototypes should derive their mock structures from real project samples, but the rendered pages should remain prototype-focused and curated rather than fully raw.

Recommended sample sources:

### xlsx record-oriented graph

- `datasets/Excel/2025年国考职位表（节选）.xlsx`
- `datasets/Excel/COVID-19全球数据集（节选）.xlsx`
- `datasets/Excel/2025山东省环境空气质量监测数据信息.xlsx`
- `datasets/Excel/电商销售数据.xlsx`
- `datasets/Excel/糖尿病患者数据.xlsx`

### md/txt bulletin-oriented graph

- `datasets/md/2023年文化和旅游发展统计公报.md`
- `datasets/md/2024年卫生健康事业发展统计公报.md`
- `datasets/txt/合肥市2024年国民经济和社会发展统计公报.txt`

### docx multimodal narrative graph

- `datasets/word/2021年民政事业发展统计公报.docx`
- `datasets/word/2024年杭州市生态环境状况公报（节选）.docx`

## Current System Findings

### Module 2 already exposes strong non-PDF structure

The current system already produces the signals needed for a higher-quality non-PDF graph model:

- xlsx sheet, row, cell, and table structures
- plain text and markdown chunk structures
- markdown tables and figure cue extraction
- docx paragraph, table, figure, and chart/media extraction
- unified trace locators for non-PDF refs
- table and figure dataframe payloads

Relevant implementation references:

- `backend/module2/app/core/format/xlsx_runtime.py`
- `backend/module2/app/core/format/plain_text_parser.py`
- `backend/module2/app/core/format/docx_document_runtime.py`
- `backend/module2/app/runtime/document_trace_runtime.py`

### Module 4 still stores a flatter graph than the product target

The current Module 4 ingest path mostly materializes:

- `Document`
- `Field`
- `Risk`
- `Table`
- `Figure`

with edges such as:

- `extracts`
- `contains`
- `has_risk`
- `has_warning`
- `links_to`

This is valuable as a storage graph and evidence graph, but it is not yet the product-facing best graph shape for non-PDF document families.

Relevant implementation reference:

- `backend/module4/app/services/ingestion/runtime.py`

## Product Decision

The prototype gallery will use a shared workbench shell with three dedicated pages:

- `xlsx-record.html`
- `bulletin-text.html`
- `docx-visual.html`

There will also be one gallery entry page:

- `index.html`

The shell and interaction model will be shared.
The graph model and inspector content will vary by document family.

## Core Design Principle

The graph center must reflect the document's natural semantic grain, not its raw parse artifact.

This means:

- xlsx pages center on records and stable entities, not the table itself
- md/txt pages center on claims and metric observations, not chunks
- docx pages center on narrative topics and observations, not images and screenshots

## Shared Graph Layer Model

All prototypes should present the same three conceptual layers:

1. `Semantic Layer`
2. `Observation Layer`
3. `Evidence Layer`

### Semantic Layer

This is the default visible layer.
It should answer:

- what the document is mainly about
- what the main entities, metrics, and topics are
- what the document's stable knowledge shape looks like

### Observation Layer

This is the bridge layer.
It should answer:

- which claims, records, or extracted observations connect the semantic graph to evidence

### Evidence Layer

This is the grounding layer.
It should answer:

- where the data came from
- which table, chunk, row, page, or figure supports a node

## Prototype 1: XLSX Record-Oriented Graph

### Main Purpose

Show that record-style spreadsheets should build around records, dimensions, entities, and metrics rather than a flat field graph.

### Primary Node Types

- `Dataset`
- `RecordObservation`
- `Entity`
- `Metric`
- `TimePeriod`
- `TableArtifact`
- `RowEvidence`

### Primary Edge Types

- `HAS_RECORD`
- `ABOUT`
- `MEASURES`
- `AT_TIME`
- `SUPPORTED_BY`
- `LOCATED_IN`

### Default Visible Graph

Visible by default:

- `Dataset`
- the most important `Entity` nodes
- the most important `Metric` nodes
- a curated subset of `RecordObservation` nodes

Hidden by default:

- all row evidence nodes
- all cell-level details
- most artifact nodes

### Inspector Behavior

When selecting a node, the right-side inspector should show:

- node summary
- typed relationships
- related record fields
- source row preview
- dataframe excerpt
- supporting table metadata

### Intended Takeaway

Users should immediately understand:

- the spreadsheet represents record observations
- the table is evidence, not the main graph center
- metrics and entities are organized through records, not through arbitrary fields

## Prototype 2: MD/TXT Bulletin-Oriented Graph

### Main Purpose

Show that bulletins should form a claim-and-metric graph rather than a chunk graph.

### Primary Node Types

- `Document`
- `Topic`
- `Metric`
- `Location`
- `TimePeriod`
- `Claim`
- `MetricObservation`
- `ChunkEvidence`
- optional `TableArtifact`
- optional `FigureArtifact`

### Primary Edge Types

- `HAS_TOPIC`
- `HAS_CLAIM`
- `STATES_METRIC`
- `ABOUT_LOCATION`
- `AT_TIME`
- `YIELDS`
- `SUPPORTED_BY`
- `LOCATED_IN`

### Default Visible Graph

Visible by default:

- `Topic`
- `Metric`
- `Location`
- `TimePeriod`
- `Claim`
- `MetricObservation`

Hidden by default:

- all chunk evidence nodes
- raw chunk ids and low-value structural references

### Inspector Behavior

When selecting a node, the inspector should show:

- claim summary
- related metric and value
- time and place
- supporting chunk text
- document locator or section hint

### Intended Takeaway

Users should immediately understand:

- the graph is driven by claims and observations
- chunks support claims instead of dominating the graph
- the semantic structure is clearer than a text-block network

## Prototype 3: DOCX Multimodal Narrative Graph

### Main Purpose

Show that graph construction for docx reports must connect text, table observations, and figure observations through a stable observation layer.

### Primary Node Types

- `Document`
- `Section`
- `Topic`
- `Claim`
- `TableObservation`
- `FigureObservation`
- `Metric`
- `Location`
- `TimePeriod`
- `TableArtifact`
- `FigureArtifact`
- inspector-only `DataFrameView`

### Primary Edge Types

- `HAS_SECTION`
- `HAS_TOPIC`
- `HAS_CLAIM`
- `HAS_TABLE_OBSERVATION`
- `HAS_FIGURE_OBSERVATION`
- `MEASURES`
- `AT_TIME`
- `ABOUT_LOCATION`
- `SUPPORTED_BY`

### Default Visible Graph

Visible by default:

- `Topic`
- `Claim`
- `Metric`
- `TableObservation`
- `FigureObservation`

Hidden by default:

- raw image nodes
- full artifact detail nodes
- dataframe row/column detail

### Inspector Behavior

When selecting a node, the inspector should show:

- observation summary
- related metric and topic
- supporting table or figure title
- dataframe preview
- artifact path or visual preview placeholder
- page and locator details

### Intended Takeaway

Users should immediately understand:

- the graph integrates narrative and visual evidence
- tables and figures support observations rather than crowding the main graph
- the observation layer is the key bridge between semantic understanding and traceability

## Shared Page Layout

All prototype pages will use the same seamless workbench layout:

1. `Top Bar`
2. `Left Semantic Control Rail`
3. `Center Graph Canvas`
4. `Right Inspector`

### Top Bar

Responsibilities:

- page title
- prototype subtitle
- current graph family tag
- lightweight scene switching

The top bar must stay compact and not become a general toolbar.

### Left Semantic Control Rail

Responsibilities:

- explain the current graph family
- expose layer toggle
- expose graph mode toggle
- show node legend
- show edge legend
- show short rationale text

The left rail is explanatory first, not control-heavy.

### Center Graph Canvas

Responsibilities:

- render the main graph
- prioritize semantic readability
- keep evidence details out of the first screen
- support one-degree reveal on interaction

### Right Inspector

Responsibilities:

- show node summary
- show attributes
- show relation interpretation
- show evidence and dataframe preview
- show locator details

The inspector is the primary place for evidence detail.

## Shared Interaction Model

All prototype pages will share the same interaction model:

### Graph Modes

- `Overview`
- `Trace`

`Overview` shows the clean semantic-first graph.
`Trace` shows the local semantic-to-evidence chain more explicitly.

### Layer Modes

- `Semantic Layer`
- `Observation Layer`
- `Evidence Layer`

The UI should never dump the full evidence layer into the graph by default.
Layer switching should remain curated.

### Node Interaction

- single click selects a node
- selecting a node updates the inspector
- selecting a node reveals one-degree related nodes if they belong to the current mode

### Evidence Strategy

Evidence should appear primarily in the inspector.
The graph may show a small number of evidence anchors in trace mode, but it should not become an artifact wall.

## Visual Direction

The gallery should look like a professional B-end SaaS analysis workbench:

- seamless split-pane layout
- no floating card pileups
- restrained but intentional color system
- strong typographic hierarchy
- graph readability over decoration

### Visual Priorities

- clear node role hierarchy
- stable visual grouping by layer
- low-noise edges
- inspector-first detail expansion
- consistent iconography and legend labels

### Suggested Role Colors

These are role-based rather than document-type-specific:

- semantic nodes: slate/ink accented by muted teal or muted blue
- observation nodes: warm neutral with amber or copper accent
- evidence nodes: pale neutral with low emphasis
- selected state: stronger contrast without glow-heavy effects

This spec does not require final production tokens yet, but the three pages should share a coherent palette.

## File and Directory Structure

The prototype gallery should live outside current production page code.

Recommended structure:

- `docs/superpowers/specs/2026-04-04-nonpdf-knowledge-graph-prototype-gallery-design.md`
- `frontend/prototypes/kg-gallery/index.html`
- `frontend/prototypes/kg-gallery/xlsx-record.html`
- `frontend/prototypes/kg-gallery/bulletin-text.html`
- `frontend/prototypes/kg-gallery/docx-visual.html`
- `frontend/prototypes/kg-gallery/assets/gallery.css`
- `frontend/prototypes/kg-gallery/assets/gallery.js`
- `frontend/prototypes/kg-gallery/assets/mock-data/`

Optional shared data files:

- `xlsx-record.json`
- `bulletin-text.json`
- `docx-visual.json`

## Implementation Boundaries

### What the prototype should do

- render the three graph families
- let the user compare structures quickly
- reflect the approved node/edge logic
- show inspector-based evidence grounding

### What the prototype should not do

- call live module4 endpoints
- mutate production graph state
- depend on Neo4j
- require a full backend service
- implement full graph editing

## Data Modeling Constraints

The implementation must avoid dataset-specific hardcoding in the graph model.

That means:

- do not build behavior around exact file names
- do not build final logic around exact Chinese labels from one sample
- do not hardcode graph shape from one spreadsheet only

Allowed:

- prototype-specific curated mock data files
- role-based graph rendering logic
- family-based graph presentation rules

The prototype can use curated sample data, but the structure of the renderer must remain family-oriented and generic.

## Error Handling

Even though these are prototypes, the pages should still behave predictably.

Expected safeguards:

- show an empty state if the mock graph payload is missing
- show a readable fallback if inspector data is incomplete
- avoid layout collapse when a node lacks evidence
- tolerate missing dataframe previews
- tolerate missing artifact titles or locators

## Testing Expectations

Prototype validation should include:

- all pages open successfully in the browser
- layer toggles work without console errors
- graph mode switching works without console errors
- node selection updates the inspector
- narrow viewport still preserves the split-pane structure acceptably
- long labels do not break the layout

## Success Criteria

The prototype gallery is successful if it lets the user answer all of the following clearly:

1. What is the correct graph center for xlsx files?
2. What is the correct graph center for bulletin-style md/txt files?
3. What is the correct graph center for docx multimodal reports?
4. Which nodes belong in the main graph versus the inspector?
5. How can the current Module 4 graph evolve toward these shapes without rewriting everything at once?

## Migration Path Into Module 4

The gallery is a precursor to later migration, not a disposable art exercise.

Recommended migration sequence:

1. migrate the shared workbench shell and inspector structure
2. migrate the graph modes and layer model
3. introduce family-aware graph adapters from Module 2 outputs into Module 4
4. replace or downgrade storage-first flat graph views in the main product where appropriate

The key principle is:

`prototype first to prove the right graph shape, then adapter-driven migration into production`

## Open Questions Resolved During Brainstorming

- Round one covers three representative prototype families, not all formats separately.
- Delivery form is a hybrid approach:
  - standalone HTML prototypes
  - shared design language
  - future migration path into Module 4
- The graph must be semantic-first and inspector-grounded.
- Evidence must not dominate the first-screen graph.

## Spec Review

**Status:** Approved

**Issues:**

- None blocking after self-review.

**Recommendations:**

- Keep round one intentionally narrow and avoid introducing live data wiring before the gallery proves the graph-family decisions.
- When implementation begins, isolate shared gallery primitives early so the later Module 4 migration can reuse them.
