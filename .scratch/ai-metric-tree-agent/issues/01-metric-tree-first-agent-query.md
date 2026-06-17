Status: superseded-by-current-agent-query-spec
Category: archive

> Current architecture note: Agent query identity already runs through the current `metric_nodes` / `data_accounts` contract. Do not implement this issue as written; use it only as historical context for future Agent configuration work.

## Parent

.scratch/ai-metric-tree-agent/PRD.md

## What to build

Make the Agent query flow resolve user-entered indicators through the **标准数据科目指标树** first. A budget question should lock metric-tree nodes and data-account bindings as the only indicator query dimensions; retired report-account fields must be rejected at the contract edge. If a resolved metric node has no usable data-account binding for the selected product or scope, the Agent should return an **指标缺绑定响应** instead of executing an empty query.

## Acceptance criteria

- [ ] Natural-language metric requests populate metric-tree/data-account query dimensions and never populate retired report-account dimensions.
- [ ] Non-leaf metric nodes default to summary behavior, while explicit “明细/结构/构成” requests can expand child indicators.
- [ ] Missing product or scope bindings produce a configuration-gap response pointing to the current data-account maintenance/governance flow, not a zero-value or empty SQL result.
- [ ] Multiple valid leaf bindings require clarification rather than silent selection.
- [ ] Pivot/search suggestions use metric-node and data-account codes, with no report-account fallback keys.
- [ ] Focused backend tests cover exact match, missing binding, multiple binding, and query-spec normalization behavior.

## Blocked by

Rewrite required against current `agent_query_spec.py` and `docs/development/current-system-map.md` before assignment.
