# AI Metric Tree Agent PRD

Status: partially-superseded-current-metric-agent-only

> 当前事实：Agent 查询主轴已经收敛到 `metric_nodes` 与 `data_accounts`；旧 `report_accounts` 不属于运行时 query spec 契约，历史草稿必须改造为指标树节点或数据科目后才能进入当前链路。产品预算工作台相关确认流已被数据科目维护表取代。本文剩余内容只可作为后续 AI 配置草稿能力的候选材料。

## Problem Statement

预算系统的核心特色是 AI 能力。当前 AI 查询主轴已经改为 `metric_nodes` 与 `data_accounts`；后续 AI 配置草稿能力也必须围绕 **数据科目维护表**、**标准数据科目指标树** 和 Database PDD 自动完成，并在对话中自动把自然语言指标映射为系统内 `metric_node_code`。

当前风险是：如果后续继续从历史草稿复制实现，AI 可能重新引入已删除的旧表口径，或把缺配置误读为数据为 0。预算人员需要一个可控、可审计、可批量的 AI 工作流：AI 高效生成草稿和待确认项，用户负责确认主数据变更和最终下发。

## Solution

将 AI 板块统一到 **AI数据科目查询主轴**：自然语言先匹配 **标准数据科目指标树** 的 `metric_node_code`，再结合产品、部门、时间、版本和范围解析到 `data_account_metric_binding` 与 `data_account`。`report_account` / `report_data_mapping` 已删除，不再作为 AI 自动取指标、历史展示、迁移对照或旧接口兼容来源。

AI 自动配置支持 **AI单产品批量配置** 和 **AI跨产品批量配置**。两种配置都只生成 **AI自动配置草稿** 和待确认项，不直接下发。跨产品批量配置必须由用户显式选择 **AI批量配置范围**，例如产品组、多个产品或我的负责产品，不能默认覆盖全量产品。

一键 AI 配置结果按 **AI配置结果分组** 展示：已自动配置到草稿、待确认创建数据科目、待确认新增指标。AI 不能擅自新增全局指标树节点，也不能擅自创建数据科目；缺少指标时生成 **AI待新增指标建议**，缺少数据科目时生成 **AI待创建数据科目建议**。如果未来恢复这类能力，确认和落库必须进入当前 **数据科目维护表** / 指标树治理流程；不得恢复已下线的 **产品预算工作台** 作为确认流。

## User Stories

1. As a budget analyst, I want AI chat to map “收入”“费用”“贷款规模” to metric-tree nodes, so that I can query using the future data-account model.
2. As a budget analyst, I want AI chat to show the locked `metric_node_code` and metric name, so that I can trust which indicator is being queried.
3. As a budget analyst, I want non-leaf metric nodes to default to summary queries, so that “收入怎么样” returns a business total instead of forcing manual child selection.
4. As a budget analyst, I want to ask for “明细”“结构”“构成” and see child indicators expanded, so that I can analyze drivers behind a summary node.
5. As a budget analyst, I want leaf metric nodes with multiple data-account bindings to ask me for clarification, so that the system does not silently pick the wrong account.
6. As a budget analyst, I want missing product bindings to be reported as configuration gaps, so that I do not mistake missing setup for a zero value.
7. As a budget analyst, I want AI chat to offer a path into current data-account maintenance when a metric lacks bindings, so that I can complete configuration from the query flow.
8. As a budget analyst, I want the query plan to include product, department, data-account metric, time, comparison type, and granularity, so that I can confirm the full query before execution.
9. As a budget analyst, I want report-account terminology removed from the main AI query experience, so that the new workflow matches the unified metric-tree direction.
10. As a product budget owner, I want AI to configure one selected product in bulk, so that I can quickly initialize product-scoped metric/data-account draft rows.
11. As a product budget owner, I want AI to configure multiple explicitly selected products in bulk, so that I can prepare similar products without repeating manual setup.
12. As a product budget owner, I want cross-product AI configuration to keep results separated by product, so that one product's assumptions do not silently affect another.
13. As a product budget owner, I want AI-generated configuration to remain a reviewable draft, so that I can review it before dispatch.
14. As a product budget owner, I want AI to reuse existing metric-tree nodes first, so that the global indicator vocabulary stays controlled.
15. As a product budget owner, I want AI to generate pending data-account creation suggestions when bindings are missing, so that I can approve only the accounts I need.
16. As a product budget owner, I want AI to generate pending metric-node suggestions when the standard tree lacks an indicator, so that global master data changes require explicit approval.
17. As a product budget owner, I want AI configuration results grouped into draft, pending data accounts, and pending indicators, so that review work is clear.
18. As a product budget owner, I want AI formulas and source bindings constrained by Database PDD and current database facts, so that generated drafts do not invent fields or tables.
19. As a product budget owner, I want accepted AI configuration to anchor on `product_code + metric_node_code`, so that configuration aligns with the unified metric-tree model.
20. As a product budget owner, I want old report-account fields removed from active AI contracts, so that existing pages cannot keep depending on deleted tables.
21. As a product budget owner, I want to confirm pending data-account and metric-node suggestions inside the current data-account maintenance/governance flow, so that official master-data changes stay in one current surface.
22. As a system administrator, I want AI-created pending metric suggestions to require confirmation before modifying the global standard metric tree, so that master data governance remains intact.
23. As a system administrator, I want AI-created pending data-account suggestions to require confirmation before standard data-account persistence, so that data-account codes and scopes remain governed.
24. As a system administrator, I want cross-product bulk AI configuration to require explicit scope selection, so that AI does not create drafts across all products by accident.
25. As a maintainer, I want the Agent query spec to accept only `metric_nodes` and `data_accounts` for indicator identity, so that retired report-account keys are rejected instead of migrated.
26. As a maintainer, I want query and configuration modules to expose small testable interfaces for metric resolution and AI result grouping, so that behavior can be verified without end-to-end UI tests.
27. As a maintainer, I want retired report-account traces to be visible only in deletion evidence and filtering guardrails, so that no compatibility dependency remains hidden in business modules.

## Implementation Decisions

- Build a metric-tree resolution module that maps natural language to `data_account_metric_node`, then resolves `data_account_metric_binding` and `data_account` within the selected product or scope.
- Update the Agent query spec model to make metric-tree nodes and data accounts the only indicator query dimensions. Report-account fields must not remain in active AI planning contracts.
- Implement **指标节点汇总查询**: non-leaf metric nodes summarize all valid descendant metric bindings by default; explicit “明细/结构/构成” requests expand children.
- Implement **指标缺绑定响应**: if a metric node has no usable binding in the selected product or scope, the Agent returns a configuration-gap response with workbench actions instead of executing an empty query.
- Update pivot/search suggestions to use metric-node and data-account codes only.
- Update AI configuration references so they anchor on `product_code + metric_node_code`; do not reintroduce `report_acct_code` or the retired product-budget workbench.
- Add an AI configuration planning module that returns **AI配置结果分组** with three groups: configured draft items, pending data-account creation suggestions, and pending metric-node suggestions.
- Current data-account maintenance and metric-tree governance are the only valid confirmation surfaces for AI configuration review, pending data-account confirmation, and pending metric-node confirmation.
- Support **AI单产品批量配置** for one selected product.
- Support **AI跨产品批量配置** for an explicitly selected **AI批量配置范围**: product group, selected products, or 我的负责产品.
- Cross-product results must be grouped by product, and pending confirmations must remain product-specific.
- AI may initialize product-scoped draft rows from existing **标准数据科目指标树** nodes.
- AI must not directly create global metric-tree nodes. It creates **AI待新增指标建议** until user or administrator confirmation inside current metric-tree governance.
- AI must not directly create data accounts. It creates **AI待创建数据科目建议** until user confirmation inside current data-account maintenance, then standard data-account persistence creates codes, product scope, metric binding, and required fields.
- AI-generated configuration remains **AI配置草稿** until a current, explicit user action confirms it through the active maintenance flow.
- DeepSeek or other model output is a reasoning layer only. Database schema, Database PDD, current master data, data-account maintenance context, metric library, and Rules/Agent PDD are authoritative.
- Existing heuristic fallbacks may remain, but they must obey the same no-invented-fields, no-unconfirmed-master-data-change rules.
- Current code treats `report_account` / `report_data_mapping` as deleted. New code must not introduce report-account-first dependencies or compatibility aliases.

## Testing Decisions

- Test external behavior rather than LLM phrasing or internal prompt strings.
- Add tests for metric-tree resolution: exact name match, synonym match, non-leaf summary, child expansion, no binding, and multiple binding clarification.
- Add tests for Agent query planning to ensure natural-language metric requests populate metric-node/data-account dimensions instead of report-account dimensions.
- Add tests for missing binding behavior to ensure no SQL execution occurs and the response is a configuration gap.
- Add tests for AI configuration grouping to verify draft items, pending data-account suggestions, and pending metric-node suggestions are separated correctly.
- Add tests for single-product batch configuration to verify drafts are anchored on `product_code + metric_node_code` and not dispatched.
- Add tests for cross-product batch configuration to verify explicit scope is required and results are grouped by product.
- Add tests for guardrails: AI cannot create global metric nodes without confirmation, cannot create data accounts without confirmation, and cannot dispatch configuration.
- Reuse existing backend API test style around FastAPI routes and SQLite fixtures where practical.
- Add focused frontend tests only where state grouping or user action routing is complex; visual polish can be covered by manual regression unless a stable frontend test harness already exists.

## Out of Scope

- Reintroducing `report_account` and `report_data_mapping` tables.
- Rebuilding budget display reports on report-account compatibility.
- Building a separate cross-page master-data approval workflow outside current data-account maintenance and metric-tree governance.
- Allowing AI to directly dispatch active calculation configuration.
- Allowing AI to run cross-product configuration over all products without explicit user scope selection.
- Replacing DeepSeek or changing model provider strategy.
- Rebuilding the retired product budget workbench UI.

## Further Notes

- This PRD depends on the domain decision that the future AI query and configuration model uses **统一业务指标树** as the primary semantic anchor.
- The most important migration rule is simple: new AI behavior is metric-tree-first; report-account behavior is deleted/retired only, not a compatibility path.
- A good implementation should create a small number of deep, testable modules around metric resolution, query-spec normalization, AI configuration planning, and confirmation application.
- The safest rollout is to reject old report-account inputs at the contract edge, keep query/spec behavior metric-tree-first, and migrate any remaining draft UI wording before implementation.
