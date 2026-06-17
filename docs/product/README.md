# Product Docs Index

本目录只放当前产品、数据库、规则和 UI 文档。历史合并补丁、旧口径说明、团队交付原文、历史方案草稿和回退材料不得作为当前需求或 schema 权威；需要追溯时去 `archive/` 或 `.scratch/architecture-deep-clean/`。

当前 `docs/product/` 产品文档精确清单（工作树门禁读取）：`Banking_Budget_Agent_PDD.md`, `Banking_Budget_Database_ERD.md`, `Banking_Budget_Database_PDD.md`, `Banking_Budget_Files.md`, `Banking_Budget_Frontend_Design_Spec.md`, `Banking_Budget_Rules_PDD.md`, `Banking_Budget_System_PDD.md`, `Banking_Budget_UI_Module_Migration_Checklist.md`, `Banking_Budget_UI_Regression_Checklist.md`, `Banking_Budget_UI_Unified_PDD.md`, `Banking_Budget_multi_user.md`, `Banking_Budget_simulation.md`, `Intelligent_Budget_Simulation_PDD.md`, `Intelligent_Budget_System_PRD.md`, `OrgProduct_Matrix_Output_PDD.md`, `OrgProduct_Naming_Glossary.md`, `OrgProduct_RiskDriver_Matrix_Output_PDD.md`, `OrgProduct_RollingForecast_Calculation_PDD.md`, `部门费用分月补录格式.md`, `预算系统需求提交模板.md`。

## Reading Order

1. [`../../CONTEXT.md`](../../CONTEXT.md): 当前业务语言和禁止恢复的旧口径。
2. [`../development/current-system-map.md`](../development/current-system-map.md): 当前前端、后端、数据库、退休表和验证规则的事实地图。
3. [`Banking_Budget_Files.md`](Banking_Budget_Files.md): 当前代码目录、Module 和文件职责。
4. [`Banking_Budget_System_PDD.md`](Banking_Budget_System_PDD.md): 当前产品功能、页面和流程；先读文件顶部“当前阅读入口与权威边界”，再读正文，历史合并记录只用于追溯。
5. [`Banking_Budget_Database_PDD.md`](Banking_Budget_Database_PDD.md): 当前数据库表、字段、约束和运行库合同。
6. [`Banking_Budget_Database_ERD.md`](Banking_Budget_Database_ERD.md): 当前库表关系图。
7. [`Banking_Budget_Rules_PDD.md`](Banking_Budget_Rules_PDD.md): 工程底线、前后端一致性、导入导出和 UI 约束。
8. [`Intelligent_Budget_System_PRD.md`](Intelligent_Budget_System_PRD.md): 基于会议纪要、口述需求、新增需求规格说明书和当前代码事实补写的项目级 PRD。

## Current Supporting Docs

| Document | Use |
| --- | --- |
| [`Banking_Budget_UI_Unified_PDD.md`](Banking_Budget_UI_Unified_PDD.md) | 当前 UI 展示语言、页面密度、表格/树/弹窗统一要求。 |
| [`Banking_Budget_Frontend_Design_Spec.md`](Banking_Budget_Frontend_Design_Spec.md) | 前端视觉细节和组件风格参考。 |
| [`Banking_Budget_UI_Module_Migration_Checklist.md`](Banking_Budget_UI_Module_Migration_Checklist.md) | UI 模块迁移和已退休入口状态。 |
| [`Banking_Budget_UI_Regression_Checklist.md`](Banking_Budget_UI_Regression_Checklist.md) | 浏览器回归走查清单。 |
| [`Banking_Budget_Agent_PDD.md`](Banking_Budget_Agent_PDD.md) | Agent 状态机、澄清、查询和透视建议规则。 |
| [`Banking_Budget_simulation.md`](Banking_Budget_simulation.md) | 模拟测算正算/倒算当前设计。 |
| [`Banking_Budget_multi_user.md`](Banking_Budget_multi_user.md) | 多用户、登录、会话和权限目标。 |
| [`预算系统需求提交模板.md`](预算系统需求提交模板.md) | 新需求提交模板，旧口径处理必须走删除、归档或按当前模型重建。 |
| [`部门费用分月补录格式.md`](部门费用分月补录格式.md) | 部门费用补录格式说明。 |

## Archived Product Drafts

| Document | Status |
| --- | --- |
| [`archive/handover/legacy_product_docs/System_PDD_historical_merge_records_20260603.md`](../../archive/handover/legacy_product_docs/System_PDD_historical_merge_records_20260603.md) | System PDD 移出的历史合并、甄别和修正记录。只用于追溯来源和验收背景，不作为当前 schema、导航、接口或 Module 职责权威。 |
| [`archive/handover/legacy_product_docs/智能报告项目梳理_20260509.md`](../../archive/handover/legacy_product_docs/智能报告项目梳理_20260509.md) | 历史智能报告方案草稿。只用于追溯；当前智能报告以 `smart_report_*`、`AnalysisReportContent.tsx`、`routers/smart_reports.py` 和 `current-system-map.md` 为准。 |

## Documentation Rules

- 新增或修改业务口径时，同步更新 `CONTEXT.md`、`current-system-map.md`、相关 PDD 和本文索引。
- 新增当前产品文档时，必须在本文精确清单登记；归档或删除产品文档时，必须从该清单移除旧文件名。
- 当前 `README.md`、`CONTEXT.md`、`AGENTS.md` 和 `docs/**/*.md` 中的相对链接必须指向真实存在的文件；移动、归档或删除文档时同步更新入口链接，避免把不存在的文档继续标成当前权威。
- 旧 `report_account`、`driver_*`、预测工作台、假设参数、产品预算工作台、旧横向产品汇总字段只能出现在明确“已退休/历史/归档”的段落。
- 当前代码入口是 `apps/web/` 和 `apps/api/`；历史根目录 `src/`、`src_from_Figma/`、团队补丁目录和 release 包不是当前开发入口，旧前端根目录不应在活仓根目录重建。
- 如果 System PDD 的历史合并记录、旧文档、历史补丁或归档材料与当前代码冲突，以当前代码、当前运行库、`CONTEXT.md` 和 `current-system-map.md` 为准。
- 新的历史方案草稿不得继续留在 `docs/product/`；需要保留追溯价值时移入 `archive/handover/legacy_product_docs/` 并在本文登记。
