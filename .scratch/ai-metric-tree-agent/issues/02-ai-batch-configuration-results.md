Status: retired-by-current-architecture
Category: archive

> Current architecture note: this issue still described confirmation inside the retired product budget workbench. Do not implement it as written; rewrite any future AI batch-configuration work around current data-account maintenance, metric-tree governance, and explicit user confirmation.

## Parent

.scratch/ai-metric-tree-agent/PRD.md

## What to build

Add **AI单产品批量配置** and **AI跨产品批量配置** behavior around `product_code + metric_node_code`. AI configuration should produce **AI配置结果分组** for each product: configured draft items, pending data-account creation suggestions, and pending metric-node suggestions. AI must not create data accounts, create global metric nodes, or dispatch configuration without user confirmation.

All confirmation actions must belong to the current **数据科目维护表** / metric-tree governance flow. Users should confirm pending data-account creation and pending metric-node creation through current master-data surfaces; the retired **产品预算工作台** must not be restored as the confirmation surface.

## Acceptance criteria

- [ ] Single-product AI configuration anchors generated draft items on `product_code + metric_node_code`.
- [ ] Cross-product AI configuration requires an explicit product scope and groups results by product.
- [ ] Results are separated into configured draft items, pending data-account suggestions, and pending metric-node suggestions.
- [ ] Missing data-account bindings produce pending data-account suggestions instead of automatic `data_account` inserts.
- [ ] Missing metric-tree nodes produce pending metric-node suggestions instead of automatic global tree inserts.
- [ ] Pending data-account and pending metric-node suggestions can be confirmed only from current data-account maintenance / metric-tree governance surfaces.
- [ ] AI-generated items remain reviewable drafts and are never dispatched automatically.
- [ ] Focused backend tests cover grouping, scope guardrails, and no-unconfirmed-master-data-write behavior.

## Blocked by

Rewrite required against current data-account maintenance and Agent contracts before assignment.
