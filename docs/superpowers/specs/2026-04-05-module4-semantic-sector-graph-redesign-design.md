# Module 4 Semantic Sector Graph Redesign

Date: 2026-04-05

## Goal

Refactor Module 4 knowledge graph rendering so non-PDF document graphs no longer collapse into a narrow vertical chain. The target experience is a professional graph workbench that matches strong RAG knowledge graph products in three ways:

1. The document's business meaning is readable at a glance.
2. Evidence, analysis, and alerts occupy stable visual regions.
3. Graph expansion interactions reveal detail without breaking spatial stability.

## Current Problems

1. Initial layout only uses base edges, so semantic structure does not participate in the first layout pass.
2. Most important node types are mapped into a single structural lane, which produces a tall vertical stack.
3. The default force-directed mode stabilizes around a weak seed shape instead of a meaningful semantic structure.
4. Switching overlays appear above the center of the canvas and interrupt graph reading.
5. Node visuals are too uniform, so users cannot infer semantic role quickly.

## Design Principles

1. Keep the existing backend data contract unchanged.
2. Avoid file-specific hardcoding. All layout behavior must come from node types, relation types, and graph structure.
3. Separate layout graph from visible graph. Hidden relations may still inform layout.
4. Prefer deterministic semantic sectors over uncontrolled force scattering.
5. Keep spatial memory stable when nodes or relations are revealed.

## Target Layout Model

The graph should use a semantic workbench model:

1. Center: Document node.
2. Upper-left sector: business context and topics.
3. Upper-right sector: observations and claims.
4. Right-lower sector: evidence nodes such as tables, figures, and images.
5. Lower-left sector: fields and structural data nodes.
6. Outer-right ring: business alerts.

This is not a decorative star chart. It is a reading-oriented graph workspace.

## Data-to-Layout Mapping

The refactor should introduce a layout planner that derives positions from semantic zones.

### Zone mapping

1. `document` -> `root`
2. `business_context`, `topic`, `community`, `entity` -> `context`
3. `observation`, `claim` -> `analysis`
4. `table`, `figure`, `image` -> `evidence`
5. `field`, `chunk`, `covariate`, unknown structural nodes -> `structure`
6. `business_alert`, `risk` -> `alert`

### Position strategy

1. Each zone has a stable anchor center, angle window, and ring spacing.
2. Nodes are distributed in multi-ring fans within their zone.
3. Ordering within a zone uses graph degree, confidence, semantic priority, and label.
4. Hidden but real semantic edges still contribute to layout clustering.

## Interaction Rules

1. Initial canvas shows stable base structure with hidden relation counts.
2. Clicking a node reveals its local hidden relations without reflowing the whole graph.
3. Non-relevant nodes dim during focused inspection.
4. Edge labels remain hidden until hover.
5. Zoomed-out view hides most labels; zoomed-in view reveals labels progressively.

## Visual Rules

1. Remove strong node shadows.
2. Use role-driven color families instead of a mostly blue palette.
3. Keep the background subtle and workbench-like.
4. Use distinct node shapes or silhouette cues where practical, especially for evidence and alerts.
5. Keep switching state out of the center of the graph.

## Implementation Plan

### Phase 1: Layout foundation

1. Extract graph semantic layout config into a dedicated feature file.
2. Build a deterministic semantic-sector position planner.
3. Allow layout to consume richer edge structure than the initially visible graph.

### Phase 2: Canvas behavior

1. Replace the current lane-based seeding with sector-based seeding.
2. Keep a controlled force pass only as a soft stabilizer.
3. Freeze or heavily damp layout after settle to preserve spatial memory.

### Phase 3: Visual semantics

1. Tune node sizes by role and importance.
2. Reduce visual noise from lines and shadows.
3. Improve label reveal thresholds and hidden-edge hinting.

### Phase 4: Regression and acceptance

1. Re-run the 16 non-PDF sample graphs.
2. Inspect representative `.docx`, `.xlsx`, `.txt`, and `.md` screenshots.
3. Confirm that no graph defaults back to the vertical-chain failure mode.

## Acceptance Criteria

1. The majority of non-PDF graphs visibly occupy multiple semantic regions instead of one narrow vertical strip.
2. Evidence-heavy files no longer place fields into a single long lower chain.
3. Graph switching no longer leaves a blocking card over the graph center.
4. No backend or API contract changes are required for the redesign.
