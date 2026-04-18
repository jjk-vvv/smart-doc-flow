# Dashboard Overview Design

Date: 2026-04-18

## Goal

Rebuild the web `dashboard` page into a project-wide command workbench that balances:

- platform situation overview (`60%`)
- actionable user-driven work continuation (`40%`)

The homepage should prioritize real user operation while still supporting external demo and presentation scenarios.

## Positioning

The page is not a module-specific status screen and not a decorative KPI wall.

It should answer four questions:

1. What is the platform doing now?
2. Where are the current bottlenecks or risks?
3. What outputs or activities happened recently?
4. What should the user do next?

## Information Architecture

The page is split into five layers:

1. Global status strip
2. Dual-core first screen
3. Module snapshot layer
4. Recent outputs and activities
5. Risk and recommendation layer

## First Screen

### Left side: platform overview

- workflow stages across module1 / module2 / module3 / module4
- current operational highlights
- short recent platform activity

### Right side: action panel

- continue work
- pending items
- quick actions

## Data Strategy

Use a hybrid aggregation model:

- keep `platform_assistant/bootstrap` as the guidance copy source
- use direct module API summaries for stable cross-module signals
- reuse module2 browser-side extraction state for recent extraction-specific context until a dedicated server-side summary exists

## Initial Backend/Data Sources

- module1 health endpoint
- module3 owner-scoped overview summary
- module4 health, graph files, alerts
- platform assistant bootstrap starter
- module2 browser-side extraction state

## Interaction Model

- every stage and module snapshot should support navigation
- continue-work items should deep-link users back into the corresponding module
- homepage should summarize, not replace module pages

## Visual Direction

- professional document-analysis workbench
- blue-slate structural palette
- restrained accents by module and risk level
- dense but readable layout
- no module2-only pipeline gimmicks on the homepage

## Constraints

- preserve existing app shell and sidebar navigation
- do not break existing module entry flows
- prefer additive API changes over risky rewiring
