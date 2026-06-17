# Agent Prompt Assets

This directory stores the current prompt assets used by product-manager intent routing and query planning. It is current knowledge-base source, not runtime trace storage.

## Files

| File | Current use |
| --- | --- |
| `catalog_graph.json` | Current prompt/catalog graph metadata. |
| `product_manager_intent_catalog.md` | Current product-manager intent categories and descriptions. |
| `product_manager_intent_messages.json` | Current message examples for intent classification. |
| `product_manager_intent_metric_rules.md` | Current metric-selection and metric-grounding rules. |
| `product_manager_intent_org_hints.json` | Current organization and department hint data for intent routing. |
| `product_manager_intent_system.md` | Current system prompt for product-manager intent handling. |
| `product_manager_intent_user.md` | Current user prompt template for product-manager intent handling. |

## Rules

- Prompt changes must stay aligned with `CONTEXT.md`, `docs/development/current-system-map.md`, and the current “机构及产品指标主表 -> 运行引用表” sync contract. Prompt/catalog terms must not be sourced directly from orphan runtime rows.
- Runtime traces, failed conversations, and debug logs belong under `var/logs/agent/`, not here.
- Historical prompt drafts belong under `archive/` unless they are rewritten against the current database and frontend navigation.
