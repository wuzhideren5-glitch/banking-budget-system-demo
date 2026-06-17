Status: ready-for-agent

# PRD: AI 智能报告蓝图

## Problem Statement

业务用户需要把已有 Word 经营分析报告变成可自动刷新的智能报告。当前实现偏向“用户手工设计模板、手工插入占位符、手工选择指标”，这与实际工作方式不一致：用户手里已有报告，希望系统自动理解报告内容，识别报告中的指标、公式口径、时间口径、预算/实际口径、分析段落和表格，再自动匹配现有数据科目和指标树。

在实际报告中，很多内容不是单一指标替换。例如“贷款规模同比下降，主要受前三个产品下降影响”属于分析任务，需要系统根据自然语言规则生成可执行分析计划，查询同比贡献、TopN 产品、归因说明，而不是简单匹配一个数据科目。

业务用户还需要一个低负担的确认流程。系统不应把整篇报告拆成复杂配置让用户逐段维护，而应自动处理高置信度内容，只把未匹配、低置信度、口径冲突、分析规则不完整等异常项交给用户确认。

## Solution

建设“AI 智能报告蓝图”能力：用户上传 Word 报告后，系统调用大模型解析报告结构，生成一份可刷新的报告蓝图。蓝图由结构块组成，包括普通文本、指标值、公式说明、分析任务、表格、图表和未匹配项。

系统将 AI 识别到的指标自动匹配到数据科目、指标树和现有公式；将同比归因、TopN 下降产品、预算偏差分析等自然语言内容识别为分析任务；将用户补充的自然语言规则翻译成结构化分析计划，并以业务语言展示给用户确认。

确认流程采用“异常项审核台”：高置信度匹配自动通过，用户只处理未匹配指标、低置信度匹配、口径冲突、分析任务参数不完整、无法结构化的段落。确认后，系统保存报告蓝图。后续用户只选择年度、版本、月份范围、预算/实际口径，系统即可自动刷新报告，预览并导出 Word。

## User Stories

1. As a 预算主管, I want to upload an existing Word report, so that I do not need to manually rebuild the report template from scratch.
2. As a 预算主管, I want AI to extract report sections, so that the system can understand the report as structured business content.
3. As a 预算主管, I want AI to identify metric names in the report, so that metric values can be refreshed automatically.
4. As a 预算主管, I want AI to match identified metrics to existing 数据科目, so that reports use the same data foundation as the budget system.
5. As a 预算主管, I want AI to match identified metrics to the 数据科目指标树, so that business terminology remains aligned with the existing indicator hierarchy.
6. As a 预算主管, I want high-confidence metric matches to be accepted automatically, so that I only review uncertain items.
7. As a 预算主管, I want low-confidence metric matches to be listed as待确认项, so that I can approve, replace, or reject them.
8. As a 预算主管, I want unmatched metric phrases to be shown with candidate matches, so that I can bind them quickly.
9. As a 预算主管, I want formula explanations in the report to be identified separately from metric values, so that formula口径 can be refreshed from the 数据科目表.
10. As a 预算主管, I want the system to detect 预算/实际口径 from report text when possible, so that refreshed reports use the correct `budget_actual` data.
11. As a 预算主管, I want the system to detect年度、月份、期间、版本口径, so that users do not need to re-enter obvious parameters.
12. As a 预算主管, I want to override年度、版本、月份范围、预算/实际口径 before preview, so that one report blueprint can be reused across periods.
13. As a 预算主管, I want ordinary paragraphs to be preserved as text blocks, so that narrative content remains stable.
14. As a 预算主管, I want analysis paragraphs to be recognized as analysis tasks, so that content like同比归因 is executable rather than static text.
15. As a 预算主管, I want to supplement analysis rules using natural language, so that I can describe cases that cannot be captured by fixed metric matching.
16. As a 预算主管, I want natural language analysis rules to be translated into a business-readable execution plan, so that I can confirm what the system will calculate.
17. As a 预算主管, I want the system to identify “规模下降前三产品” as a product-dimension attribution task, so that it can query and rank contributing products.
18. As a 预算主管, I want the system to identify同比、环比、预算偏差等比较类型, so that analysis plans use the correct comparison baseline.
19. As a 预算主管, I want the system to support TopN analysis parameters, so that I can choose top 3, top 5, or another ranking count.
20. As a 预算主管, I want the system to generate both summary text and detail tables for attribution tasks, so that the Word report contains explainable evidence.
21. As a 预算主管, I want AI assumptions to be visible, so that I can understand where the system made judgment calls.
22. As a 预算主管, I want unresolved issues to block blueprint finalization, so that refreshable reports are not created with ambiguous bindings.
23. As a 预算主管, I want confirmed bindings to be reusable, so that future reports with similar wording need less manual review.
24. As a 预算主管, I want report blueprints to be versioned, so that changes to matching rules or analysis plans are auditable.
25. As a 预算主管, I want to preview refreshed report output before download, so that I can verify numbers and analysis language.
26. As a 预算主管, I want to export refreshed reports as Word, so that output can be circulated using the existing reporting workflow.
27. As a 预算主管, I want generated report instances to store the selected parameters and data snapshot, so that historical outputs can be reproduced.
28. As a 预算主管, I want failed AI parsing or execution errors to produce actionable messages, so that I know whether to adjust the document, binding, or rule.
29. As a 系统管理员, I want AI API configuration to live in environment settings, so that credentials are not hardcoded into source code.
30. As a 系统管理员, I want AI parsing to degrade gracefully when the model is unavailable, so that basic report text extraction still works.
31. As a 开发人员, I want report parsing, matching, analysis planning, and rendering to be separate modules, so that each can be tested independently.
32. As a 开发人员, I want analysis tasks to execute behind stable interfaces, so that new task types can be added without rewriting the Word rendering flow.

## Implementation Decisions

- The primary product direction is “AI 报告结构理解 + 可刷新报告蓝图”, not “manual placeholder template editing”.
- Word upload remains the main user entry point. Manual template editing remains as a fallback or advanced tool, not the main workflow.
- The report blueprint is the core domain object. It should represent structured report blocks rather than raw placeholders.
- Report blueprint blocks should include at least: `text_block`, `metric_value`, `formula_explain`, `analysis_task`, `table_block`, `chart_block`, and `unmatched_item`.
- The AI inspection response should expose summary, blocks, issues, assumptions, warnings, and raw text excerpt.
- The confirmation UI should be an exception-focused审核台. Users handle only unresolved or uncertain items.
- High-confidence metric matches may be auto-accepted; low-confidence and unmatched items must become issues.
- Natural language analysis rules are allowed, but they must be translated into structured analysis plans before execution.
- Structured plans should be displayed in business language, not raw JSON.
- A first-class `analysis_task` module should be introduced as a deep module behind a stable interface: input report parameters and task plan, output text/table/chart-ready data.
- Initial analysis task types should prioritize同比归因、环比归因、预算偏差 TopN、产品维度下降贡献.
- Data matching should use existing 数据科目, 数据科目指标树, budget/actual formulas, value type, and existing report catalog language.
- Formula explanations should be sourced from data account formula fields according to selected预算/实际口径.
- Refresh parameters should include年度、版本、月份范围、预算/实际口径 and optional product/department/report dimensions.
- Report generation should use the confirmed blueprint and selected parameters to produce a preview before Word download.
- Generated report instances should retain parameter values, resolved values, analysis outputs, data snapshot, output file path, status, and error messages.
- DeepSeek integration should reuse the existing model client and settings. API keys remain in environment configuration.
- The configured model target for this feature is DeepSeek v4 pro via the existing DeepSeek-compatible chat completion interface.
- The current prototype endpoint for AI report inspection is acceptable as a tracer bullet, but production work should persist blueprints and confirmation decisions.
- Existing calculation metric support can remain, but it should be repositioned as one possible block/binding type under the broader blueprint model.
- Existing preview and Word generation capabilities should be refactored to render from blueprint blocks rather than only placeholder variables.
- The issue tracker entry for this PRD uses local markdown and is marked `ready-for-agent`.

## Testing Decisions

- Tests should focus on external behavior and domain outcomes, not implementation details.
- AI parsing should be tested with deterministic fixtures by mocking the model client and asserting normalized inspection results.
- Report text extraction should be tested with sample Word documents containing paragraphs and tables.
- Matching should be tested by feeding known report phrases and asserting high-confidence, low-confidence, and unmatched outcomes.
- Confirmation workflow should be tested by applying user decisions to inspection issues and asserting the resulting blueprint state.
- Natural language analysis plan translation should be tested with model-output fixtures and schema validation.
- Analysis task execution should be tested independently from Word rendering. Good tests assert returned rankings, contribution values, and generated summary text.
-同比归因 tests should cover positive growth, negative decline, zero baseline, missing comparison period, and TopN tie handling.
- Budget/actual tests should cover `budget_actual=0`, `budget_actual=1`, missing actual data for a selected version, and user-facing warnings.
- Preview rendering should be tested from a confirmed blueprint, ensuring unresolved tokens or unresolved issues do not silently pass.
- Word export should be tested by generating a document from a minimal blueprint and verifying visible text replacement.
- Existing test prior art includes backend compile checks, database migration checks via `ensure_databases()`, smoke tests for smart report preview/generation, and frontend production build checks.

## Out of Scope

- Full free-form autonomous financial reasoning without a structured plan confirmation step.
- Direct execution of natural language rules without showing a business-readable execution plan.
- Supporting old `.doc` format in the first production version.
- Full chart authoring and advanced chart styling beyond using chart-ready data blocks.
- Multi-user collaborative editing of the same blueprint.
- Enterprise-grade model evaluation, prompt A/B testing, and long-term feedback learning.
- Replacing the existing 数据科目管理、指标树、预算汇总 or version management systems.
- Fully automatic correction of missing source data.

## Further Notes

- This PRD intentionally reframes 智能报告 as an AI-assisted report understanding and refresh system.
- The previous manual placeholder approach is still useful as an internal rendering mechanism or fallback, but it should not dominate the user workflow.
- The most important product risk is black-box automation. Every AI-generated analysis task must be explainable and confirmable.
- The most important engineering seam is the analysis task executor. It should be a deep module with a small stable interface, because同比归因、TopN、预算偏差、结构变化 and future analysis types can grow quickly.
- If future work formalizes domain terminology, add glossary entries for 报告蓝图、结构块、待确认项、分析任务、自然语言分析规则 and 执行计划.
