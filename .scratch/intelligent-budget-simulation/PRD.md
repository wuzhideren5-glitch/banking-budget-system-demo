Status: ready-for-agent

# PRD: 智能预算模拟工作台

## Problem Statement

预算系统当前已经有模拟测算正算和倒算能力，但它们主要服务于明确参数输入或目标倒算。真实经营管理中，领导经常给出较为含糊的经营目标，例如“净利润维持增长 10%”“不良率要控制到某水平”“风险不要明显上升”“规模别太冒进”。这些目标不能由单一参数解释，而是涉及规模、收益率、费用、风险、拨备、产品结构等多因素联动。

用户需要一个智能预算模拟板块，把领导自然语言目标转成结构化经营目标，在用户确认后，基于现有机构及产品指标体系、运行引用和预算事实，生成 Top 10 套目标满足且经营可接受的方案。方案要有不同经营侧重的候选来源，但最终排名必须由数学评分决定，不能由大模型拍脑袋。每套方案还需要能解释到二层经营因子和三层产品拆解，尤其要能说明风险目标如何通过新生成不良、回收/清收、拨备和不良率传导。

现有系统不允许恢复旧 `driver_*` 表或建立第二套预算公式体系。任何智能模拟结果都必须能追溯回机构及产品指标体系、机构及产品指标运行引用和预算事实。

## Solution

新增“智能预算模拟工作台”页面，放在现有模拟测算模块下，和“模拟测算（正算）”“模拟测算（倒算）”并列。该页面不改造现有正算/倒算链路。

用户输入领导自然语言目标后，系统调用 DeepSeek 解析为结构化硬目标、软偏好和可调因子。用户确认后，系统启动后端求解任务：先由公式感知步长算法生成二层和三层候选档位，再由二层 MOEA/D 生成不同经营偏好的经营因子组合，随后由三层 CP-SAT/MILP 做产品级拆解和配平，最后由数学评分自然筛选 Top 10。DeepSeek 只负责方案命名、解释、风险提示和无解协商话术，不参与最终排名。

页面采用单一工作台视图：顶部展示约束条件、领导目标、AI 解析结果、步长算法摘要和求解状态；中间展示 Top 10 方案卡片；右侧展示当前选中方案的树形传导拆解。树形拆解默认展示边际贡献最大的前 5 个产品，其余折叠为“其他产品”。

当无解或可行解不足 10 套时，系统进入协商模式。数学引擎定位冲突来源，DeepSeek 翻译成业务语言并提出可讨论方向。系统不得自动放宽约束，必须由用户确认后重跑。

第一版支持 Excel 导出，导出领导目标、约束摘要、步长摘要、Top 10 总览、二层经营因子组合、三层产品拆解和协商记录。

## User Stories

1. As a 预算负责人, I want to enter a fuzzy leadership target in natural language, so that I can start simulation from real leadership wording.
2. As a 预算负责人, I want DeepSeek to parse the leadership target into structured hard targets, so that I can confirm what the system will solve.
3. As a 预算负责人, I want the parsed target to show net profit and risk goals separately, so that I can verify the two main objectives before solving.
4. As a 预算负责人, I want the system to show soft preferences such as稳健、风险不激进、规模不冒进, so that implicit leadership intent is visible.
5. As a 预算负责人, I want to confirm the parsed objective before solving, so that AI interpretation cannot silently trigger a calculation.
6. As a 预算负责人, I want the first version to support net profit and NPL/risk level as main objectives, so that the most important management loop is covered first.
7. As a 预算负责人, I want scale, yield rate, expense, and risk to be adjustable factors, so that profit and risk targets can be reached through multiple business paths.
8. As a 预算负责人, I want the system to reuse 机构及产品指标体系 and 机构及产品指标运行引用, so that simulation formulas are traceable to current business definitions.
9. As a 预算负责人, I want the system not to restore旧 driver 表, so that intelligent simulation does not create a second source of truth.
10. As a 预算负责人, I want formula-aware step sizes, so that solution candidates use realistic increments instead of arbitrary decimal changes.
11. As a 预算负责人, I want a step-size algorithm summary before solving, so that I know the system considered formula sensitivity, history, and business execution units.
12. As a 预算负责人, I want sensitive variables to use finer candidate levels, so that high-impact factors are not searched too coarsely.
13. As a 预算负责人, I want low-impact variables to use coarser candidate levels, so that solving remains efficient and outputs are not noisy.
14. As a 预算负责人, I want second-layer business-factor solutions to have different preference directions, so that the candidate pool contains varied经营取向.
15. As a 预算负责人, I want MOEA/D to generate candidate factor families, so that Top 10 options do not all look like tiny variations of one solution.
16. As a 预算负责人, I want final selection to be by mathematical score, so that方案排序 is auditable.
17. As a 预算负责人, I want DeepSeek not to change ranking, so that AI explanations cannot override the scoring model.
18. As a 预算负责人, I want product-level decomposition, so that each business-factor solution explains which products carry the adjustment.
19. As a 预算负责人, I want product decomposition to respect product-specific limits and histories, so that solutions are operationally believable.
20. As a 预算负责人, I want CP-SAT/MILP or an equivalent solver to handle product allocation, so that product-level constraints and discrete step sizes are enforced.
21. As a 风险管理人员, I want risk modeling to include拨备调节、回收/清收提升、新生成不良控制, so that the risk path reflects real business levers.
22. As a 风险管理人员, I want NPL ratio to be derived from NPL balance and loan scale, so that the system does not treat NPL ratio as an isolated variable.
23. As a 风险管理人员, I want new NPL, recovery/collection, and write-off disposal to feed ending NPL balance, so that risk movements are internally consistent.
24. As a 风险管理人员, I want provision balance and excess provision to be derived, so that profit plans do not ignore risk buffer.
25. As a 风险管理人员, I want the system to distinguish risk improvement from scale dilution, so that lower NPL ratio is not misread as lower risk.
26. As a 风险管理人员, I want new NPL reduction to carry higher difficulty penalty, so that the solver does not overuse unrealistic natural-risk improvement.
27. As a 风险管理人员, I want recovery/collection improvement to carry medium difficulty penalty, so that operational intervention is possible but not free.
28. As a 风险管理人员, I want provision adjustment to be modeled as more controllable, so that artificial provision choices are represented separately from natural risk.
29. As a 预算负责人, I want the Top 10 cards to show rank, name, net profit achievement, risk target achievement, and core actions, so that leadership can scan solutions quickly.
30. As a 预算负责人, I want core actions to show numeric movements for scale, yield, risk, and expense, so that cards do not rely on vague prose.
31. As a 预算负责人, I want the selected solution to show a tree from leadership target to business factors to product contribution, so that I can explain how the result was reached.
32. As a 预算负责人, I want the tree to show the top 5 products by marginal contribution by default, so that the right panel stays focused.
33. As a 预算负责人, I want the remaining products grouped as other products, so that full product allocation is still accounted for without overwhelming the view.
34. As a 预算负责人, I want DeepSeek to name each solution, so that方案 can be discussed in leadership language.
35. As a 预算负责人, I want DeepSeek to explain risks and assumptions, so that mathematical outputs become understandable business proposals.
36. As a 预算负责人, I want solving progress to show stages, so that I know whether the system is parsing, generating steps, solving, decomposing products, scoring, or explaining.
37. As a 预算负责人, I want long-running solving to be task-based, so that the browser is not blocked by a synchronous request.
38. As a 预算负责人, I want to cancel deep solving, so that I can stop a long search without losing the confirmed input.
39. As a 预算负责人, I want no-solution cases to enter discussion, so that the system explains conflicts instead of silently relaxing constraints.
40. As a 预算负责人, I want fewer than 10 feasible solutions to also enter discussion, so that final output always meets the Top 10 solution-set standard.
41. As a 预算负责人, I want the system to suggest possible relaxation directions, so that I can choose whether to adjust targets, constraints, product ranges, step refinement, or search depth.
42. As a 预算负责人, I want every relaxation to require user confirmation, so that the system never changes the business premise automatically.
43. As a 预算负责人, I want Excel export, so that the result can be reviewed and circulated in existing budget workflows.
44. As a 预算负责人, I want exported Excel to include objective, constraints, step summary, Top 10, factor combos, and product decomposition, so that the result is auditable.
45. As a 系统管理员, I want DeepSeek credentials to live in backend environment variables, so that API keys are not exposed to the frontend.
46. As a 系统管理员, I want DeepSeek outputs schema-validated, so that malformed AI responses cannot enter the solver.
47. As a 开发人员, I want target parsing, step generation, MOEA/D, product decomposition, scoring, explanation, negotiation, and export to be separate modules, so that each can be tested independently.
48. As a 开发人员, I want simulation results to be traceable to current metrics and budget facts, so that debugging does not depend on black-box AI text.

## Implementation Decisions

- Build a new page named 智能预算模拟工作台 under the existing 模拟测算模块.
- Do not modify or replace existing 模拟测算（正算） and 模拟测算（倒算） pages.
- Use current 机构及产品指标体系, 机构及产品指标运行引用, and budget facts as formula and data sources.
- Do not restore旧 `driver_*` tables and do not introduce a second budget formula system.
- Introduce an 智能模拟传导模型 as an algorithm-layer mapping, not as a new source of business facts.
- First-version leadership objectives are net profit and NPL/risk level.
- First-version adjustable business factors are scale, yield rate, expense, and risk.
- Risk modeling first focuses on loan/credit products. Non-credit products may participate in profit factors but not the full risk submodel.
- DeepSeek parses natural language goals into structured JSON and the backend validates the JSON before any solve starts.
- Users must confirm parsed hard targets, soft preferences, adjustable factors, constraints, and step-size summary before solving.
- DeepSeek API keys and model settings live in backend `.env` settings such as `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`.
- DeepSeek names solutions, explains solution rationale, surfaces risk warnings, and drafts negotiation language.
- DeepSeek does not generate final numeric solutions, does not write budget facts, does not bypass constraints, and does not decide ranking.
- Formula-aware step generation is a deep module. It uses Morris-style screening, finite-difference local sensitivity, and MADS-style adaptive mesh refinement.
- The step-size module outputs candidate levels rather than a single manual step value.
- Second-layer steps are coarser and preference-oriented.
- Third-layer product steps are more mathematical and product-specific.
- Second-layer business-factor generation uses MOEA/D to create candidate solution families with different preference directions.
- Final Top 10 selection is natural mathematical scoring, not forced coverage of every preference label.
- Product-level decomposition uses CP-SAT/MILP or an equivalent discrete constraint optimizer.
- Product-level decomposition must respect product bounds, step candidates, history, concentration limits, and risk submodel consistency.
- Risk actions are modeled as拨备调节、回收/清收提升、新生成不良控制.
- NPL ratio is derived from ending NPL balance and ending loan scale.
- Ending NPL balance is derived from opening NPL balance, new NPL, recovery/collection, and write-off disposal.
- Ending provision balance is derived from opening provision balance, provision charge, and write-off provision consumption.
- Excess provision equals ending provision balance minus ending NPL balance.
- Risk scoring penalizes provision distortion, recovery improvement difficulty, new NPL reduction difficulty, write-off timing deviation, insufficient excess provision, and scale-dilution-only NPL improvement.
- Final score filters out hard-target failures first. It then ranks by target stability, business acceptability, historical fit, product decomposition quality, risk-action difficulty, excess provision buffer, and solution difference.
- Net profit overachievement is not inherently better. A solution close to the target with lower disruption can rank above a more aggressive solution.
- The page has one workbench view: top objective/constraint/status area, middle Top 10 cards, right selected-solution tree.
- Top 10 cards show rank, solution name, net profit achievement, risk target achievement, and numeric core actions.
- Cards do not show an operating disturbance score in the first-glance view.
- The right tree defaults to the top 5 products by marginal contribution to target achievement, with remaining products grouped as other products.
- Solving is task-based and exposes staged progress.
- If no solution or fewer than 10 feasible solutions exist, the system enters negotiation and requires user confirmation before rerun.
- First version supports Excel export only, not PPT export.

## Testing Decisions

- Tests should focus on external behavior and domain outcomes rather than implementation internals.
- Target parsing should be tested with deterministic DeepSeek fixtures and schema validation.
- Confirmation gating should be tested so solving cannot start before user confirmation.
- Formula-source tests should assert that the intelligent simulation path reads current metric/run-reference facts and does not depend on retired driver tables.
- Step-size tests should cover high-sensitivity variables, low-sensitivity variables, historical clamp behavior, business-unit rounding, and adaptive refinement behavior.
- MOEA/D tests should use deterministic seeds or fixtures to assert that candidate families cover multiple preference directions without requiring final ranking diversity.
- Product decomposition tests should verify that product sums match second-layer targets and that bounds, steps, concentration limits, and feasibility statuses are respected.
- Risk submodel tests should verify NPL balance, NPL ratio, provision balance, excess provision, actual loss, new NPL, recovery/collection, and write-off calculations.
- Risk scoring tests should verify difficulty penalties for new NPL reduction, recovery improvement, provision changes, and scale-dilution-only risk improvement.
- Final scoring tests should verify hard-target filtering, natural mathematical ranking, and similarity suppression.
- No-solution tests should assert negotiation output and confirm that constraints are not automatically relaxed.
- Fewer-than-10 tests should assert negotiation instead of silently showing an incomplete solution set.
- DeepSeek explanation tests should mock model responses and verify that ranking does not change after explanation generation.
- Frontend tests should cover the single workbench layout, target confirmation, status changes, Top 10 cards, and selected-solution tree defaulting to top 5 products.
- Export tests should verify workbook sheets for objectives, constraints, step summary, Top 10, second-layer factors, product decomposition, and negotiation records.
- Existing prior art includes budget simulation router/service tests, simulation export tests, org-product runtime reference tests, budget output contract tests, and frontend component/view-model tests.

## Out of Scope

- Generating a new official budget version.
- Writing final solutions back to `budget_data`.
- Replacing existing 模拟测算（正算） or 模拟测算（倒算）.
- Letting DeepSeek directly calculate final numbers or decide final rank.
- Restoring旧 `driver_*` tables or old prediction-driver pages.
- Building a second product master-data or budget formula system.
- PPT export in the first version.
- Full risk-submodel coverage for all non-credit products.
- Fully automatic relaxation of targets, constraints, steps, or product bounds.
- Manual editing of every individual generated step candidate in the first version.

## Further Notes

- The core product promise is “目标满足型经营可接受方案集”, not profit maximization.
- The most important engineering boundary is that AI produces structured intent and explanation, while deterministic algorithm modules produce and rank candidate plans.
- The most important mathematical boundary is the formula-aware step-size module. It should be built as a first-class tested module rather than hidden inside the solver.
- The most important risk-model boundary is distinguishing controllable provision actions from harder natural-risk improvement.
- The most important UI boundary is the single workbench: top confirmed premise, middle Top 10 cards, right tree explanation.
- If the solution later needs implementation issues, split them by deep module: target parser, transmission model, step generator, MOEA/D candidate generation, product decomposition, risk submodel, scoring, task orchestration, workbench UI, negotiation, and Excel export.
