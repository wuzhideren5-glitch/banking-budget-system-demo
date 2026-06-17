Status: ready-for-agent
Category: enhancement

# PRD: 全局 UI 体系治理与金融表格规范

## Problem Statement

当前系统已经覆盖预算编制、主数据维护、费用管理、透视分析、智能报告、智能 PPT 和 Agent 助手等多个业务域。各模块在功能上逐步成型，但前端展示方式仍存在风格漂移：页面骨架、按钮层级、表格密度、卡片使用、颜色语义、空态错误态和导出操作尚未完全统一。

预算系统的核心用户是银行预算、财务和经营分析人员。用户需要的是一个直观好用、长期使用不累、迁移成本低的业务处理系统，而不是展示型驾驶舱、BI 大屏或宣传型首页。尤其报表、录入和透视模块需要接近 Excel 的强大表格能力：层级缩进、结构分组、展开收起、隐藏显示、筛选、冻结表头和关键列、单位切换、导出结构一致。

如果继续逐页美化，每个模块都会形成自己的表格和交互逻辑，后续新增功能也会继续复制差异。系统需要先沉淀一套全局 UI 规范和统一的 FinancialGrid / ReportGrid 组件体系，再以此迁移现有模块，并要求未来新功能默认遵守。

## Solution

建立“全局 UI 体系治理”作为前端设计和实现的长期基准。

全局风格定位为：现代金融企业办公系统，温馨、简洁、高级、低视觉压力。系统视觉遵循国际主流 enterprise web app 审美，采用浅色金融工作台、柔和背景、弱网格线、强结构线、小圆角、弱阴影、少浮卡。功能上提供 Excel 级表格能力，让预算人员可以按熟悉方式完成录入、复核、查询、展开、筛选和导出。

实施策略：

1. 先锁定 UI 风格和治理规范，形成后续新功能必须遵守的 PRD 与设计规范。
2. 先建设统一 FinancialGrid / ReportGrid 体系，而不是逐页做视觉补丁。
3. 表格体系分为展示版、列组/行组版、可编辑版和统一工具栏。
4. 先迁移最典型的报表和录入页面，建立可复用标杆。
5. 再统一普通业务页、AI 审核台、Agent 和智能报告/PPT 的视觉与交互。
6. 建立 UI 回归验收和截图基线，避免后续新模块重新漂移。

## User Stories

1. As a 预算填报用户, I want the system to look like a modern financial enterprise tool, so that I trust it for daily budget work.
2. As a 预算填报用户, I want table operations to feel close to Excel, so that I can move from offline workbooks to the system with low learning cost.
3. As a 预算主管, I want reports to support hierarchy, grouping, expand/collapse, filtering, and export consistency, so that online review matches offline report workflows.
4. As a 财务分析用户, I want report pages to prioritize the work area instead of dashboards, so that I can focus on numbers, structure, and exceptions.
5. As a system user, I want the interface to be warm, clean, and low pressure, so that long sessions of checking tables do not feel visually tiring.
6. As a product owner, I want new modules to follow one UI standard, so that the product feels coherent as the system grows.
7. As a developer, I want a reusable FinancialGrid / ReportGrid system, so that each module does not reimplement table grouping, freezing, editing, and states.
8. As a developer, I want clear acceptance criteria for UI consistency, so that AFK agents can implement module migrations without re-litigating visual taste.
9. As a reviewer, I want screenshot and viewport checks, so that future changes do not regress readability, density, or layout behavior.

## Design Decisions

- The system is a business processing system, not a display system.
- Do not use dashboard, big-screen, BI showpiece, marketing page, or full-page KPI-card visual language as the global style.
- The global visual direction is modern financial enterprise office UI: warm, concise, premium, quiet, and easy to read.
- Work area comes first. Module pages should open directly into operational surfaces such as tables, trees, forms, previews, and import flows.
- Report and input modules should provide Excel-grade capabilities while retaining modern web visual quality.
- Build FinancialGrid / ReportGrid as a system-level capability before broad module migration.
- Use weak grid lines and strong structure lines: ordinary cell lines are soft; group headers, summary rows, frozen boundaries, and hierarchy boundaries are clearer.
- Use small radii and weak shadows. Avoid rounded SaaS card-heavy layouts.
- Use shallow warm/neutral backgrounds and soft white working surfaces. Avoid high-saturation gradients and large dark canvases.
- Tables must support right-aligned numbers, fixed headers, key frozen columns, row hierarchy, grouping, expand/collapse, column groups, read-only/editable/locked/error states, and export consistency where applicable.
- AI surfaces should feel calm and explainable, not showy. AI suggestions require confirmation and quality feedback.
- Future feature PRDs and implementation issues should reference this PRD and the frontend design spec before defining UI behavior.

## Implementation Decisions

- Store governance and implementation issues under `.scratch/ui-system-governance/`.
- Use existing frontend stack: React, TypeScript, Tailwind, lucide-react, and current Vite build.
- Continue using the newly introduced design tokens and `bb-*` base classes as the first visual foundation.
- Evolve shared UI components in the repo rather than importing a heavy new component suite unless a later decision explicitly changes that.
- FinancialGrid / ReportGrid should begin as reusable components with narrow, demoable capabilities, then expand through vertical slices.
- Module migration should proceed after grid foundations exist, starting with the highest-value report and input pages.
- New feature work should not introduce one-off table shells, one-off toolbar styles, or arbitrary new color palettes unless approved by updating this PRD/design spec.

## Testing Decisions

- Every implementation slice should pass `npm run build`.
- Grid slices should include behavior-focused tests or demo fixtures where practical, especially for hierarchy, grouping, editing states, and toolbar actions.
- Module migration slices should be manually checked at 1024px and 1366px widths.
- Report and input pages should be checked for fixed headers, key column visibility, numeric alignment, and no whole-page horizontal scrolling.
- Export-related migrations should verify that page state and exported workbook/report structure remain consistent.
- AI surface migrations should verify that suggestions, warnings, and quality reports are visibly distinct from official business results.

## Out of Scope

- Rebuilding the entire frontend in a new framework.
- Introducing a dashboard/big-screen product direction.
- Replacing all business logic while doing UI migration.
- Recreating Excel completely in the browser.
- A single massive rewrite of all modules in one issue.

## References

- `Design docs/Banking_Budget_Frontend_Design_Spec.md`
- `Design docs/Banking_Budget_UI_Unified_PDD.md`
- `Design docs/Banking_Budget_UI_Module_Migration_Checklist.md`
- Existing System / Agent / Database PDDs

