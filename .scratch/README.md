# Local Issue Tracker

`.scratch/<feature-slug>/` 保存本仓库仍可继续评审、拆分或验证的本地 PRD、issue 和架构审计。已退休或仅作追溯的历史方案不再留在这里，统一归档到 `archive/handover/legacy_scratch_plans_20260603/`。

阅读规则：

- 当前事实以 `CONTEXT.md`、`docs/development/current-system-map.md`、当前 `apps/web` / `apps/api` 代码和运行库为准。
- 旧产品预算工作台、旧 `report_account` / `report_data_mapping`、旧 `driver_*`、旧预测工作台等方案已经退休；相关 PRD 只作为历史讨论材料。
- 若要恢复 `.scratch` 中任一方案，必须先按当前数据库表、前端导航和后端路由重新校验，并生成新的 issue/ADR。

当前 `.scratch/` 工作区精确清单（工作树门禁读取）：`ai-metric-tree-agent`, `ai-ppt-template-studio`, `architecture-deep-clean`, `budget-display-structure-row-key`, `data-account-export`, `intelligent-budget-simulation`, `intelligent-budget-system-prd`, `org-product-metric-tree-review`, `org-product-tree-review`, `product-dimension-data-account-maintenance`, `smart-report-ai-blueprint`, `ui-system-governance`。

当前仍可评审工作区：

| Work area | Current use |
| --- | --- |
| `architecture-deep-clean/` | 本轮代码库架构、工作树、数据库、前后端关系和文档门禁整理审计。 |
| `product-dimension-data-account-maintenance/` | 数据科目维护按产品维度指标树重塑的当前方案和 issue。 |
| `ai-metric-tree-agent/` | AI 指标树和数据科目问答相关的当前设计记录。 |
| `ai-ppt-template-studio/` | AI PPT 模板工作室相关的当前设计记录。 |
| `budget-display-structure-row-key/` | 预算展示结构行 key 和展示关系整理记录。 |
| `data-account-export/` | 数据科目导出相关当前记录。 |
| `intelligent-budget-system-prd/` | 基于会议纪要、口述需求、新增需求规格说明书、现有 PDD 和当前代码事实补写的项目级 PRD。 |
| `smart-report-ai-blueprint/` | 智能报告 AI 蓝图相关当前设计记录。 |
| `ui-system-governance/` | UI 系统一致性、页面治理和前端拆分相关当前记录。 |

已归档历史方案：

- `archive/handover/legacy_scratch_plans_20260603/product-budget-workbench/`
- `archive/handover/legacy_scratch_plans_20260603/product-forecast-driver-input/`
- `archive/handover/legacy_scratch_plans_20260603/report-account-retirement/`
