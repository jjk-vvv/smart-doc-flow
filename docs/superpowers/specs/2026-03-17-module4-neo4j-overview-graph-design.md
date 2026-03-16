# Module 4 Neo4j Overview Graph Design

Date: 2026-03-17

## Summary

This design defines the next product-facing behavior for the Module 4 graph workbench:

`single-file graph -> overview-first projection -> node-focused exploration -> optional evidence expansion`

The approved product direction is:

- Module 4 should feel like a Neo4j-style graph browser, not a raw artifact viewer
- the default view should be an overview graph, not a full evidence graph
- `Chunk`, evidence, and structural edges should be hidden by default
- node click and node drag must be separate interactions
- drag must be responsive and must not open node detail
- the first screen should emphasize semantic clusters instead of dense edge noise

This spec sits on top of the already-approved single-file graph isolation work.
It does not change the "one file -> one graph" boundary. It defines how that file graph should be projected, rendered, and explored in the frontend.

## Why This Spec Exists

The current file-scoped graph workbench is directionally correct, but its default experience is still too close to a raw graph dump.

The current problems are:

- edges visually cross and stack in the center of the graph
- many edge labels appear at once and create visual noise
- semantic edges and structural edges are mixed in the same initial view
- node dragging feels slow because the simulation overreacts during drag
- dragging a node currently opens node detail, which breaks graph browsing flow
- the graph does not yet present a clear "overview first, evidence later" exploration model

As long as those conditions remain true, the graph can still feel unstable or cluttered even when the underlying data boundary is correct.

## Goals

- Make the default Module 4 graph view readable on first load.
- Make the default graph feel closer to Neo4j Browser interaction patterns.
- Separate semantic exploration from evidence exploration.
- Keep the current single-file graph boundary intact.
- Make node dragging responsive and predictable.
- Ensure drag never opens the node detail inspector.
- Reduce edge and label noise without removing the ability to inspect evidence later.
- Introduce a stable graph projection layer between backend graph data and frontend rendering.

## Non-Goals

- Do not replace the GraphRAG pipeline.
- Do not remove evidence, chunk, or structural graph data from storage.
- Do not make the default view a multi-file graph.
- Do not make the right side of the page a permanent fixed detail panel again.
- Do not rely only on force tuning to solve visual clutter.
- Do not require immediate backend API redesign before the first frontend improvement pass.

## Approved Product Decisions

The following decisions were explicitly approved during brainstorming and are treated as fixed inputs:

- the default graph should be "more like Neo4j overview graph"
- the default graph should hide some `chunk`, evidence, and structural relationships
- node detail should appear from node interaction rather than living as a fixed right-side panel
- single click opens node detail in-place
- double click expands graph context
- drag must pin or preserve node position but must not open detail
- the default view should retain `Document + Entity + Community`
- `Document` should act as a lighter anchor, not the primary visual focus
- `Entity` should remain the main visual focus
- `Community` should organize clusters rather than dominate the graph

## Current State Findings

### 1. The graph renders a raw file graph, not a product-facing overview graph

The current frontend loads the file graph and renders it with minimal semantic projection.
This means the first screen still reflects too much of the imported graph structure instead of a curated overview.

### 2. Structural edges and semantic edges compete in the same initial frame

The imported graph currently includes relation families such as:

- `RELATED`
- `PART_OF`
- `HAS_ENTITY`
- `HAS_CHUNK`
- `IN_COMMUNITY`

These edges are all useful, but not all of them belong in the first screen.
When they are shown together, they produce unnecessary crossings and center congestion.

### 3. Edge labels are too eager

The current rendering logic shows many edge labels in modestly sized graphs.
This creates secondary clutter even when the graph topology itself would otherwise be acceptable.

### 4. Drag and click are still coupled

The current drag flow enters drag mode too aggressively and then calls node detail open on drag end.
That creates two bad outcomes:

- drag feels sticky or slow
- users see accidental detail popups after repositioning a node

### 5. The force graph still behaves like a general simulation, not a browser-quality explorer

The current force setup is more advanced than a naive implementation, but it still needs:

- a clearer separation between overview layout and evidence layout
- lower visual emphasis on edges
- less aggressive simulation reheating during drag
- a more deliberate notion of semantic focal nodes versus structural support nodes

## Product Experience Definition

Module 4 should behave like a graph workbench with two user-facing graph modes:

- `Overview Graph`
- `Evidence Graph`

### Overview Graph

This is the default mode on page load.

It should answer:

- what is this document mainly about
- which entities are central
- how do those entities cluster
- what communities organize the graph

### Evidence Graph

This is a user-invoked mode or local expansion state.

It should answer:

- what chunks support this entity or relationship
- which structure edges connect chunks, communities, and entities
- where a graph fact came from

The key principle is:

- overview mode explains the knowledge shape
- evidence mode explains the document grounding

## Architecture Overview

This design introduces a frontend graph projection layer with three explicit graph forms:

- `rawGraph`
- `projectedGraph`
- `focusedGraph`

### Raw Graph

`rawGraph` is the graph returned from the backend file graph endpoint.

It contains the full set of nodes and edges currently available for the selected file graph.

### Projected Graph

`projectedGraph` is the mode-aware graph derived from `rawGraph`.

It is the graph actually rendered in the canvas for the current mode.

This is where the default overview filtering rules are applied.

### Focused Graph

`focusedGraph` is the interaction-aware graph state used for local emphasis.

It supports:

- selected node neighborhood highlighting
- progressive expansion
- local evidence reveal
- edge and label emphasis for the current focus only

This layered approach keeps the renderer simple and prevents the full raw graph from dictating the user experience.

## Default Overview Projection

The default overview projection should keep the following node classes visible:

- `Document`
- `Entity`
- `Community`

The default overview projection should hide the following node classes unless explicitly expanded:

- `Chunk`
- future evidence nodes
- low-value structural helper nodes

The default overview projection should keep the following relation classes visible:

- selected high-value `RELATED` edges
- limited anchor or community skeleton edges needed to preserve graph readability

The default overview projection should hide the following relation classes by default:

- `PART_OF`
- `HAS_ENTITY`
- `HAS_CHUNK`
- `IN_COMMUNITY`
- other purely structural relations that do not help first-screen comprehension

### Projection Rules

The projection layer should apply these rules in order:

1. select the current file graph only
2. classify nodes into semantic, anchor, structural, and evidence roles
3. keep `Document`, `Entity`, and `Community`
4. suppress `Chunk` and evidence by default
5. keep semantic edges first
6. keep only the minimum anchor and community skeleton edges needed for cluster readability
7. remove isolated nodes that become meaningless after suppression unless they are the active `Document` anchor

## Visual Hierarchy

The default graph should use a clear role hierarchy.

### Document

Document is an anchor node.

It should:

- remain visible
- be smaller or lighter than dominant semantic nodes
- confirm file identity without pulling the whole layout into itself

### Entity

Entity is the primary semantic node type.

It should:

- dominate the first-screen visual hierarchy
- carry the most readable labels
- define cluster centers and semantic relationships

### Community

Community is a cluster organizer.

It should:

- help the graph read as grouped neighborhoods
- visually structure the entity field
- appear as a supporting semantic skeleton rather than a replacement for entities

### Structural and Evidence Objects

These should be visually secondary and absent from the default overview.

They appear only through explicit user drill-down or mode switch.

## Interaction Model

The graph interaction model should be:

- click to inspect
- double click to expand
- drag to reposition
- blank canvas click to clear focus

These actions must not overlap semantically.

### Single Click

Single click on a node should:

- select the node
- open a floating inspector near the node
- highlight the selected node neighborhood
- dim unrelated nodes and edges

Single click should not:

- trigger evidence expansion
- rebuild the entire graph
- jump layout state unexpectedly

### Double Click

Double click on a node should:

- expand local graph context
- fetch or reveal additional neighborhood information
- animate the new neighborhood as a local growth around the selected node

Double click should preserve the user's mental map and not replace the full graph wholesale.

### Drag

Drag on a node should:

- move the node immediately and responsively
- pin or preserve the node position after drag end
- allow surrounding nodes to settle smoothly

Drag must not:

- open the node detail inspector
- trigger click behavior after drag end
- cause the whole graph to re-enter a high-chaos layout state

### Blank Canvas Click

Blank canvas click should:

- close the floating inspector
- clear local highlight state
- keep the current layout and viewport intact

## Drag Behavior Design

Drag behavior needs its own explicit interaction state machine.

### Pointer State Model

The frontend should distinguish:

- press candidate
- click
- drag

Recommended pointer transition model:

1. `pointerdown` enters a press candidate state
2. movement below threshold remains a click candidate
3. movement above threshold becomes drag
4. once drag starts, click behavior is suppressed for that gesture
5. drag end only finalizes position and pin state

### Drag Threshold

A drag threshold should be introduced, for example in the `6px` to `8px` range.

This prevents micro-movement during click from being interpreted as a drag and prevents drag gestures from accidentally opening detail.

### Simulation During Drag

During drag:

- the dragged node should follow the pointer directly
- simulation reheating should be lighter than it is now
- alpha changes should be deliberate, not re-triggered aggressively on every move
- neighboring nodes should respond smoothly, not explosively

### Drag End

On drag end:

- preserve the node location
- keep or set pin state
- do not open inspector
- do not trigger expansion
- gently let the surrounding graph settle

## Edge Rendering Design

Edges must become visually supportive rather than visually dominant.

### Geometry

The renderer should move from simple straight center-to-center lines to path-based edges.

The desired edge geometry is:

- edge starts at the source node boundary, not the source center
- edge ends at the target node boundary, not the target center
- lightly curved paths for dense or hub-connected areas
- controlled fan-out where multiple edges share the same hub neighborhood

This change alone will substantially reduce the perception of crossing density.

### Edge Weight and Opacity

Default edge styling should become more restrained:

- lower base opacity
- thinner default stroke width
- stronger emphasis only for focused or selected neighborhoods

Edges should be quiet until the user asks for them.

### Edge Labels

Edge labels should be highly selective.

Default behavior:

- hidden for most of the overview graph

Visible only when:

- the edge belongs to the selected node neighborhood
- the edge is hovered
- the graph is sufficiently zoomed in and the visible edge count is small

Labels should also be offset from the path rather than stacked on top of midpoints in dense clusters.

## Layout Design

This spec does not require abandoning force layout.
It does require making force layout role-aware.

### Overview Layout Priorities

The overview layout should prioritize:

- readable semantic clusters
- less center congestion
- softer anchor influence from the `Document` node
- clearer cluster grouping around `Community`

### Role-Aware Force Strategy

Force behavior should differ by node role:

- `Entity`: main semantic layer
- `Community`: cluster skeleton layer
- `Document`: low-force anchor layer
- `Chunk` and evidence: secondary structural layer used mainly in evidence view

High-degree entity nodes should receive:

- stronger collision space
- somewhat longer semantic link distance
- enough repulsion to prevent center collapse

Document nodes should participate more weakly so they do not pull too many edges back into the center.

### Fit Behavior

Viewport fit should prioritize the readable semantic core of the graph rather than extreme outliers.

The fit logic should avoid shrinking the whole graph just because one or two leaf nodes sit far outside the main cluster.

## Backend Support

The first pass can be implemented largely in the frontend, but the backend should gradually expose clearer graph semantics.

### Recommended Backend Additions

Over time, node and edge payloads should expose role semantics such as:

- `node_role = anchor | semantic | structural | evidence`
- `edge_role = semantic | structural | evidence`

Examples:

- `Document -> anchor`
- `Entity -> semantic`
- `Community -> semantic`
- `Chunk -> structural`
- `RELATED -> semantic`
- `PART_OF`, `HAS_ENTITY`, `HAS_CHUNK`, `IN_COMMUNITY -> structural`

These semantics would let the frontend project the graph without relying only on hard-coded relation names forever.

### Optional Future Endpoint

An optional backend endpoint may later be introduced:

- `GET /module4/graph/files/{file_hash}/overview`

This endpoint would return a server-projected overview graph.

This is explicitly optional for the first implementation pass.
The initial improvement can and should happen with a frontend projection layer first.

## Error Handling

The graph workbench should fail visibly and specifically.

### If file graph is not ready

The UI should:

- show file-level graph status
- keep the current file context visible
- avoid falling back to a different file graph silently

### If overview projection removes too much

The UI should:

- show an empty-state explanation
- allow switching to evidence mode or broader relation visibility

### If detail fetch fails

The UI should:

- keep the current selection
- show a local error message
- not clear the graph or reset layout

### If expansion fetch fails

The UI should:

- leave the current graph untouched
- show a local expansion failure message
- keep the selected node active

## Testing Strategy

This design requires tests at the projection, interaction, and rendering levels.

### Projection Tests

- default overview keeps `Document`, `Entity`, and `Community`
- default overview hides `Chunk` and structural evidence layers
- overview projection preserves the current file anchor
- overview projection does not leave meaningless disconnected noise after filtering

### Interaction Tests

- click opens inspector
- double click expands neighborhood
- drag does not open inspector
- drag end preserves node position
- click after drag is suppressed for that gesture
- blank canvas click clears focus without resetting layout

### Rendering Tests

- default overview edge labels are suppressed in non-focused dense views
- focused neighborhood edges receive stronger emphasis
- visible edge count in overview mode is lower than in evidence mode for the same file graph

### Performance Tests

- drag frame time should improve relative to the current implementation
- simulation reheating should remain bounded during drag
- first paint should improve because overview mode renders fewer visible graph elements

## Milestones

### Milestone 1: Interaction Safety

Deliver:

- drag threshold
- click versus drag separation
- drag end no longer opens detail
- lighter drag simulation behavior

Exit criteria:

- users can reposition nodes without accidental detail popups
- drag feels meaningfully more responsive

### Milestone 2: Overview Projection Layer

Deliver:

- raw graph to projected graph pipeline
- default overview filtering
- focused graph highlighting rules

Exit criteria:

- first screen is visibly less cluttered
- overview mode uses only approved default node and edge classes

### Milestone 3: Edge Rendering Upgrade

Deliver:

- path-based edges
- boundary-aware link endpoints
- selective edge labels
- lower default edge noise

Exit criteria:

- central edge crossing perception is reduced
- labels no longer form dense stacks in the graph core

### Milestone 4: Role-Aware Layout Refinement

Deliver:

- role-aware force tuning
- better fit behavior
- stronger semantic cluster readability

Exit criteria:

- graph reads as clusters rather than a central tangle
- the document anchor remains present but visually secondary

### Milestone 5: Evidence Graph Mode

Deliver:

- explicit user-triggered evidence graph
- chunk and structural drill-down behavior
- reversible switch between overview and evidence semantics

Exit criteria:

- the user can move from "what is in this file" to "what evidence supports it" without losing context

## Acceptance Criteria

This design should be considered successful only when all of the following are true:

- the default single-file graph opens in overview mode
- the default overview graph retains `Document + Entity + Community`
- `Chunk` and structural evidence layers are not shown by default
- edge labels are not densely visible in the initial graph view
- clicking a node opens nearby detail and focused highlight
- dragging a node is responsive and does not open detail
- double clicking a node expands local graph context
- the graph remains clearly file-scoped and does not mix multiple files
- the graph feels closer to a Neo4j-style browser than a raw artifact renderer

## Risks

### Risk 1: Over-filtering the overview

If the overview projection hides too much, the graph may feel empty or misleading.

Mitigation:

- keep `Document + Entity + Community`
- allow drill-down and explicit evidence mode
- validate on several document types, not one sample only

### Risk 2: Frontend-only projection drift

If projection rules live only in the frontend forever, semantics may drift from backend intent.

Mitigation:

- add backend role fields later
- keep projection rules centralized in one frontend layer until backend semantics arrive

### Risk 3: Drag changes may destabilize selection logic

Separating click and drag can introduce edge-case regressions if gesture state is not modeled carefully.

Mitigation:

- implement an explicit press/click/drag state machine
- add interaction tests for threshold, cancel, and drag end behavior

## Final Recommendation

The best next move is not a generic layout tweak.
The best next move is to explicitly redefine the graph workbench as an overview-first explorer.

That means:

- keep the current single-file graph boundary
- add a frontend graph projection layer
- default to `Document + Entity + Community`
- hide structural and evidence layers by default
- make edges quieter and more selective
- separate click, double click, and drag into distinct user actions
- treat drag responsiveness and "no detail on drag end" as first-class interaction requirements

This is the cleanest path to making Module 4 feel like a real Neo4j-style graph browser while staying compatible with the existing GraphRAG pipeline and the approved single-file graph direction.
