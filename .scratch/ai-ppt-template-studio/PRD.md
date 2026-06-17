Status: ready-for-agent
Category: enhancement

# PRD: AI PPT Template Studio - 经营简报智能模板

## Problem Statement

用户已经拥有一份专家制作的《一季度全行经营简报》PPT 模板。这份模板不是普通的视觉参考，而是包含 13 页经营汇报结构、原生 PowerPoint 图表、内嵌 Excel/XLSB 数据源、原生表格和经营结论文本的成品材料。

当前智能 PPT 能力可以基于场景生成一份通用经营分析 PPT，也已经支持原生可编辑图表。但从用户视角看，它仍然不够像现有经营简报材料：版式、信息密度、章节节奏、图表组合和分析表达都无法完全复刻专家模板。

用户真正需要的是一个高级、好用的 AI PPT 能力工具：它能读懂已有 PPT 模板，将模板中的页面对象变成可绑定对象，并基于预算系统内的数据自动刷新文字、表格、图表和结论，同时最大限度保留原 PPT 的视觉系统和 Office 原生可编辑能力。

## Solution

建设 **AI PPT Template Studio**，定位为“懂模板、懂数据、懂汇报逻辑的经营简报生产工具”。

系统不从空白页重新画 PPT，而是复制用户上传的经营简报模板，然后通过模板解析、绑定配置、指标取数、结论生成、原生图表数据刷新和质量检查，生成一份新的经营简报 PPT。

MVP 聚焦《一季度全行经营简报》前 10 页：

1. 封面
2. 目录
3. 经营概要
4. 客户
5. 业务
6. B/S
7. P&L
8. P&L-业务及管理费
9. 全行风险概览
10. 民营银行风险监测体系

集团口径和结束页暂不作为 MVP 的核心自动化范围。结束页可直接复制模板，集团口径后续扩展。

用户使用流程：

1. 管理员上传经营简报 PPT 模板。
2. 系统解析 PPT，识别每页文本框、表格、图表、内嵌数据源和候选绑定对象。
3. 管理员进入模板绑定配置 UI，在缩略图和对象列表上为文本、表格、图表配置绑定规则。
4. 业务用户选择模板、年份、季度、预算版本、实际版本、组织口径和产品口径。
5. 系统复制模板并刷新已绑定内容。
6. 用户下载生成后的 PPT，图表仍为 PowerPoint 原生 chart，背后保留内嵌数据表。
7. 系统同步给出生成质量报告，提示缺失数据、未绑定对象、图表刷新失败、文本溢出风险和人工确认项。

## User Stories

1. As a finance analyst, I want to upload an existing经营简报 PPT template, so that I can reuse expert-designed slide layouts instead of rebuilding decks from scratch.
2. As a finance analyst, I want the system to parse the PPT template, so that I can see every slide, text box, table, chart, and embedded data source that may need binding.
3. As a finance analyst, I want to view slide thumbnails in a binding workspace, so that I can navigate the template visually.
4. As a finance analyst, I want to click a slide and see its bindable objects, so that I can configure the page without editing raw JSON.
5. As a finance analyst, I want bindable objects to be grouped by text, table, chart, indicator card, note, and static object, so that I can understand what each shape is for.
6. As a finance analyst, I want AI to suggest likely bindings for template objects, so that I can configure complex slides faster.
7. As a finance analyst, I want to override AI-suggested bindings, so that final binding decisions remain under human control.
8. As a finance analyst, I want to bind a text box to report parameters such as year and quarter, so that cover and directory pages update automatically.
9. As a finance analyst, I want to bind a text box to an AI narrative rule, so that management commentary can be generated from actual metrics.
10. As a finance analyst, I want generated narratives to include traceable metric values, so that reviewers can verify where each conclusion came from.
11. As a finance analyst, I want to bind table cells to system metrics, so that经营概要 and P&L tables can refresh automatically.
12. As a finance analyst, I want to bind a table region to a metric matrix, so that multi-row management tables can be refreshed in one rule.
13. As a finance analyst, I want to bind a chart to system metric series, so that existing template charts refresh with new data.
14. As a finance analyst, I want refreshed charts to remain PowerPoint native charts, so that I can still edit chart data after downloading the deck.
15. As a finance analyst, I want refreshed charts to keep the original template styling, so that generated decks look like the existing management material.
16. As a finance analyst, I want to configure calculation modes such as current period, previous period,同比,环比,较年初, and预算完成率, so that binding rules cover management reporting logic.
17. As a finance analyst, I want to configure output units such as亿元、万户、百分比 and bp, so that generated values match existing report language.
18. As a finance analyst, I want to configure rounding and sign display, so that output values follow finance presentation conventions.
19. As a finance analyst, I want to configure missing-data behavior, so that absent values can render as blank, dash, unchanged template text, or a manual-review warning.
20. As a finance analyst, I want to mark a binding as manual input, so that values not yet available in the system can still be collected and inserted.
21. As a finance analyst, I want to save binding configurations by template version, so that future generations use the same mappings consistently.
22. As a finance analyst, I want to duplicate a binding configuration to a new template version, so that small template updates do not require starting from zero.
23. As a finance analyst, I want to validate a template binding configuration before generation, so that missing or inconsistent rules are caught early.
24. As a business user, I want to choose a registered经营简报 template, so that I can generate a report without understanding template internals.
25. As a business user, I want to select year, quarter, budget version, actual version, organization scope, and product scope, so that the generated report uses the intended口径.
26. As a business user, I want to generate a 10-page经营简报 MVP, so that most management meeting material can be prepared automatically.
27. As a business user, I want to download a generated PPTX, so that I can continue editing and sending the material in PowerPoint.
28. As a business user, I want generated PPT files to preserve the original layout and style, so that the deck looks like the official template.
29. As a business user, I want generated PPT files to preserve unbound slides and objects, so that the template remains complete even while automation is incremental.
30. As a business user, I want to regenerate only selected pages, so that I can fix or update one section without rebuilding the whole deck.
31. As a business user, I want a generation record, so that I can find previously generated decks and their parameters.
32. As a reviewer, I want a quality report after generation, so that I know which pages, objects, and metrics succeeded or failed.
33. As a reviewer, I want to see missing metric warnings, so that I can decide whether to regenerate, manually fill, or approve with caveats.
34. As a reviewer, I want to see unbound object warnings, so that I understand which template content remained unchanged.
35. As a reviewer, I want to see text overflow risks, so that I can adjust narratives before the deck is used in a meeting.
36. As a reviewer, I want to see chart refresh status, so that I know whether each chart is using current generated data.
37. As a reviewer, I want to see large movement warnings, so that surprising changes in key metrics get human review.
38. As an administrator, I want template parsing to be repeatable, so that template updates can be inspected and compared.
39. As an administrator, I want object identity to survive small template edits where possible, so that bindings do not break unnecessarily.
40. As an administrator, I want unsupported chart or embedded object types to be flagged, so that automation limitations are explicit.
41. As an administrator, I want binding rules to be exportable and importable, so that configuration can be backed up and moved across environments.
42. As an administrator, I want template versions and generation instances to be auditable, so that I can trace which template and data口径 produced a deck.
43. As a product owner, I want the MVP to cover 10 pages rather than only 4 pages, so that the delivered capability feels like a real management-report workflow.
44. As a product owner, I want the binding configuration UI to ship early, so that the product is a tool rather than a one-off engineering script.
45. As a product owner, I want customer-page chart refresh as an early POC, so that the hardest Office-native chart risk is validated before broad rollout.
46. As a product owner, I want the system to keep the existing scene-driven PPT generation separate, so that generic smart PPT and template-driven PPT can evolve independently.
47. As an AFK implementation agent, I want clear module boundaries, so that template inspection, binding, metric resolving, rendering, and quality checking can be implemented and tested independently.

## Implementation Decisions

- Build a new **template-driven PPT generation** path instead of extending the current scene-driven PPT renderer to imitate the existing template.
- Preserve the current scene-driven smart PPT capability as a separate mode. The new capability is **经营简报智能模板** / **AI PPT Template Studio**.
- Use **template cloning + targeted replacement** as the rendering strategy. The renderer copies the original PPTX and mutates selected text, table, chart, and embedded workbook content.
- The MVP covers 10 pages: cover, directory,经营概要,客户,业务,B/S,P&L,P&L-业务及管理费,全行风险概览,民营银行风险监测体系.
- The MVP does not require full automation of集团口径 pages. Those pages can remain copied from the template or be handled in a later phase.
- The binding configuration UI is part of the MVP and should be implemented before relying on broad template automation.
- The binding UI should use a three-panel workspace:
  - slide thumbnail/navigation panel
  - page object list/selection panel
  - binding rule configuration panel
- Bindable object categories include text, metric value, narrative, table, chart, manual input, and static object.
- Binding rules should be stored as versioned configuration associated with a registered PPT template.
- AI binding suggestions are useful but non-authoritative. Human confirmation and overrides are required for MVP usability.
- A deep module named **PptTemplateInspector** should encapsulate PPT parsing. Its stable interface should return a template structure report containing slides, objects, object identity, object type, text summary, table dimensions, chart metadata, and embedded data-source metadata.
- A deep module named **PptBindingService** should own template registration, binding configuration persistence, validation, and versioning.
- A deep module named **MetricResolver** should resolve binding rules into concrete values, time series, matrices, and derived calculations using current system concepts such as budget summary, metric node, data account, department, product, version, budget/actual口径,同比,环比,较年初,预算完成率.
- A deep module named **NarrativeGenerator** should generate management commentary from resolved metrics and narrative rules. MVP may use deterministic rules before introducing LLM generation.
- A deep module named **PptTemplateRenderer** should copy the PPT template and apply resolved content while preserving layout, styles, native tables, native charts, and editable embedded data where possible.
- A deep module named **PptQualityChecker** should produce a generation quality report with missing data, unbound objects, unsupported objects, text overflow risk, chart refresh status, and manual review warnings.
- A front-end **Template Studio** should be added or integrated into the smart PPT area with four workspaces: template library, binding workspace, generation center, and quality/revision view.
- Template registration should track at least template name, template version, source file, parse status, supported page count, and active binding configuration.
- Generated instances should track template version, generation parameters, output file, generation status, quality report, and generation time.
- Chart refresh should prioritize PowerPoint native chart data and embedded workbook refresh over image replacement.
- Existing original template formatting should take precedence over generated visual styling. The renderer should avoid recreating layouts from scratch.
- Unsupported chart/OLE cases should not silently fail. They should remain unchanged and appear in the quality report.
- Manual-input bindings should be supported so that data not yet available in the budget system can be entered during generation.
- Fixed/mock values may be used only to validate the end-to-end binding and rendering pipeline, and they must be flagged in the quality report.
- The user-visible product language should use current domain terms such as经营简报、模板、绑定、指标节点、口径、预算版本、实际版本、数据科目、部门、产品、生成实例、质量报告.

## Testing Decisions

- Tests should focus on external behavior and generated artifact structure, not implementation details of python-pptx internals.
- PptTemplateInspector tests should parse a known PPTX fixture and assert stable high-level structure: slide count, object categories, chart count, table count, and presence of embedded data sources.
- PptBindingService tests should validate that binding configurations can be created, updated, versioned, and rejected when referencing missing template objects or invalid metric rules.
- MetricResolver tests should use a controlled budget summary fixture to assert current period, previous period,同比,环比,较年初,预算完成率, unit conversion, and missing-data behavior.
- NarrativeGenerator tests should assert deterministic output for trend, budget-vs-actual, risk, and summary narratives using known metric inputs.
- PptTemplateRenderer tests should generate a PPTX from a fixture template and assert that:
  - original slide count is preserved
  - selected text values are replaced
  - selected tables are updated
  - native chart parts still exist
  - embedded workbook parts still exist where chart refresh is supported
  - unbound objects remain present
- PptQualityChecker tests should assert quality warnings for missing data, unbound objects, unsupported chart types, stale manual input, and long generated text.
- API tests should cover template registration, parse report retrieval, binding configuration save/load, generation, download path resolution, and quality report retrieval.
- Front-end tests should cover primary workflows at the component level where practical: selecting a template, navigating slide objects, editing a binding rule, generating a deck, and viewing quality warnings.
- Prior testing style in the project includes backend service-level tests and API tests using Python, plus TypeScript build checks for frontend DTO compatibility. This feature should follow that pattern before adding browser-heavy tests.
- Generated PPT validation should inspect the PPTX package structure, not just file existence. Good validations include chart XML parts, embedded workbook parts, slide count, and modified text content.

## Out of Scope

- Full 13-page automation in the first MVP. The first productized scope is 10 pages.
- Full集团口径 automation.
- Building a brand-new PPT design system from scratch.
- Replacing PowerPoint with a web-only presentation editor.
- Guaranteeing every possible PPT/OLE/chart variation can be edited in MVP.
- Fully autonomous AI decisions without human binding review.
- Real-time collaborative editing.
- Scheduled recurring generation.
- Direct integration with external Office cloud APIs.
- Pixel-perfect rendered screenshot comparison for every slide in MVP, unless later required by QA.

## Further Notes

- The template currently observed has 13 pages, many native charts, many embedded Excel/XLSB data sources, and dense finance-reporting tables. This reinforces the decision to clone and mutate the template rather than redraw it.
- The current smart PPT path is useful for scenario-driven decks, but the template-driven经营简报 should be implemented as a separate product path to avoid making the renderer responsible for both generic slide creation and template mutation.
- The riskiest technical spike is native chart data refresh while preserving the template's visual style. The customer page should be used as an early POC because it contains multiple charts and dense business semantics.
- The riskiest product workflow is binding usability. A JSON-only configuration would make the feature feel like an engineering tool; a binding UI is required for a genuinely高级好用的 AI PPT capability.
- The product should frame AI as a copilot for template understanding, binding suggestions, narrative drafting, and quality review. It should not hide uncertainty. Quality reports and manual confirmation are part of the core product experience.

## Comments

> *This was generated by AI during triage.*

## Triage Notes

**Recommendation:** Keep this as an `enhancement` parent PRD with state `ready-for-agent`.

**What we've established so far:**

- The PRD is sufficiently specified for agents to start decomposition work.
- The work is too broad for one AFK implementation issue because it includes template inspection, binding UI, metric resolution, template rendering, chart refresh, generation center, and quality reporting.
- The safest next step is to split this PRD into thin vertical-slice implementation issues. Each issue should produce an independently demoable path through schema/API/UI/tests where practical.
- No `.out-of-scope/` conflict was found.

**Recommended next triage action:**

- Run `to-issues` against this PRD and publish implementation issues under `.scratch/ai-ppt-template-studio/issues/`.
- Prioritize the first slice around template parsing and structure reporting, then template registration, then binding UI, then one chart-refresh POC.
