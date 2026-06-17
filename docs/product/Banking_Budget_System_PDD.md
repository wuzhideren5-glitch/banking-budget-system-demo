# 银行业务预算管理系统及智能体（AI-Native Budget System）系统设计文档（System PDD）

| 项目 | 说明 |
|------|------|
| **文档版本** | v1.0 |
| **产品定位** | 面向银行业务的财务预算原型系统，集成传统数据编报与 LangGraph 智能体分析，实现 AI 原生的预算管理与测算体验。 |
| **界面主标题** | **管衡之家-财务预算智能体**（顶栏与欢迎文案以当前 `apps/web/` 实现和已确认设计为准；历史 Figma 导出材料只作归档追溯，不是当前运行入口）。 |
| **交付范围** | **当前目标版本**：公司内网 **多用户**——通过服务器地址 Web 访问，含登录会话与 **RBAC**；并支持“当前年度多版本透视”与“多年度对比透视（`compare.db`）”。演进路径见 **Rules「范围与演进」** 及本文 **§2.4**（与 Database PDD / ERD 表头 **「交付范围」** 一致）。信息架构、布局、控件与文案仍以 **Figma** 为准。 |
| **数据与编码权威** | **表结构、字段、约束及主数据编码（指标/数据科目、产品、部门、部门预算科目等）以 Database PDD 为唯一权威。** 历史 Figma 导出或归档前端样例中的编号、表格示例**仅作界面与前端逻辑参考**，持久化与校验必须与 Database PDD 一致。 |

---

## 0. 当前阅读入口与权威边界（2026-06-02）

本文只保留当前产品功能、页面流程和 Module 职责正文。新开发、重构和缺陷修复先读本节、`CONTEXT.md`、`docs/development/current-system-map.md`、`docs/product/Banking_Budget_Files.md` 和 Database PDD；不要从归档历史合并记录推导当前运行口径。

- **当前产品入口**以 `apps/web/src/app/workspaceCatalog.tsx` 和 `current-system-map.md` 的 Frontend Map 为准；历史 Figma、根目录旧 `src/` / `src_from_Figma/`、团队提交包和 release 包不是当前导航来源，且旧前端入口不应在活仓根目录重建。
- **当前数据口径**以 Database PDD、ERD、`CONTEXT.md` 和运行库合同为准；旧 `report_account` / `report_data_mapping`、旧 `driver_*`、预测工作台、假设参数和产品预算工作台只允许出现在已退休/历史说明中。
- **当前前后端 Module 关系**以 `current-system-map.md`、`Banking_Budget_Files.md` 和本文件 §2-§4 为准；页面组件不应重新拼接已经下沉到 `apps/web/src/lib/*Api.ts` 的后端路径。
- **历史合并记录**已归档到 `../../archive/handover/legacy_product_docs/System_PDD_historical_merge_records_20260603.md`，只保留追溯价值。若归档记录中的任何表、入口、接口或旧口径没有被本节、§2-§4、`current-system-map.md` 或 Database PDD 重新声明为当前主线，则不得作为新开发依据。

## 0.23 本轮架构收拢（2026-06-05）— 唯一机构及产品指标体系

本轮在 bin 机构及产品指标体系合入基础上收拢口径：机构及产品指标体系是唯一主指标体系、唯一指标配置入口；`data_account*` 仅作为机构产品指标运行引用，编码和名称必须与机构及产品指标表保持同一语义，不再作为第二套指标配置入口。系统不得再扩展中间映射层；历史 `metric_node_code`、`data_acct_code`、`org_product_ref` 等字段只作为迁移审计和兼容读取。

- **唯一配置入口**：业务新增、改名、调层级、公式和表单顺序，应优先在 `机构及产品` / `机构及产品指标` 入口完成。
- **数据科目同体系重构**：`data_account_metric_node`、`data_account`、`data_account_metric_binding` 继续服务预算运行，但编码、名称和层级直接采用机构及产品指标体系；例如 `AA.01.01.01` 在数据科目表中即表示 `利息收入`。
- **入口收口**：数据科目不再提供独立页面配置入口；前端新增、导入、删除和新增指标节点入口已下线。后端仅保留运行读模型、批处理 helper 和只读导出能力，对外新增/导入应用/删除直写 API 不再注册。
- **潘潘费用类迁移**：潘潘旧费用类已并入机构及产品指标体系，不再保留独立保护页或单独迁移流程。
- **实体口径**：`AA/aa` 表示微众银行实体；“全行”是汇总/矩阵视角，不等同于 AA 实体。
- **运行同步链路**：`services/org_product_metric_runtime_sync.py` 在机构及产品指标保存和启动初始化时同步 `data_account`、`data_account_metric_node`、`data_account_metric_binding`，并由库存门禁校验每条运行数据科目均存在已确认机构及产品指标来源。

## 0.22 本轮需求变更（2026-06-05）— bin机构及产品指标树体系合并

本轮从 `TeamSubmit_20260604_org_product_metrics.zip` 中只合入“机构及产品”指标树体系实质功能。该体系已在 §0.23 中明确升级为后续唯一主指标体系。

- **新增基础维护入口**：预算管理 → 规则配置台 → `机构及产品`、`机构及产品指标`，分别维护机构/产品树、单机构指标表、月内公式和 Excel 导入导出。
- **新增录入与输出入口**：预算管理 → 预算数据输入 → `机构及产品数据录入`、`机构及产品预测输出`，支持滚动预测录入、版本草稿/提交、输出运行和 Excel 导出。
- **模块边界**：`org_product_*` 是机构及产品滚动预测体系，也是后续唯一主指标配置体系；当前 `data_account`、`data_account_metric_node`、`data_account_metric_binding` 和 BudgetDataWriter 仍承担预算事实运行合同。机构产品数据录入默认保存版本快照，版本确认后可显式同步预算事实；同步只处理已确认、已进入同一数据科目体系的单元格，并且必须通过 BudgetDataWriter 写入 `budget_data`。写入成功后同步重建 `budget_summary` 和 `budget_pivot_aggregate`，让预算展示和透视表读取到本次机构产品录入结果。
- **预算展示配置接入**：预算展示配置可从已确认机构产品指标候选创建展示行。展示行保存 `org_product_ref`、机构/产品编码、指标表和机构产品指标编码作为迁移追溯身份，但取数仍使用底层 `data_acct_code`，不改变预算展示汇总和导出口径。
- **费用预测变量接入**：费用预测逻辑配置的“指标表达式”变量可以从已确认机构产品指标候选中选择。页面选择候选时先写入 `source_type=org_product_metric`、机构产品指标编码和 `org_product_ref`，保存、试算或重算前再统一解析为 `source_type=metric_tree`、`source_key=data_acct_code`、`source_subkey=实体/产品编码`，规则计算继续走当前指标树取数；规则读模型会从 `org_product_metric_table` 回填只读 `org_product_refs`，页面展示变量来自哪张机构产品指标表。规则模板下载会同步生成 `机构产品指标候选` sheet，提供可复制的 `org_product_metric` 变量映射 JSON；导入预览、导入应用、API 保存和规则试算时都会解析为计算可用的 `metric_tree` 变量。
- **差异排除**：提交包中的旧 `backend/` / `src/` 应用壳、旧数据科目页面、旧费用/Agent/配置文件和旧 PDD 历史口径不进入当前主线。
- **设计文档**：新增 `OrgProduct_Naming_Glossary.md`、`OrgProduct_RollingForecast_Calculation_PDD.md`、`OrgProduct_Matrix_Output_PDD.md` 和 `OrgProduct_RiskDriver_Matrix_Output_PDD.md`，用于后续继续改造该模块时统一术语。

## 0.21 本轮需求变更（2026-06-04）— 潘潘0602数据科目与投入产出表精准合并

本轮从 `TeamSubmit_20260602_panpan_budget_system` 的 185 个差异中只合入实质业务增量，不整包覆盖当前主线。

- **数据科目来源材料**：新增 `resources/business_inputs/科目和层级表.xlsx`，作为潘潘0602补充科目和层级的业务核对来源；当前运行权威仍是 `data_account`、`data_account_metric_node`、`data_account_metric_binding` 和 BudgetDataWriter。
- **投入产出/成本收入比维护**：成本收入比后台维护页增加产品模板选择器，用户按产品维护投入/产出明细和指标；明细支持绑定数据科目唯一指标号码、手工录入模式和取值模式。
- **投入产出专题概览**：沿用当前主线独立 `input_output_topic_overview` 页面、API 和 service，读取当前 `business_cost_income_*` 私有表，不恢复来源包中把专题概览挂回成本收入比路由的旧方式。
- **差异排除**：提交包中的旧式 `data_accounts.py`、`DataAccountContent.tsx`、`data_account_usage.py` 以及与本需求无关的费用执行、BI 映射、Agent、系统配置和整包发布脚本差异不进入当前主线；这些差异多数会覆盖当前已经完成的模块拆分和数据科目重构。

## 0.20 当前架构权威补充（2026-05-19）— Module 职责与历史兼容边界

本节是当前功能架构的优先解释层。归档的“本轮需求变更”只保留合并历史和验收追溯价值；若历史说明与本节冲突，以本节、`CONTEXT.md` 和 Database PDD 的当前权威补充为准。

- **机构及产品指标** 是预算配置、公式加工、预算输入、预算展示、模拟测算和费用预测指标表达式的唯一指标配置入口。机构产品指标运行引用只承载同码运行主键、公式消费和预算事实引用，不再维护第二套指标体系。
- **机构及产品指标树** 是指标口径主事实源。产品编码是指标主键第一段，产品中文名从“机构及产品”主表展开的运行产品清单读取。
- **BudgetDataWriter** 是 `budget_data` 写入和数据科目生命周期清理的唯一 Module。预算输入、导入、费用、模拟测算、Agent 或智能生成能力不得绕过它直接写入年度预算明细；删除数据科目时，也必须通过它清理年度预算事实行。
- **旧报告科目表已删除**：`report_account` / `report_data_mapping` 已于 2026-05-19 从当前 schema 和运行库删除，不再保留兼容入口或输入别名。报告展示、预算汇总、图表和智能查询统一通过标准指标树、数据科目绑定和年度预算事实/投影实现。
- **费用预测导出请求规划** 的默认版本归一化、按预算科目 `subject_id` 校验、事业群存在性校验和 owner 范围排序由 `apps/api/app/services/expense_forecast_export_plan.py` 统一承载；Excel 公式、金额单位、锁定单元格、按预算科目/按事业群文件名和字段排除逻辑由 `apps/api/app/services/expense_forecast_export.py` 统一构造，`expense_forecast.py` 路由只负责读取预测视图和返回文件流。
- **费用预测导入解析** 的普通模板、按事业群模板和按预算科目模板识别由 `apps/api/app/services/expense_forecast_import_parser.py` 统一承载。
- **费用预测导入请求规划** 的费用归属部门口径校验、“全部部门”事业群 owner 范围解析、按预算科目叶子科目校验和导入 parser 选择由 `apps/api/app/services/expense_forecast_import_plan.py` 统一承载；`expense_forecast.py` 路由只负责提供当前科目表和 owner 查询 Adapter。
- **费用预测导入预览判定** 的插入、更新、追加跳过、实际月跳过、事业群成员校验、归口管理部门校验和自动预测覆盖提示由 `apps/api/app/services/expense_forecast_import_preview.py` 统一承载。
- **费用预测导入应用写库** 的月度手工预测写入、自动预测人工覆盖写入、年度业务报送/资划建议写入、应用跳过计数和重算目标收集由 `apps/api/app/services/expense_forecast_import_apply.py` 统一承载；`expense_forecast.py` 路由只负责加载当前数据库上下文、触发规则重算、写审计日志并返回前端结果。
- **费用预测手工单元格保存** 的月度预测写入、人工覆盖清理和年度字段写入由 `apps/api/app/services/expense_forecast_cell_commands.py` 承载；它与导入应用共用 `apps/api/app/services/expense_forecast_write_commands.py`，避免同一张费用预测私有表出现两套写库口径。
- **费用预测人工覆盖保存/删除** 由 `apps/api/app/services/expense_forecast_override_commands.py` 承载；保存覆盖时同步写最终预测值，删除覆盖时恢复系统测算值，底层仍复用 `expense_forecast_write_commands.py`。
- **费用预测私有表 schema 准备** 由 `apps/api/app/services/expense_forecast_schema.py` 承载；它统一打开 `common.db`，执行当前 `expense_forecast_*` 表 bootstrap，并调用 `db_bootstrap/expense.py` 的当前合同校验拒绝旧 driver 物理结构，`expense_forecast.py` 路由不再直接维护 schema 准备 SQL。
- **费用预测规则定义命令** 由 `apps/api/app/services/expense_forecast_rule_commands.py` 承载；它统一写入 `expense_forecast_rule`、`expense_forecast_rule_param` 和 `expense_forecast_rule_variable`，更新规则时替换参数和变量行，删除规则时依赖当前外键合同级联清理参数/变量，`expense_forecast.py` / `expense_forecast_rules.py` 路由只负责保存后的读取、重算和响应装配。
- **费用预测规则读模型** 由 `apps/api/app/services/expense_forecast_rule_read_model.py` 承载；它统一读取规则行、参数、变量、测算结果、人工覆盖映射和按规则 ID 定位所属年版/费用归属部门/预算科目，供规则配置、导入预览、预测表、追踪和重算共享。
- **费用预测规则月度计算** 由 `apps/api/app/services/expense_forecast_rule_calculation.py` 承载；它统一处理余额分摊、逐月递增/自定义系数、指标表达式、指标树变量取数和测算依据 JSON，`expense_forecast.py` 路由只提供数据库上下文加载适配。
- **费用预测数据上下文** 由 `apps/api/app/services/expense_forecast_data_context.py` 承载；它统一读取费用责任部门 scope、部门预算科目树、归口管理部门继承、当前实际截止月、实际数 Adapter、手工预测、年度输入和年度预算映射，供预测表、导入预览、规则重算、追踪和导出共享。实际截止月只取 `expense_actual_detail_raw.import_kind='current_year_actual'` 中匹配成功且月份在 1-12 的当前明细，不再由路由直接查询。
- **费用预测表视图读模型** 由 `apps/api/app/services/expense_forecast_view_model.py` 承载；它统一处理 scope 视图和按预算科目 owner 视图的部门预算科目展示、父级汇总、实际月/预测月来源、费用责任部门归口限制、规则覆盖标记和年度经营分析字段，`expense_forecast.py` 路由只负责读取数据库上下文并校验 API 响应。
- **费用预测前端展示模型** 由 `apps/web/src/lib/expenseForecastViewModel.ts` 承载；它统一处理金额单位、导出字段、scope 文案、月度单元格来源提示、部门预算科目树/部门树构建、预算科目搜索、预测表可见行和按预算科目 owner 聚合树；按预算科目编制的预算科目选择器子视图由 `apps/web/src/app/components/ExpenseForecastSubjectPicker.tsx` 承载，费用归属部门表格子视图由 `apps/web/src/app/components/ExpenseForecastSubjectCompileTable.tsx` 承载，按预算部门与按事业群编制表格子视图由 `apps/web/src/app/components/ExpenseForecastScopeCompileTable.tsx` 承载，导入 Excel 弹窗由 `apps/web/src/app/components/ExpenseForecastImportDialog.tsx` 承载，导出字段选择弹窗由 `apps/web/src/app/components/ExpenseForecastExportFieldsDialog.tsx` 承载，页面组件只保留状态、主操作、API 调用和视图切换编排。
- **费用执行明细导入 schema 准备** 由 `apps/api/app/services/expense_actual_import_schema.py` 承载；它统一打开 `common.db`，执行 `expense_actual_import_batch`、`expense_actual_detail_raw`、BI部门映射和 BI-AI 科目映射当前表 bootstrap，并调用 `db_bootstrap/expense.py` 的当前合同校验拒绝旧字段/旧约束，`expense_actual_import.py` 路由不再直接维护 schema 准备 SQL。
- **费用预算执行报表前端展示模型与子视图** 由 `apps/web/src/lib/expenseBudgetExecutionViewModel.ts`、`apps/web/src/app/components/ExpenseBudgetExecutionControls.tsx`、`apps/web/src/app/components/ExpenseBudgetExecutionFilterControls.tsx`、`apps/web/src/app/components/ExpenseBudgetExecutionTreeReport.tsx`、`apps/web/src/app/components/ExpenseBudgetExecutionMetricTable.tsx` 和 `apps/web/src/app/components/ExpenseBudgetExecutionMatrixTable.tsx` 承载；展示模型统一金额单位、金额/百分比格式、localStorage key、主体/事业群/费用归属部门级联选项、查询/导出参数、页面摘要、树标题和月度列标签；控制栏只编排展示模式、金额单位、关键字、零值行和查询触发；筛选控件承载主体/事业群/费用归属部门、预算科目和费用月份选择；树形报表统一月报格式、部门模式和科目模式的 `ReportGrid` 列组、本年实际/去年同期列展开、行展开、行右键菜单和选中状态，月报指标表格统一业务费用、IT费用和日常费用分块的层级分组、部门标签合并、收起/展开、本年实际月度列、去年同期月度列、预算进度、同比/环比和空数据展示，矩阵表格统一 3.2 日常费用-分解至使用部门的动态预算科目列、本年实际月度展开、预算/进度列组和层级分组。页面组件只保留页面状态、加载/导出命令和子视图编排，不直接维护后端请求口径。
- **费用预算执行报表后端响应编排** 由 `apps/api/app/services/expense_budget_execution_report_resolver.py` 承载；它统一读取框架、费用执行实际、年度预算、上一年度实际、预算科目目录和筛选上下文，并组装查询、月报、部门模式、科目模式响应标题与说明文案。`expense_budget_execution.py` 路由只负责 HTTP 参数选择、上传解析、错误映射和导出文件响应。
- **费用预测规则重算结果写库** 由 `apps/api/app/services/expense_forecast_recalculation_commands.py` 承载；它统一写入 `expense_forecast_calc_result`、同步最终预测值，并在存在人工覆盖时更新覆盖行的系统测算值。
- **费用预测追踪明细读模型** 由 `apps/api/app/services/expense_forecast_trace.py` 承载；它统一输出 manual、auto、override 三类月度来源、最终值、系统值、覆盖值和测算依据。
- **PDD 当前权威与历史记录分离**：归档历史合并说明中出现的旧入口、旧表、旧导航和旧口径，只有在本节或后续正文中被重新声明为当前主线时才继续有效。

## 历史合并记录归档

历史合并、甄别和修正记录已从当前 System PDD 正文移出，归档到 `../../archive/handover/legacy_product_docs/System_PDD_historical_merge_records_20260603.md`。
归档记录只用于追溯来源、验收背景和被拒绝的旧实现；不得据此恢复旧表、旧导航、旧接口或旧 Module 职责。

---

## 0. 文档定位与权威性

### 0.1 四文档分工（阅读顺序建议）

| 文档 | 职责 |
|------|------|
| [**Banking_Budget_Rules_PDD.md**](Banking_Budget_Rules_PDD.md) | **工程底线**（MUST/SHOULD/MUST NOT）：财务单一事实来源、`budget_data`/`budget_summary`/`compare_budget_summary` 口径、`need_calc` 与预聚合、审计、安全与 AI 治理、Excel 血缘、当前前端落地目录 `apps/web/src/`；交付阶段见 Rules **「范围与演进」**。 |
| [**Banking_Budget_Database_PDD.md**](Banking_Budget_Database_PDD.md) | **数据模型（唯一权威）**：表/字段、物理名 snake_case、主数据编码规则、`Period.quarter`、`BudgetData`（**`budget_actual`** 区分预算/实际口径）、`BudgetSummary`、`operation_log`（`common.db`）等；**不以 Figma 示例为准**。 |
| [**Banking_Budget_Database_ERD.md**](Banking_Budget_Database_ERD.md) | **库表关系图**（Mermaid），与 Database PDD 同步。 |
| [**Banking_Budget_Agent_PDD.md**](Banking_Budget_Agent_PDD.md) | **Agent 设计权威文档**：LangGraph 状态机、意图分流（预算查询分析 vs 知识/通用问答）、澄清循环、只读 SQL 安全护栏、短期/长期记忆、六按钮交互规格、管衡人设与话术、评测指标与分期路线。 |
| **本文（System PDD）** | **产品目标、用户场景、功能与体验设计**（PRD + 功能设计）：按 Figma 归纳界面壳层、导航与模块；Agent 记忆与安全交互、Excel 导出惯例、技术路线概括；**不替代** Rules/Database 的条款与表结构。 |
| **当前 UI 规范 + 已确认设计** | 前端界面视觉、布局、交互与前端逻辑的评审参照；可交付实现位于 **`apps/web/src/`**（Rules **E.7**）。历史 Figma 导出材料只作归档追溯，不是当前运行入口，活仓根目录不再保留 `src_from_Figma/`。例外：（1）表头「交付范围」以内网多用户目标为准；（2）库表与主数据编码以 Database PDD 为准，不得以 Figma 示例覆盖。 |

### 0.2 交叉引用与冲突处理

- 工程与数据持久化约束：**以 Rules、Database PDD 为准**；若本文与之冲突，**修订本文**。
- **数据库与主数据编码**：**唯一权威为 Database PDD**；历史 Figma 导出或归档前端样例内的 mock 数据、示例编号**不定义**持久化契约。
- 界面样式、组件结构、布局比例、导航命名、典型前端流程：以当前 `apps/web/` 实现、统一 UI 规范和已确认设计为准；历史 Figma 导出材料只作为归档追溯，不能覆盖当前业务口径或运行入口。
- Rules 中「参见 System PDD」处，除另有注明外，常指 **§2.2** / **§2.2.1**（业务口径、`need_calc`、**value_type** 小数位）、**§2.3**（Agent）、**§2.5**（Excel 惯例）等对应小节。

### 0.3 本文职责（摘要）

- 描述产品目标、用户场景、功能设计与体验预期（与 Figma 导出对齐）。
- 需要条款级约束时**引用** Rules / Database PDD，避免重复定义已定型内容。
- 后端与实现细节在 **§3** 概括；栈选型与离线约束与 Rules **E.5**、**E.7** 一致。

> 2026-06-10 当前口径：机构及产品是产品维度唯一维护入口；旧“产品科目维护”页面、`product_type` 物理维护表和同名视图均已下线删除。本文早期章节中关于产品科目维护页、产品科目物理表或产品维度配置入口的描述，以 `CONTEXT.md` 和 `docs/development/current-system-map.md` 的当前事实为准。

### 0.4 界面用语与数据实体（避免歧义）

- **机构及产品** 对应产品层级主表快照 **`org_product_tree_snapshot`**；旧 **`product_type`** 对象不再保留。
- **机构产品指标运行引用 / 机构及产品 / 部门科目 / 部门预算科目**与当前运行库表一致；**字段定义、编码规则、校验与持久化**以 **Database PDD** 为准。**各维护页的控件布局、交互、空态与视觉**以当前前端实现和设计规范为准。

### 0.5 数据科目层级演进（2026-05-08）

- 机构产品指标运行引用、预算输入和模拟测算统一采用“产品前缀指标树 + 运行引用明细”的层级体验：产品编码进入指标主键第一段，同一产品下指标体系只在“机构及产品指标”维护。
- 业务层级编码采用“产品编码 + 产品内指标编码”的方式表达完整路径，例如叶子 `A05.01.01.001`、父节点派生 `A05.01.01`；其中产品级编码必须直接来自“机构及产品”主表。
- `data_account.data_acct_code` 是公式、预算明细和展示汇总的唯一引用键；它必须等于唯一指标号码。
- 新增指标身份时，用户只在“机构及产品指标”维护产品前缀指标主键；机构产品指标运行引用由保存/启动同步生成同码运行记录。
- 父节点汇总/倒算结果仍落在唯一事实明细表 `budget_data`，以 `value_source='rollup'` 标记为系统派生事实；预算输入、手工导入和手工补录不得写入或覆盖 `rollup` 行。

---

## 1. 产品需求（PRD）

### 1.1 核心目标

1. **类 Excel 的预算编报体验**：高密度表格录入与查询；界面极简紧凑，优先利用 PC 宽屏（**视觉与布局以 Figma 为准**）。
2. **财务智能体（Agent）**：基于 LangGraph 与 Deepseek API，支持同环比、预实对比、滚动预算与复杂测算（目标求解等）；安全与确认流见 **§2.3** 与 Rules **E.3**；**右侧「智能助手」面板布局与按钮以 Figma 为准**。
3. **数据架构**：**`common.db`**（字典、**`operation_log`** 全库审计等）+ **`budget_{year}.db`**（**`version`、`budget_data`、`budget_summary`**）；底层业务数值落在 **`budget_data`**（**`budget_actual`** 区分预算/实际口径），由 **`data_account`**、**`data_account_metric_node`** 和从 **`org_product_tree_snapshot`** 展开的运行产品清单等约束颗粒度与公式；预算展示配置和部门科目提供展示/汇总维度，汇总由引擎计算并落入 **`budget_summary`**（**禁止**用前端自算替代引擎结论，Rules **E.1**、**E.4**）。
4. **大规模字典与效率**：支持 **Tab / 方向键**（Rules **E.6**）及树状映射维护（交互以 Figma 为准）。
5. **版本与留痕**：高频版本迭代；顶栏常驻**软件版本**、**预算年份**、**预算版本号**、**预算版本名称**等（字段布局以 Figma 为准）；变更审计见 Rules **E.2** 与 `operation_log`。

### 1.2 核心用户场景（与左侧导航模块对齐）

- **规则与主数据维护**：**机构及产品**、**机构及产品指标**、**部门科目维护**、**部门预算科目维护**、**BI映射维护**；机构及产品是产品维度和产品指标的唯一维护入口，预算展示配置收敛在**预算展示报表**内，不恢复独立旧报告科目维护、旧数据科目运行表或旧产品科目维护入口。**公式编辑器**、Excel 导入等以各页工具栏为准。
- **预算数据输入**：**机构及产品数据录入** — 在机构/产品指标体系上下文中维护预算、实际和预测事实。确认同步时，已确认且已绑定数据科目的单元格通过 **`BudgetDataWriter`** 写入 **`budget_data`**；持久化字段 **`budget_actual`** 仍表达预算/实际口径（**`0`**=预算，**`1`**=实际，见 Database PDD）。落库粒度为 **数据科目 × 产品 × 期间 × 版本 × `budget_actual`**。旧预算实际录入页和旧预算 Excel 导入链路已物理退休，不得作为第二录入口恢复。
- **多维分析工具**：**数据透视表-当前年度多版本透视**、**数据透视表-多年度对比透视**、**多年度数据透视图**、**智能分析报告**、**智能演示PPT**；前者读取 **`budget_summary`**，后者读取 **`compare.db.compare_budget_summary`**，均以预聚合结果与引擎结论为准（Rules **E.1**、**E.4**）。两类透视表界面的「指标层级 / 数据科目」行维度文本应**左侧顶格**显示，不使用层级缩进。
- **系统配置中心**：**用户和权限管理**、**系统设定控制** —界面信息架构与 Figma 一致，并落地用户维护、数据库文件维护、版本管理、编辑版本/展示版本管理等能力（见 **§2.4**）。
- **帮助与使用说明**：**使用说明**、**常见问题**、**联系管理员**（内容与结构以 Figma 为准）。其中若出现 **PDF** 等非 Excel 导出表述，**以产品分期为准**；当前工程验收上 **Excel 导出血缘**以 Rules **E.6** 为准。
- **版本管理**：创建/切换版本、在历史版本上修改等产品行为以 Figma 为准；**凡改必记**（Rules **E.2**）。
- **滚动预算与预实**：按业务规则拼接视图；展示与结论以引擎及 **`BudgetSummary`** 为准。
- **Agent 分析**：口径确认、取数、联动工作区；**高危写库**须 SQL/影响行与确认（Rules **E.3**）。
- **目标求解**：沙箱/临时库迭代；应用前满足版本与审计策略。

---

## 2. 功能设计（FDD）

### 2.1 界面壳层与信息架构（以当前 `apps/web/` 与已确认设计为准）

**总则**：整体为 **顶栏 + 中部可调整宽度的三栏 + 底栏状态栏**。中部三栏为 **左侧导航**、**中间工作区**、**右侧智能助手**；左右栏可**折叠**为窄条并一键展开；栏宽通过可拖拽分隔条调整。可交付代码在 **`apps/web/src/`**；历史 `src/` / `src_from_Figma/` 不作为当前开发入口，且不应在活仓根目录重建（Rules **E.7**）。

**顶栏（Header）** 须体现（具体排布与样式以 Figma 为准）：

- **软件版本**（如 `2026_v2.13` 形式）；
- **预算年份**；
- **预算版本号**（与 `version` 表主键或业务编号映射，以实现为准）；
- **预算版本名称**（与 `Version.version_name` 等一致）；
- **当前用户展示名与角色**（来自登录会话与用户表）。

**左侧导航树**（层级与文案以当前 `apps/web/src/app/workspaceCatalog.tsx` 为准）：

1. **预算管理** → 规则配置台（机构及产品；机构及产品指标）；预算数据输入（机构及产品数据录入；机构及产品预测输出）；系统配置中心（预算事实刷新跑批）；预算输出报表展示（预算展示报表）；模拟测算模块（模拟测算（正算）；模拟测算（倒算））；智能预算模拟。
2. **预算录入、部门费用预算管理模块** → 部门科目维护；部门预算科目维护；BI映射维护；费用执行明细导入；费用预测逻辑配置；部门费用预测；费用预算执行报表；业务支出成本收入比实际导入；业务支出成本收入比维护；投入产出专题概览。
3. **多维分析工具** → 当前可编辑年度多版本透视报表；多年度对比透视报表；多年度数据透视图；智能分析报告；智能演示PPT。
4. **系统配置中心** → 用户和权限管理；系统设定控制；数据同步管理；Agent对话测试。
5. **帮助与使用说明** → 使用说明；常见问题；联系管理员。

点击叶子节点在**中间工作区**打开对应 **Tab**（同模块多开策略以实现为准，默认与 Figma 行为一致）。

**中间工作区**：

- **多标签页**：可切换、可关闭；**超过 8 个标签**时出现溢出入口（如下拉「更多」），可将隐藏标签**切换到靠前位置**（与 Figma `WorkArea` 一致）。
- **无标签时**：显示欢迎区文案（如「欢迎使用银行财务预算管理系统」及引导语，以 Figma 为准）。
- 各模块内容区：**高密度表格**、树表、筛选器、工具栏、**Tab/方向键**导航（Rules **E.6**）等以各页 Figma 为准。

**右侧智能助手**（`ChatBot`）：

- 标题区：**智能助手**；**新对话**、**历史**（历史在顶栏与底栏快捷区可并存，以 Figma 为准）。
- 消息区：用户/助手气泡与时间。
- 输入区：**单行输入**与**展开多行**切换（如 Shift+Enter 换行、Enter 发送）；**发送**按钮。
- 底部快捷按钮（图标+提示）：**智能提问**、**上传文件**、**语音输入**、**电话交流**、**历史问题** 等 — **以 Figma 为准**。
- **§2.3** 规定安全与记忆；具体按钮是否接后端以分期实现为准，**布局与命名不改变 Figma 设计**。

**底部状态栏（StatusBar）**：

- 系统运行状态（如「系统就绪」）、**数据库连接状态**、**数据库最后全局计算并刷新时间**（与 **§2.2.2** 计算与预聚合任务一致）、待处理消息提示、在线状态、快捷设置入口等 — **字段与样式以 Figma 为准**。

**系统设定控制（内容范围）**：

- 系统设定控制在当前目标版本为实装页面，采用标签页方式承载：
  - **数据库文件维护**：维护 `var/data/` 目录下 `budget_{year}.db` 文件，展示年度库 `settings` 信息。
  - **数据库版本管理**：维护版本列表（含当前月份 `current_month`），支持新增/删除与继承。继承父版本时，按 `current_month` 仅迁移允许口径：`X` 月前迁实际、`X` 月及后迁预算；`X=1` 仅预算，`X=13` 仅实际。
  - **当前编辑版本与展示版本管理**：维护 `edit_show_version`，设置唯一编辑版本（`edit_show_sign=0`）与最多5个展示版本（`edit_show_sign=1..5`）。
- 该页面进入时需执行“文件系统与 `common.db.databases` 对齐检查”，发现增删变更需提示并同步。
- 密钥与凭据管理仍遵守 Rules **E.3**。

**Excel 导出**：

- 与在线计算**血缘一致**（Rules **E.6**，不一致为 P0）；**原则上**对公式与汇总结果导出**原生 Excel 公式**；**例外与边界**见 **§2.5**；技术见 **§3.2**。

### 2.2 核心业务与数据口径（对齐 Database PDD / Rules）

- **底层颗粒度**：`data_account`、机构及产品运行产品清单；`budget_data` **含** `product_code`（行级产品维），与「机构及产品」主表及公式重算上下文一致（Database PDD）。
- **树与绑定**：`data_account_metric_node`、`data_account_metric_binding`、`dept_account`、`org_product_tree_snapshot` 产品层级；删 `data_account` 前公式引用校验（Rules **E.6**）。
- **期间**：`period` 含 **`quarter`**（`Q1`–`Q4`），初始化静态填充（Database PDD）。
- **预算填报视图 vs 物理行**：**机构及产品数据录入**是唯一用户侧事实录入面；确认同步后通过当前数据科目绑定解析到 **`data_account_metric_binding`** 和 **`budget_data`** 业务键。**物理表 `budget_data`** 存储 **`data_acct_code`、`product_code`、`period_id`、`version_id`、`budget_actual`、`value`** 等，**不存报告树列**。
- **明细唯一性**：`budget_data` 联合唯一为 **`(data_acct_code, product_code, period_id, version_id, budget_actual)`**（Rules **E.1**）。**已删除**历史字段 **`data_type`**；**预算/实际**仅由 **`budget_actual`** 表达，并与 Figma「预算值/实际值」一致。
- **`DataAccount.value_type`（数值类型）**：与**机构产品指标运行引用**中的「数值类型」对应（金额/百分比/户数等），**不是**已废弃的 `budget_data.data_type`。
- **`budget_actual`**：与**机构及产品数据录入**同步到预算事实时的预算/实际口径对应：**`0`**=预算口径，**`1`**=实际口径。
- **`need_calc`**：引擎/后台标脏，**无 Figma 控件**；定时重算与「立即计算」消费该字段（Rules **E.1**）。
- **预算/实际月份窗口硬约束**：对任一版本，按 `current_month = X` 约束 `budget_data`：`X` 月前仅允许 `budget_actual=1`（实际），`X` 月及后仅允许 `budget_actual=0`（预算）；`X=1` 仅预算，`X=13` 仅实际。出现违规记录时，服务端需在版本创建继承与预算输入加载环节清理。
- **预聚合**：`budget_summary` 含 **`year`、`month`、`quarter`、`budget_actual`** 及展开列（**无** `data_type`）；大面查询读宽表（Rules **E.4**）。
- **`need_calc` 与重算（依赖传播）**：**字典或公式变更**后须走 `need_calc` 与重算链（Rules **E.1**）。任一 **`budget_data` 行**在**持久化**后若该版本内需参与引擎重算（含手工改值、导入、公式覆盖等），须将**该行** `need_calc` 置为需重算。**依赖链级联（MUST）**：在**同一 `version_id` 下**，凡因上述原因被标脏的行，**必须**按引擎可解析的**公式依赖图**（预算式、实际式及跨科目引用）**级联**将所有**直接或间接依赖**该行的 `budget_data` 行一并标为需重算，直至后台重算或「立即计算」完成并正确清零；**禁止**只标脏源行而遗漏下游公式行。依赖图解析边界（如跨版本、循环检测）以实现为准，且不得违背 Rules **E.1**。
- **精度**：存储与 **`DataAccount.value_type`**、舍入**仅在服务端**统一（Rules **E.1**）；**存储小数位数**以 **§2.2.1** 为准。**展示精度**由系统设置统一，**不得**反向污染存储值（Rules **E.1**）。
- **审计**：变更 `budget_data`、字典、映射、版本等须写入 **`common.db`** 的 **`operation_log`**（按 **`create_time`** 追加；**`action_desc` / JSON 快照**须可还原业务年度与 `version_id` 等），见 Database PDD **§1.9**；`target_table` 为物理表名（Rules **E.2**）。

#### 2.2.1 value_type 与存储小数位（Rules **E.1** 可查证锚点）

`DataAccount.value_type` 为枚举类展示名；**未在下表列出的取值**须在实现中定义小数位并纳入同一可查证配置，**新增或变更**时同步修订本表与 Rules **E.1** 审查。

| `value_type`（示例取值） | 存储小数位数 | 说明 |
|--------------------------|-------------|------|
| **金额** | **2** | 货币金额；写入 `budget_data` /引擎中间结果前按本表舍入。 |
| **百分比** | **4** | 比率类数值（内部以统一比例口径存储，如小数形式）；**界面「百分数」与存储的换算只在服务端做一次**，避免混用口径。 |
| **户数** | **0** | 户次、件数等非货币计数，存储为整数语义（无小数位）。 |

**舍入模式**：同一 `value_type` 内采用**四舍五入**或监管/财务规定的等价模式，须在服务端实现处单一实现、可审计；与上表不一致的特例**不得**静默生效，须先有文档与配置变更。

#### 2.2.2 计算与预聚合（摘要）

- **触发**：后台周期任务 + 用户显式触发。后台周期任务固定 **10 分钟**一轮，且仅在“至少 1 个有效登录会话”时执行；预算输入页采用「页面首次打开 / 页面离开 / 用户点击全局计算」触发刷新，**单元格逐次保存不触发即时全量公式重算**；完成后界面与库一致（Rules **E.4**）。
- **步骤**：更新 `budget_data` → 刷新 `budget_summary`；禁止用前端临时全表聚合替代宽表结论。
- **公式保存触发**：“机构及产品指标”在预算式/实际式保存成功后，须立即对对应唯一指标号码触发重算；每个产品使用自身产品前缀指标主键和上下文数据回写 `budget_data`。
- **公式引用约束**：公式引用仍使用 `data_acct_code` 作为稳定指针；保存与重算时必须校验引用科目与当前产品编码一致，计算读取限定在当前产品上下文。
- **跨年**：可多 `budget_{year}.db`；`period_id` 跨库有效性见 Database PDD「跨库逻辑引用」。
- **A/B 水位机制（MUST）**：
  - 年度库 `settings.global_refresh_time_a`（A）：该年度库“最近一次全局汇总刷新”时间；
  - Compare库 `settings.global_refresh_time_b`（B）：最近一次 compare 全量刷新完成时间；
  - 每轮后台任务先做公式重算，再判断 `MAX(budget_data.update_time)` 与 A；仅在数据晚于 A 时重建该年度 `budget_summary` 并更新 A；
  - 比较所有年度 A 与 B，若存在 `A > B`，则触发 compare 全量刷新并更新 B。
- **底栏时间展示口径（MUST）**：底栏“数据库最后全局计算并刷新时间”优先显示 B（compare 全局刷新时间），保证跨年度一致；B 不存在时回退到当前预算库 `budget_summary` 的最大 `update_time`。

### 2.3 智能体（Agent）与安全交互（对齐 Rules **E.3**）

#### 2.3.1 设计边界（宏观）

- Agent 采用 **LangGraph** 进行循环编排，支持**意图识别 → 口径判定 → 澄清追问 → 查询分析 → 用户反馈再迭代**的闭环交互。
- Agent 以预算系统底层数据库为分析基础，优先只读查询与解释；涉及写入或高风险动作时，遵循 Rules **E.3** 的确认与审计要求。
- Agent 对问题进行分流：**预算查询分析类**进入预算流程；**知识性/通用问答类**由大模型先直接回答，再附预算专长说明。
- Agent 同时具备**短期记忆**（本轮会话状态）与**长期记忆**（跨会话经验沉淀）的能力，但长期记忆不得覆盖 Rules 的强约束条款。
- Agent 输出包括：透视分析维度建议、查询结果解读、可视化联动（界面行为以 Figma 为准）；用户可通过“满意/不满意”反馈闭环持续优化。
- Agent 在体验上采用拟人化数字员工“管衡”形象；命名与话术原则在 Agent PDD 定义，System PDD 仅保留宏观能力约束。

#### 2.3.2 详细设计索引

- Agent 的状态机节点、状态字段、Prompt 分层、记忆模型、知识库目录、SQL 安全护栏、字段中文化映射、六按钮交互规格、评测方案与分期路线，统一见 [**Banking_Budget_Agent_PDD.md**](Banking_Budget_Agent_PDD.md)。

### 2.4 权限、用户与内网多用户范围（相对 Figma 的工程例外）

工程阶段划分与 **Rules「范围与演进」** 完全一致，摘要如下：

- **界面**：Figma 含 **「用户和权限管理」**、**「系统设定控制」** 等入口，导航与页面结构保持不变。
- **当前目标版本（内网多用户）**：实现登录、首次登录改密、会话隔离与权限控制，`operation_log.user_id` 与 `ip_address` 绑定真实访问主体。
- **角色与权限**：全权管理员拥有权限 1/2/3；数据录入用户拥有权限 1/2；数据浏览用户拥有权限 1。
- **后续增强版本**：在同一信息架构上扩展审批流和更细粒度权限，不得违背 Rules 字段语义与 **E.2** 可追溯要求；升级前须同步修订 **Rules「范围与演进」** 与本节。

### 2.5 Excel 智能导出与公式血缘（产品惯例）

细化 **Rules E.6** 的验收惯例：

- **总则**：由公式引擎、层级/时间汇总得到的单元格，在**技术上可行时优先**写入 **Excel 原生公式**；「应保留血缘」区域**禁止**仅写与在线无关的死数。在线结果与导出后 Excel **重算结果**须一致，**否则 P0**。
- **范围**：数据科目公式、报告/部门层级汇总、**年/季/月**汇总（与 `quarter` 口径一致）、同表基础区与衍生区混排时的公式链。
- **树形**：优先 **Group & Outline** 对齐在线折叠体验。
- **边界**：超大规模若需「部分公式 + 部分值」折中，须**文档化范围**并经产品认可，且不得削弱核心血缘（Rules **E.6**）。
- **导入模板目录规范（MUST）**：所有“需模板导入”的页面，其模板文件统一放在工作目录根下 **`resources/download_template/`**；前端“下载模板”按钮必须通过后端接口从该目录读取并下发，不得在前端硬编码模板内容。通用模板接口只接受当前注册的模板标识：`budget_data_temp`、`data_acct_temp`、`dept_acct_temp`、`pivot_export_temp`、`product_org_tree_import_template`；不得用完整文件名、目录扫描或历史别名下载未注册文件。
- **预算事实录入收口规范（MUST）**：预算/实际/预测事实只允许从**机构及产品数据录入**进入；旧预算实际录入页、旧 `/api/budget-input/*` 和旧预算 Excel 导入结果回写链路已删除，不得以兼容入口或隐藏页面恢复。

---

## 3. 技术路线与前端实现原则

### 3.1 前端（当前实现）

当前前端为 `apps/web/` 下的 **React + TypeScript + Vite** 应用，使用 Tailwind/CSS 变量、`react-resizable-panels`（可调整分栏）和 `lucide-react`（图标）等。可交付代码在 **`apps/web/src/`**（Rules **E.7**）。纯本地、无 CDN（Rules **E.5** SHOULD）。

### 3.2 后端（概括）

FastAPI（或同等）+ 异步 SQLite；表名/字段以 Database PDD 为准；预聚合写入 `budget_summary`；Excel 使用可写公式与分组库（如 `openpyxl` / `XlsxWriter`）满足 Rules **E.6**。

### 3.3 Agent 技术栈（概括）

LangGraph + Deepseek（兼容 OpenAI 协议）；密钥仅环境变量（Rules **E.3**）；分析只读优先，写库走固定接口。

---

## 4. Figma 界面元素与持久化映射（审阅用）

本节将当前界面构件与 **Database PDD** 表字段做**对照**，并附 **SQLite** 建表示意（与 PDD 一致；**权威正文仍以 Database PDD 为准**）。主数据**编码样式**以 Database PDD 为准，**勿沿用**历史导出或旧 mock 编号。各页映射与 SQL 阅毕后，**§4.8** 提供控件与字段的一行汇总，便于全文核对。

### 4.1 全局壳层

| UI / 代码 | 含义 | 主要库表 / 字段 |
|--------------|------|-----------------|
| 顶栏 **软件版本** | 应用发布版本号 | 实现配置或静态资源，**非** `version` 表 |
| 顶栏 **预算年份** | 当前打开的编报年度 | 决定加载 **`budget_{year}.db`**；与 `Period.year`（`Y2026`）对应关系见 Database PDD |
| 顶栏 **预算版本号 / 名称** | 当前编报版本 | **`version.version_id`**、**`version.version_name`**（年度库内） |
| 顶栏 **用户 / 角色** | 展示用 | 来自登录会话；审计见 **`operation_log.user_id`**（`common.db`） |
| 底栏 **最后全局计算时间** | 预聚合完成时刻 | 与 **`budget_summary.update_time`** / 任务水位一致，以实现为准 |
| 底栏 **最后全局计算时间（显示口径）** | 全局刷新状态 | 优先显示 **`compare.settings['global_refresh_time_b']`**；缺失时回退 `MAX(budget_summary.update_time)` |
| 左侧导航 | 模块 IA | 无单独表；各叶子对应各维护页所读写的字典或 `budget_*` |

### 4.2 机构产品指标运行引用（`data_account*`）

| 界面元素 | 持久化 |
|----------|--------|
| 唯一指标号码 / 名称 | **`data_account.data_acct_code`**、**`data_acct_name`**；号码由“机构及产品指标”按产品前缀指标主键同步生成，例如 `A05.01.01.001`；父节点派生号码同样使用父节点产品前缀指标主键，用户不在第二页面手工填写 |
| 指标树归属 | **`data_account_metric_node`**；配置主交互已经收拢到“机构及产品指标”，不再提供数据科目运行表独立页面 |
| 指标树汇总标识 | **`data_account_metric_node.horizontal_rollup`**、**`vertical_rollup`**、**`logic_code`**；横向按同逻辑码跨产品汇总，纵向按子节点汇总；旧 `metric_rollup_method` 已退休 |
| 产品编码 | **`data_account_metric_binding.scope_code`** → 机构及产品主表产品编码；旧 `product_type` 对象已删除 |
| 预算式 / 实际式 | **`budget_formula`**、**`actual_formula`** |
| 公式编辑器左侧科目树（防错） | 按当前科目产品编码过滤可引用科目；保存时后端重复校验，禁止绕过前端规则 |
| **数值类型**（金额/百分比/户数） | **`value_type`**（与 §2.2.1 小数位表对应） |
| 是否允许手工补录 | **`allow_manual_entry`**（`1`=允许，`0`=不允许；默认允许） |
| 备注 | **`remark`** |

**层级体验补充**

- `data_account*` 只保留为后端运行引用结构，同一产品指标主键下只保留一条同码运行记录，避免“指标树 + 产品树”双重嵌套造成冗余。
- 用户不直接手输第二套业务层级编码；系统根据“机构及产品指标”中维护的产品前缀指标主键同步生成类似 `A05.01.01.001` 的唯一指标号码，并自动继承上级路径；父节点汇总号码由系统按父节点产品前缀指标主键同步生成。
- 新增或调整指标身份时，用户进入“机构及产品指标”维护；系统同步生成唯一的 `data_acct_code`，并保证有效绑定不重复。
- 产品末级展示必须与机构及产品主表保持一致，产品名称、层级和编码通过运行产品清单读取。

### 4.2.1 预算输入与模拟测算对数据科目层级的使用

- 当前预算输入与模拟测算不维护独立的平面驱动分类体系；分类树来自 `data_account_metric_node`，可输入行来自 `data_account_metric_binding + data_account`。
- 数据科目是否允许人工维护预算值以 `allow_manual_entry` 为准；默认允许，需要锁定时在“机构及产品指标”维护对应运行口径。
- 实际数与预测数读取同一套 `budget_data` 明细，实际数使用 `budget_actual=1` 且前端只读、浅灰展示；预测预算数使用 `budget_actual=0` 且允许用户维护。
- 当用户修改某个产品下的底层输入科目后，重算结果应展示该产品相关的全部公式科目，便于校验底层输入对上层计算指标的影响。
- Excel 导入导出模板应包含唯一指标号码、数据科目名称、产品编码、产品名称、数值类型与月度值，导入时优先按唯一指标号码定位；源 Excel 指标编码仅作为导入追溯信息，不作为主数据号码。

### 4.3 报告 / 部门 / 机构及产品

| 界面 | 主表 |
|------|------|
| 部门科目树 | **`dept_account`** |
| 机构及产品 | **`org_product_tree_snapshot`**；旧 `product_type` 对象已删除 |

> **部门与产品解耦口径**
> `dept_account` 只维护事业群与费用归属部门两级部门科目；费用发生部门保留在费用整体框架快照表中；产品层级只从“机构及产品”维护，`product_type` 不再是物理维护表。系统不得再依赖全局“部门 → 产品”映射推断产品归属。

> **强制一致性要求（主数据维护界面）**
> 机构及产品、机构及产品指标、部门科目维护、部门预算科目维护和 BI 映射等当前工作界面的展示数据必须来自上述数据库表或运行视图的实时查询结果；数据科目仅作为后端运行链路和只读导出来源，不得恢复为独立维护界面；
> 当底层表为空时，界面必须显示空状态，不得回退到前端内置样例数据（mock/demo）；
> 界面新增/编辑/删除/映射操作必须通过后端 API 持久化并在刷新后可复现，确保 UI 与底层库的一致性（读写同源、刷新不漂移）。

### 4.4 机构及产品数据录入（`OrgProductDataEntryContent`）

| 界面元素 | 持久化说明 |
|----------|------------|
| 预算 / 实际 / 预测事实 | 用户只在机构及产品指标体系内维护；确认同步后由 `BudgetDataWriter` 写入 `budget_data` |
| 机构/产品与指标选择 | 通过机构及产品指标体系定位已确认单元格，并解析到已绑定的 `data_acct_code` 与 `product_code` |
| 指标层级 / 数据科目列 | 数据科目编码和名称直接采用机构及产品指标体系；不保留第二套指标语义 |
| 1–12 月列 | 对应 **`period_id`**（`common.db` **`period`**），同步后每月一行 **`budget_data`**（同 `data_acct_code`、`product_code`、`version_id`、`budget_actual`） |
| **全局计算并刷新** | 引擎重算 +刷新 **`budget_summary`**；更新 **`need_calc`** |

### 4.5 多维分析与图表

| 界面 | 数据源 |
|------|--------|
| 数据透视表-当前年度多版本透视 | 读当前编辑年度库 **`budget_summary`** |
| 数据透视表-多年度对比透视 | 读 **`compare.db.compare_budget_summary`** |
| 多年度数据透视图 | 以上两类透视结果的可视化消费（按页面上下文选源） |

### 4.6 审计日志

所有 **Rules E.2** 覆盖的写路径 → 插入 **`common.db`** **`operation_log`**；**`target_table`** 为 snake_case 表名；快照中须含**业务年度**与 **`version_id`**（若适用）。

### 4.7 SQL 建表示意（SQLite）

以下为**节选**，列名与类型与 Database PDD 对齐，便于审阅；迁移时以 PDD 全文为准。

**`common.db`**

```sql
CREATE TABLE org_product_tree_snapshot (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 运行产品清单由服务从 org_product_tree_snapshot 展开；
-- 递归 JSON 展开 SQL 由 apps/api/app/services/org_product_runtime_catalog.py 统一生成。
-- 旧产品科目维护物理表、CRUD API、导入模板和页面均不得恢复。

CREATE TABLE data_account (
  data_acct_code TEXT PRIMARY KEY NOT NULL,
  data_acct_name TEXT NOT NULL,
  budget_formula TEXT,
  actual_formula TEXT,
  budget_rule_code TEXT,
  budget_rule_config_json TEXT,
  need_calc INTEGER NOT NULL DEFAULT 0,
  formula_calc_mode INTEGER NOT NULL DEFAULT 0,
  allow_manual_entry INTEGER NOT NULL DEFAULT 1,
  value_type TEXT NOT NULL,
  remark TEXT
);

CREATE TABLE data_account_metric_node (
  node_code TEXT PRIMARY KEY NOT NULL,
  node_name TEXT NOT NULL,
  parent_code TEXT,
  product_code TEXT,
  local_metric_code TEXT,
  logic_code TEXT,
  functional_group_code TEXT,
  level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 8),
  node_type TEXT NOT NULL CHECK (node_type IN ('CATEGORY', 'GROUP', 'METRIC')),
  horizontal_rollup INTEGER NOT NULL DEFAULT 0 CHECK (horizontal_rollup IN (0, 1)),
  vertical_rollup INTEGER NOT NULL DEFAULT 0 CHECK (vertical_rollup IN (0, 1)),
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  remark TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE data_account_metric_binding (
  data_acct_code TEXT PRIMARY KEY NOT NULL REFERENCES data_account(data_acct_code),
  metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
  scope_code TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  remark TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (metric_node_code, scope_code),
  CHECK (data_acct_code = metric_node_code),
  CHECK (scope_code = SUBSTR(metric_node_code, 1, INSTR(metric_node_code, '.') - 1)),
  CHECK (
    (scope_type = 'CORP' AND scope_code = 'CORP')
    OR (scope_type = 'PRODUCT' AND scope_code <> 'CORP')
  )
);

CREATE TABLE period (
  period_id INTEGER PRIMARY KEY AUTOINCREMENT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  year_month TEXT NOT NULL UNIQUE,
  days INTEGER NOT NULL
);

CREATE TABLE operation_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  action_type TEXT NOT NULL,
  action_desc TEXT NOT NULL,
  target_table TEXT,
  affected_rows INTEGER,
  before_data TEXT,
  after_data TEXT,
  ip_address TEXT,
  create_time TEXT
);
-- 其余字典表见 Database PDD §1
```

**`budget_{year}.db`（示例年度库）**

```sql
CREATE TABLE version (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_date_time TEXT NOT NULL,
  version_name TEXT NOT NULL,
  current_month INTEGER NOT NULL
);

CREATE TABLE budget_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_acct_code TEXT NOT NULL,
  product_code TEXT NOT NULL,
  period_id INTEGER NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  value REAL NOT NULL DEFAULT 0,
  need_calc INTEGER NOT NULL DEFAULT 1,
  manual_value REAL,
  formula_value REAL,
  value_source TEXT NOT NULL DEFAULT 'manual'
    CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
  create_time TEXT,
  update_time TEXT,
  UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
);

CREATE TABLE budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_level1 TEXT, metric_level2 TEXT, metric_level3 TEXT, metric_level4 TEXT, metric_level5 TEXT,
  dept_level1 TEXT, dept_level2 TEXT, dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL, month TEXT NOT NULL, quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL,
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  version_name TEXT,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  update_time TEXT
);
-- 宽表其余约定见 Database PDD §2.4
```

**跨库引用**：`budget_data` 对 `data_account`、`period` 和机构及产品主表产品编码（经 `product_code`）为**逻辑引用**（应用层或 `ATTACH`），见 Database PDD「跨库逻辑引用与 SQLite 限制」。

**`compare.db`（多年度对比透视只读库）**

```sql
CREATE TABLE compare_budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  show_level INTEGER NOT NULL,
  data_file_id INTEGER NOT NULL,
  source_year INTEGER NOT NULL,
  source_version_id INTEGER NOT NULL,
  source_version_name TEXT,
  metric_level1 TEXT, metric_level2 TEXT, metric_level3 TEXT, metric_level4 TEXT, metric_level5 TEXT,
  dept_level1 TEXT, dept_level2 TEXT, dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL, month TEXT NOT NULL, quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  sync_time TEXT NOT NULL
);
```

### 4.8 界面控件与持久化字段速查（汇总）

| 用户可见控件 / 概念 | 数据库位置 | 备注 |
|---------------------|------------|------|
| **机构产品指标运行引用** — **数值类型** | `data_account.value_type` | 与 **§2.2.1** 小数位表联动；**无** `budget_data` 侧「数据类型」列 |
| **机构及产品数据录入** — **预算 / 实际口径** | `budget_data.budget_actual`（预聚合行见 `budget_summary.budget_actual`） | **`0`** = 预算口径，**`1`** = 实际口径 |
| （无直接控件） | `budget_data.need_calc` | 引擎/任务标脏，见 **§2.2**；**不**出现在 Figma 表单列中 |
