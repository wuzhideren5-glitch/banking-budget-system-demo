# Context

## Domain Language

- **BudgetDataWriter**: The module that owns `budget_data` writes and data-account lifecycle cleanup. It validates the rolling `current_month` window, formula-account write protection, conflict upserts, and `need_calc` assignment before any caller changes budget or actual detail values; callers must also use it when deleting facts for a removed data account.
- **预算事实唯一录入口**: 用户侧预算/实际/预测数值录入统一收口到 **机构及产品数据录入**。`budget_data` 仍是唯一事实表，`BudgetDataWriter` 仍是唯一写入服务；旧预算录入页面、`/api/budget-input/*` 和旧 Excel 导入链路已物理退休，不再作为兼容入口存在。
- **数据科目运行 Module**: The module that reads `data_account`, `data_account_metric_node`, and `data_account_metric_binding` after they have adopted **机构及产品指标体系** codes and meanings. It is a runtime read model and fact/formula contract consumer, not a second metric configuration surface.
- **预算管理模块**: 由预算工作台与规则配置、预算输入、预算输出组成的业务闭环。
- **预算输出**: 面向经营预算结果展示与交付的报表区，不等同于费用预算执行报表。
- **预算展示报表**: 预算输出中的年度预算/P&L展示报表，按全行、分产品、单产品等视角呈现预算结果。
- **部门费用预算管理模块**: 围绕部门科目、部门预算科目、BI 映射、费用执行明细、费用预测和费用预算执行报表形成的费用预算闭环。
- **费用责任部门**: `dept_account` 中 level=2 的叶子部门，是费用执行、费用预测和费用预算执行报表的责任归属口径。
- **部门预算科目**: `budget_subject_catalog` 维护的费用预算科目树，是部门费用预测表和费用预算执行报表的科目口径。
- **费用执行明细**: 从外部“部门费用执行”文件导入的原始实际发生明细，入库到 `expense_actual_detail_raw` 后作为费用实际数 Adapter，而不是全局预算事实表。
- **BI映射维护**: 部门费用预算管理模块中的费用执行明细导入映射配置；当前只保留 **BI-AI科目映射表** 和 **BI部门维护**。BI-AI科目映射表读取 `bi_ai_subject_mapping`，BI部门维护读取 `manage_dept_owner_mapping` 并维护“归口管理部门 -> 费用归属部门”的映射；旧 BI科目维护表 `control_item_subject_mapping` 不再作为兼容入口。
- **费用预测表**: 部门费用预算管理模块中的预测录入与计算表，使用 `expense_forecast_entry`、`expense_forecast_annual_entry`、规则结果和人工覆盖表作为私有状态。
- **费用预测逻辑配置**: 维护费用预测规则、参数、变量、重算和模拟测算的专业 Module，属于费用预测表的配置面。
- **业务支出成本收入比 Module**: 部门费用预算管理模块中的成本收入比分析与配置能力；年度库 `business_cost_income_*` 表是私有状态，报表读取由 `services/business_cost_income_ratio.py` 承载，录入、细项树维护、指标维护和分区引用校验由 `services/business_cost_income_commands.py` 承载。
- **产品预算工作台**: 已下线的旧配置入口；运行表和活跃迁移脚本均已退休，前端统一入口改为 **机构及产品** 与 **机构及产品指标**。历史档案只用于追溯，不是当前导入源、对照源或维护面。
- **产品预算配置包**: 历史产品预算工作台中围绕一个系统产品科目沉淀的一组预算配置；当前不再自动提升、导入或对照，任何仍有业务价值的配置必须按 **机构及产品指标体系** 和 **唯一指标号码** 重新录入。
- **原预算配置页面**: 旧“预算工作台配置”和“预算模板与规则”页面已退休；指标规则配置统一收敛到 **机构及产品指标**、费用预测逻辑配置和模拟测算等仍在导航中的专业 Module。
- **底稿产品名称**: Excel底稿中的产品页名称，是目标展示样式的一部分，但需要映射到 **机构及产品**。
- **运行产品清单**: 旧 `product_type` 维护对象彻底下线删除；产品名称和层级由服务按需从 `org_product_tree_snapshot` 展开，供预算展示、模拟测算和运行引用水合使用。任何新增、修改、删除或导入产品节点都必须从 **机构及产品** 进入。
- **展示版本槽位**: 系统中由用户选择的展示版本层级，用于把不同年度库和版本放入预算展示报表的对比列组。
- **报表展示版本**: 预算展示报表中从展示版本槽位里实际勾选并显示的版本列组。
- **全行总表**: 预算展示报表中的全行汇总视图。
- **分产品概览**: 预算展示报表中的跨产品对比视图。
- **单产品明细**: 预算展示报表中的单个产品预算明细视图。
- **机构及产品指标体系**: 由 `org_product_tree_snapshot`、`org_product_metric_table` 和相关录入/输出快照承载的唯一主指标体系，也是后续唯一指标配置入口；`AA/aa` 表示微众银行实体，“全行”是汇总/矩阵视角。
- **数据科目同体系表**: `data_account_metric_node`、`data_account`、`data_account_metric_binding` 已直接采用 **机构及产品指标体系**，同一编码必须表达同一业务含义。
- **数据科目运行指标树**: 由 `data_account_metric_node` 承载的运行指标树；本轮收拢后不再作为独立指标配置入口。产品面向的指标节点使用 `产品码.产品内指标码` 作为 `node_code`，例如 `A01.01.01.001`。
- **指标树第三/第四语义层**: 五级指标码中的第三、第四段用于表达业务对象与细分归属，例如贷款及融资资产、金融市场投资、存款负债、FTP定价、手续费及渠道成本等；正式叶子不再挂在 `.00.00` 占位层下。
- **机构及产品指标运行引用**: 由 `data_account`、`data_account_metric_binding` 和运行指标树共同组成的预算事实和公式运行引用体系；当前编码和名称直接跟随 **机构及产品指标体系**，只提供读取、导出和运行引用，不再提供独立维护、导入或第二套数据科目语义。
- **潘潘费用类迁移结果**: 潘潘旧费用类已并入 **机构及产品指标体系**，不再保留独立 99 保护页或独立保护页。
- **指标树父节点派生事实**: 指标树汇总只读取 **机构及产品指标体系** 中的 `horizontal_rollup`、`vertical_rollup` 和 `logic_code`。父节点必须先在机构及产品指标体系中确认成运行主键，系统才会写入 `budget_data.value_source='rollup'` 的事实行。旧 `metric_rollup_method` 已退休，不得作为配置、接口或数据库字段恢复。
- **唯一指标号码**: 面向产品维度的业务主键，正式形态为 `产品码.产品内指标码`，例如 `A05.01.01.001`。它首先来自 **机构及产品指标体系** 的已确认引用；同步到运行引用后，`data_account.data_acct_code` 必须等于 `data_account_metric_binding.metric_node_code`；`product_code` 是查询/展示维度；`scope_code` 由产品前缀派生并用于绑定校验。
- **指标功能族**: 用于把不同产品下“功能相似”的产品内指标主键归入同一分析族的治理字段（`functional_group_code`）。它只支持比较、筛选和人工治理，不代表指标口径天然一致，也不允许默认跨产品求和。
- **多维分析工具**: 面向预算汇总、跨年度对比、透视表、透视图、智能分析报告和智能演示 PPT 的分析区；它读取预算系统已经形成的结果口径，不承担主数据维护职责。
- **多维分析透视模型**: 多维分析工具中负责透视字段目录、字段取值、页字段筛选、搜索过滤、行列树聚合和数值展示格式的前端纯 Module；当前年度透视和多年度对比透视共享这套模型。
- **已删除旧报告科目表**: 历史 `report_account` / `report_data_mapping` 已从当前 schema 与运行库删除；不得作为兼容入口、迁移源、查询主轴或预算展示主事实源恢复。
- **源 Excel 指标痕迹**: 历史初始化导入时保存在 `ai_reason` 等字段里的追溯信息，只能用于排查导入来源，不是主数据，也不能作为新业务筛选、编码或公式依据。

## Relationships

- **预算管理模块** contains **预算输出** as the final presentation step after rules/configuration and input.
- **预算管理模块** no longer exposes **产品预算工作台** as a primary navigation entry.
- **产品预算工作台** data is retired historical state, not an adapter into **机构及产品指标运行引用** and not a second maintenance surface.
- **产品预算配置包** belongs to one **机构及产品** node only as historical migration context.
- **产品预算配置包** formula, parameter, template, binding, validation, and trial-calculation concerns are not auto-promoted; they become official only after being remodelled in **机构及产品指标体系** with current **唯一指标号码**.
- **预算展示报表** belongs to **预算输出**.
- **预算展示报表** is the first entry under **预算输出**.
- **预算展示报表** contains **全行总表**, **分产品概览**, and **单产品明细** views.
- **预算展示报表** must use real budget data from the budget system, not static demo data.
- **预算展示报表** uses **展示版本槽位** for V1/V2-style rolling forecast columns.
- **报表展示版本** is a user-selected subset of **展示版本槽位**; not every configured slot must be visible in the report.
- **预算展示报表** defaults to the current editable version plus show level 1; additional show levels are enabled by user selection.
- **预算展示报表** keeps monthly detail columns collapsed by default and lets users expand them when needed.
- **预算展示报表** uses **机构及产品指标体系** and **机构及产品指标运行引用** for row items; the Excel file is a style reference for layout and default display levels, not a separate report-account master-data source.
- **机构及产品指标体系** is the single maintenance surface for metric configuration. **机构及产品指标运行引用** directly uses the same metric codes and meanings, while still carrying runtime formulas, bindings, and budget fact contracts.
- **机构及产品数据录入** is the only user-facing budget fact entry surface. It may sync confirmed cells into `budget_data` through **BudgetDataWriter**; no second user-facing budget/actual entry page may coexist.
- **唯一指标号码** is the product-scoped metric key confirmed in **机构及产品指标体系** and then synced to `data_account_metric_node.node_code`. Old source Excel codes, orphan runtime rows, and report account codes must not participate in official identity.
- **多维分析工具** uses budget result read models such as `budget_summary`, `budget_pivot_aggregate`, `compare_budget_summary`, and `compare_pivot_aggregate`; it must not become a second maintenance surface for **机构及产品指标体系** or **机构及产品指标运行引用**.
- **多维分析透视模型** belongs to **多维分析工具** and is shared by current-year and compare-year pivot views.
- Old report-account tables must not receive aliases or new dependencies; budget output, formula configuration, charting, simulation, and AI behavior must resolve through **机构及产品指标体系** and **机构及产品指标运行引用**.
- The former 报告科目维护 workflow is retired as a business maintenance workflow rather than renamed into a new primary surface.
- **底稿产品名称** maps to **机构及产品** for data retrieval; product display names and hierarchy are read from the runtime product catalog expanded from **机构及产品** only as a runtime read model.
- **单产品明细** may be scoped to either a leaf **机构及产品** node or a parent product node, in which case it aggregates all descendant products.
- **分产品概览** shows user-selected product nodes as column groups; selected parent product nodes aggregate their descendant products.
- **预算输出** appears as a second-level navigation group under **预算管理模块**.
- **预算展示报表** is distinct from the existing **费用预算执行报表**.
- **部门费用预算管理模块** owns **费用责任部门**, **部门预算科目**, **费用执行明细**, **BI映射维护**, **费用预测表**, **费用预测逻辑配置**, and **费用预算执行报表** as one business loop.
- **费用执行明细** enters the system through **BI映射维护** and then becomes the actual-number adapter for **费用预测表** and **费用预算执行报表**.
- **费用预测逻辑配置** writes private rule state for **费用预测表**; empty optional rule-variable or override tables are not evidence that the Module is dead.
- **费用预算执行报表** is a read model over **费用责任部门**, **部门预算科目**, **费用执行明细**, and annual budget data; it must not become a second master-data maintenance surface.
- **业务支出成本收入比 Module** owns its input/output item tree, indicator definitions, and monthly actual/budget/forecast cells; item section and item id must match on every write so the read model never silently skips mismatched rows.

## Example dialogue

> **Dev:** "Should the annual P&L style report be added under the existing expense execution report?"
> **Domain expert:** "No. It is a new budget output entry in the budget management module, separate from the expense execution report."
