# 银行预算管理系统 — 变更日志 (CHANGELOG)

> 本文档由 AI Release Manager 自动维护。  
> 格式规范见 `.claude/skills/merge-release/SKILL.md` 阶段四。

---

## v2.24-fix (2026-06-09) — 费用统计表三列源表对齐与跨表自检预警

- 修复: 费用预算执行报表「费用统计表」的“本年实际/上年同期”源表汇总不再只取最近批次，改为读取当前 `expense_actual_detail_raw` 中所有有效匹配行；覆盖导入已按期间清理旧行，因此当前源表全量行就是报表源口径。
- 修复: 本年实际和上年同期均按匹配状态过滤，owner 明细口径要求 `owner_matched=1` 且 `subject_matched=1`，科目汇总口径要求 `subject_matched=1`，避免未匹配源表行进入报表汇总。
- 修复: 费用统计表在主体/事业群/费用归属部门筛选下，改用 owner+科目明细聚合当前实际和上年同期，不再把全行科目汇总误带入局部筛选。
- 新增: 月报格式响应新增 `consistency_warnings`，自动比较费用统计表、业务费用表、IT费用表、日常费用表中的同类指标；字段覆盖本年实际、本年预算、预算进度、同比、环比、去年同期等核心数值列。
- 新增: 费用预算执行报表页面展示跨表一致性预警，标注不一致指标、字段、涉及报表和值差异。

### 验证
- `.venv/bin/python -m pytest apps/api/test_expense_budget_execution_budget_source.py apps/api/test_expense_budget_execution_report_resolver.py -q` 通过，59 个测试覆盖全量源表行、匹配过滤、范围筛选和跨表预警。
- `PYTHONPATH=apps/api .venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases(); import app.main"` 通过。
- `npm --workspace apps/web exec tsc -- --noEmit` 通过。
- `cd apps/web && npm run build` 通过，仅保留既有 Vite chunk size warning。

## v2.23-merge (2026-06-09) — shier0603本年预算匹配口径融入执行报表

- 修改: 部门费用预算管理模块「费用预算执行报表」的“本年预算”列改为读取 `common.db.expense_budget_entry` 已匹配预算录入数据，不再从年度库 `budget_summary` 反推部门预算。
- 匹配: 仅纳入 `budget_year` 等于当前年度、`owner_matched=1`、`subject_matched=1`，且费用归属部门和预算科目可被当前框架上下文规范化的行；未匹配部门或未匹配科目的行不进入部门报表本年预算列。
- 金额: 本年预算使用 `amount + adjustment_amount` 的调整后金额，内部单位为元，再从费用归属部门聚合到事业群和主体。
- 说明: 报表响应在存在预算录入来源时追加预算来源说明，明确“费用归属部门匹配预算录入部门、预算科目匹配预算录入科目、仅纳入双匹配数据”。

### 验证
- `.venv/bin/python -m pytest apps/api/test_expense_budget_execution_budget_source.py -q` 通过，7 个测试覆盖双匹配排除、调整后金额和全行科目汇总边界。
- `.venv/bin/python -m pytest apps/api/test_expense_budget_execution_report_resolver.py -q` 通过，50 个报表 resolver 测试确认既有报表结构和文案兼容。
- `PYTHONPATH=apps/api .venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"` 通过。
- `PYTHONPATH=apps/api .venv/bin/python -c "import app.main"` 通过，确认预算录入和预算执行报表路由均可注册。

## v2.22-merge (2026-06-09) — shier0603部门费用预算录入模块合入

- 新增: 部门费用预算管理模块下恢复 shier 0603 的「预算录入」入口，挂载 `ExpenseBudgetEntryContent`，独立于“费用执行明细导入”。
- 新增: `/api/expense-budget-entry/*` 后端接口，支持预算录入模板下载、Excel 上传预览、匹配结果导出、确认导入、批次列表/删除、已导入预算金额和预算调整金额维护。
- 数据: `common.db` 新增并启动时确保 `expense_budget_entry_batch`、`expense_budget_entry`，预算录入上下文复用当前部门科目、部门预算科目、BI-AI 映射，并补读费用框架快照中的预算部门/产品部门/预算科目用于初始化匹配。
- 边界: 不恢复费用执行明细导入里的“本年预算导入”切换项；`current_year_budget` 仍被费用执行明细导入白名单拒绝，避免和预算录入模块混用。

### 验证
- `PYTHONPATH=apps/api .venv/bin/python -m compileall ...` 通过。
- `PYTHONPATH=apps/api .venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"` 通过，并确认两张预算录入表存在。
- `PYTHONPATH=apps/api .venv/bin/python -c "import app.main"` 通过，确认 8 个 `/api/expense-budget-entry/*` 路由注册。
- `npm run build` 通过，仅保留既有 Vite chunk size warning。
- 登录后实测 `/api/expense-budget-entry/batches`、`/api/expense-budget-entry/rows` 返回正常，`/api/expense-budget-entry/template` 返回 Excel 文件。
- 自检 Excel 解析通过：真实部门和预算科目可匹配，金额单位 `ten_thousand` 正确换算。
- 费用执行明细导入回归测试通过：`apps/api/test_expense_actual_import_batches.py`、`apps/api/test_expense_actual_import_router.py`、`apps/api/test_expense_actual_import_apply.py` 共 8 个测试通过。

## v2.21-merge (2026-06-05) — bin机构及产品指标树体系合并

- 修改: 机构及产品指标体系确认为唯一主指标体系和唯一指标配置入口；数据科目表不再保留第二套编码语义，也不再作为投影层绕行，编码和名称直接采用机构及产品指标体系。
- 数据: 已按机构及产品指标体系直接重建 `data_account_metric_node`、`data_account`、`data_account_metric_binding`；当前 `data_account_metric_node=1687`、`data_account=1252`、`data_account_metric_binding=1252`，其中机构产品主体系 `1485` 个节点，潘潘 99 保护区 `202` 个节点。
- 数据: `AA.01.01.01` 在数据科目表中已确认为 `利息收入`，与机构及产品指标表一致；潘潘旧 05 费用类统一保留在第二段 `99`，例如 `AA.99.01.01=常规人力`。
- 新增: `apps/api/scripts/rebuild_data_accounts_from_org_product_metrics.py`，用于从机构及产品指标表直接重建数据科目表；执行前自动备份，最近备份为 `var/backups/common_before_direct_org_product_data_account_rebuild_20260605_232138.db`。
- 新增: `apps/api/scripts/fix_org_product_metric_source_conflicts.py`，已把机构及产品指标表内 9 个冲突编码改为唯一编码，包括 `AA.01.01.02=利息支出`、`AA.46.01.02=利息支出`、`A02.19.02=数字人民FTP成本`，以及把 A02 主体系参数从 `99` 改到 `98`，避免占用潘潘 99 保护区；当前源体系同码冲突 `0`。
- 新增: 直接重构冲突底稿 `var/output/data_account_direct_rebuild_conflicts_20260606_001427.xlsx`，本轮冲突行 `0`，父级缺失 `0`。
- 新增: `apps/api/scripts/rebind_budget_output_display_to_data_accounts.py`，已按新数据科目体系回挂预算展示配置 `508` 条；剩余未回挂项已输出到底稿 `var/output/budget_display_rebind_20260606_001735.xlsx`，主要为旧展示层级、GROUP 行或同名多义项。
- 修改: 数据科目页恢复为 `数据科目维护`，页面说明改为“数据科目编码和名称直接采用机构及产品指标体系；除潘潘99保护区外，同一编码必须表达同一业务含义”。
- 修改: 数据科目页的 `Excel上传科目`、`新增数据科目`、左侧 `新增指标节点` 和删除动作仍收口到“机构及产品指标”唯一入口；后端 `/api/data-accounts` 新增、`/api/data-account-metric-nodes` 新增、`/api/data-accounts/import-apply` 和 `/api/data-accounts/{code}` 删除直写入口返回 409。
- 修改: 预算事实录入入口彻底收拢为“机构及产品数据录入”；旧“预算实际/预算数据录入”页面、`/api/budget-input/*`、Excel 导入链路和 `BudgetInput*` DTO 已物理删除。`budget_data` 和 `BudgetDataWriter` 继续作为唯一事实表与写入服务；“预算/实际数据跑批”仅保留计算刷新能力。
- 数据: 直接重构后清空断链旧数据科目引用并按新体系回挂可确定项；当前预算展示配置无断链引用，`PRAGMA foreign_key_check=0`。
- 修改: `AA/aa` 明确为微众银行实体；“全行”作为汇总/矩阵视角处理，不等同于 AA。

### 变更来源
- 团队提交包: `TeamSubmit_20260604_org_product_metrics.zip`
- Codex: 将包内“机构及产品”指标树体系作为独立新增模块合入当前 `apps/` 主线；不整包覆盖旧 `backend/`、旧 `src/`、旧 `Design docs/`，不替换当前数据科目维护和产品前缀标准指标树。

### 变更明细
- 新增: 基础数据维护下“机构及产品”和“机构及产品指标”入口，支持机构/产品树维护、指标表维护、公式配置、Excel 导入导出。
- 新增: 预算数据输入下“机构及产品数据录入”和“机构及产品预测输出”入口，支持滚动预测录入、版本草稿/提交、预测输出运行与导出。
- 新增: 后端 `org_product_metrics` 路由，注册 `/api/org-product-tree/*`、`/api/org-product-metrics/*`、`/api/org-product-data-entry/*`、`/api/org-product-output/*`。
- 新增: Excel 原生公式到系统公式文本转换模块 `org_product_excel_formula.py`，支持同表、跨表、跨机构引用转换。
- 修改: `ensure_databases()` 启动链路补齐 `org_product_*` 私有表幂等初始化。
- 修改: 费用预测逻辑配置的指标表达式变量接入 `org_product_metric_table` 已确认映射；页面选择已确认机构产品指标时改为提交 `org_product_metric`、机构产品指标编码和 `org_product_ref`，保存/试算/重算前由后端解析为 `metric_tree/data_acct_code/source_subkey` 参与当前预测规则计算，规则读模型返回只读 `org_product_refs` 展示来源表。
- 修改: 费用预测逻辑配置模板下载增加 `机构产品指标候选` sheet，从现场 `org_product_metric_table` 读取已确认且非 05 保护的候选，并生成可复制到 `变量映射JSON` 的示例。
- 修改: 费用预测规则导入预览/应用支持 `source_type=org_product_metric` 或 `org_product_ref` 变量写法，保存前自动解析为 `metric_tree` 变量；05 保护或不存在的机构产品引用会作为导入错误拦截。
- 修改: 费用预测规则 API 保存和试算入口也支持 `org_product_metric` 变量写法，进入保存、重算或试算前统一解析为当前 `metric_tree` 计算合同。
- 新增: 机构及产品数据录入版本确认后支持显式“同步预算事实”；仅将 `MANUAL_CONFIRMED`、非 05、已绑定 `data_acct_code` 的月度实际/预测单元格通过 BudgetDataWriter 写入年度库 `budget_data`，未确认、未绑定、05 保护和月份窗口外单元格只计入跳过；写入成功后同步重建 `budget_summary` 和 `budget_pivot_aggregate`，让预算展示和透视表读取到机构产品录入结果。
- 修改: 预算展示配置从机构产品指标候选创建展示行时，持久化 `org_product_ref`、机构/产品编码、指标表名、机构产品指标编码和名称；预算展示取数仍使用底层 `data_acct_code`，删除或解绑数据科目时同步清空 `org_product_*` 来源字段，避免残留断开的机构产品身份。
- 修改: 预算展示报表 API、页面主指标列和完整报表 Excel 导出透传展示配置行保存的 `org_product_*` 身份；导出 `机构产品来源` 优先使用配置行来源，未保存来源时才回退到按 `data_acct_code` 反查全部已确认机构产品引用。
- 修改: 权限策略补齐机构及产品维护/录入/输出接口权限，其中维护类写操作为管理员，录入和输出运行为录入权限，只读快照为浏览权限。
- 新增: `docs/product/OrgProduct_*.md` 专题文档，保留 bin 包对单机构指标表、月内公式、滚动预测和矩阵输出的术语与设计边界。

### 差异甄别边界
- 已合入: `org_product_metrics.py`、`org_product_excel_formula.py`、四个 OrgProduct 前端页面、三个前端共享 helper、OrgProduct 专题文档。
- 未合入: 包内旧 `backend/` 和旧 `src/` 的整包应用壳、旧数据科目页面、旧预算输入、旧费用、旧 Agent、旧配置文件和乱码 Excel 附件。
- 未合入: 包内旧 PDD 对 `report_account`、旧多层指标树和旧工作台的历史口径；当前主线仍以 `data_account`、`data_account_metric_node`、`data_account_metric_binding` 和 BudgetDataWriter 为预算事实主线。

### 数据库影响
- `common.db` 新增并初始化以下私有表: `org_product_tree_snapshot`、`org_product_metric_table`、`org_product_metric_table_catalog`、`org_product_data_entry_snapshot`、`org_product_data_entry_snapshot_v2`、`org_product_data_entry_draft`、`org_product_output_snapshot_v1`。
- 当前现场表计数: 指标表目录 `org_product_metric_table_catalog=9`，其余快照/录入/输出表暂为空。
- 不修改 `data_account`、`data_account_metric_node`、`data_account_metric_binding`、`budget_data` 主键或当前预算写入链路。

### 验证
- `PYTHONPATH=apps/api ./.venv/bin/python -m py_compile ...` 通过。
- `PYTHONPATH=apps/api ./.venv/bin/python -m pytest apps/api/test_org_product_excel_formula.py -q` 通过，3 个测试通过。
- `PYTHONPATH=apps/api .venv/bin/python -m unittest apps/api/test_expense_forecast_rule_read_model.py apps/api/test_expense_forecast_rule_router.py` 通过，19 个测试通过。
- `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/test_expense_forecast_rule_import_workflow.py apps/api/test_expense_forecast_rule_import.py apps/api/test_expense_forecast_rule_router.py -q` 通过，24 个测试通过。
- `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/test_expense_forecast_rule_import_workflow.py apps/api/test_expense_forecast_rule_import.py apps/api/test_expense_forecast_rule_router.py apps/api/test_expense_forecast_rule_save.py apps/api/test_expense_forecast_rule_simulation.py -q` 通过，32 个测试通过。
- `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/test_org_product_budget_sync.py -q` 通过，3 个测试通过，确认机构产品录入同步只写已确认非 05 映射行、复用 BudgetDataWriter 写入 `budget_data`，且写入成功后刷新预算汇总和透视聚合。
- `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/test_budget_output_display_config.py apps/api/test_data_account_commands.py apps/api/test_db_bootstrap_schemas.py::DbBootstrapSchemaTests::test_common_schema_creates_budget_output_display_item apps/api/test_db_bootstrap_schemas.py::DbBootstrapSchemaTests::test_report_display_sync_bootstrap_creates_only_current_table -q` 通过，14 个测试通过，确认预算展示配置保存机构产品追溯身份、解绑时清空来源字段、schema bootstrap 创建新列。
- `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/test_budget_output_export.py -q` 通过，确认预算展示 Excel 优先导出配置行保存的机构产品来源，再回退按数据科目反查来源。
- `npx tsc -p apps/web/tsconfig.json --noEmit` 通过，确认预算展示配置前端 payload 和 DTO 类型可编译。
- 真实 `common.db` 规则模板候选 sheet 抽样通过：`ref_data_acct_codes=242`、`candidate_rows=355`，首条候选可生成 `org_product_metric` 变量映射 JSON。
- 真实 `common.db` 机构产品变量解析抽样通过：`A01:业务状况表:A0111` 可解析为 `source_type=metric_tree`、`source_key=A01.01.01.01.01.017`、`source_subkey=A01`。
- `PYTHONPATH=apps/api ./.venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"` 通过，并创建 `org_product_*` 私有表。
- `PYTHONPATH=apps/api ./.venv/bin/python -c "import app.main"` 通过，确认 37 个 `org-product` 相关路由注册，包含预算事实同步预览/应用端点。
- `npm --workspace apps/web exec tsc -- --noEmit` 通过。
- `cd apps/web && npm run build` 通过，仅保留既有 Vite chunk size warning。

## v2.20-merge (2026-06-04) — 潘潘0602数据科目与投入产出表精准合并

### 变更来源
- 团队提交包: `TeamSubmit_20260602_panpan_budget_system`
- Codex: 盘点提交包与当前主线 185 个差异后，只合入数据科目来源表和投入产出/成本收入比实质功能；不整包覆盖当前主线，不回退当前已完成的数据科目维护重构、费用执行、BI 映射、Agent 和系统配置代码。

### 变更明细
- 新增: `resources/business_inputs/科目和层级表.xlsx` 作为潘潘0602数据科目和层级来源材料；该文件用于业务核对和后续导入来源追溯，不替代当前 `data_account` / `data_account_metric_node` 运行库权威。
- 修改: `business_cost_income_item` 扩展为产品模板维度，补齐 `product_code`、`display_group`、`data_acct_code`、`manual_entry_mode`、`value_mode` 等字段，投入/产出明细可按产品维护，并可绑定当前数据科目唯一指标号码。
- 修改: `business_cost_income_indicator` 扩展为产品维度指标树，补齐父级、显示分组、专题指标节点、分子/分母取值模式、年化和 `number` 格式支持。
- 新增: `business_cost_income_source_mapping` 来源映射表，用于把成本收入比明细和指标映射到当前数据科目口径。
- 修改: 成本收入比 bootstrap 支持旧 18 行配置平滑升级到产品模板；仅当年度库没有产品模板且 `business_cost_income_value` 无业务值时才重播模板，避免覆盖已有人工值。
- 修改: 启动初始化通过当前 `common.db` 连接准备成本收入比 schema，确保 `data_acct_code` 绑定能解析当前数据科目主数据。
- 修改: 成本收入比后台维护页增加产品模板选择器，维护操作按产品加载/创建/启停/保存，并保留潘潘包新增的手工录入模式和取值模式字段。
- 修改: 成本收入比导入服务只允许导入手工维护明细，专题概览服务和页面沿用当前主线独立 `input_output_topic_overview` 路由，不恢复来源包旧路由拼接方式。

### 差异甄别边界
- 已合入: `db_bootstrap/business_cost_income.py`、成本收入比相关 service、投入产出专题 overview service/API/UI、成本收入比后台维护 UI、数据科目和层级来源 workbook。
- 未合入: 提交包中 `data_accounts.py`、`DataAccountContent.tsx`、`data_account_usage.py` 等旧式数据科目页面/路由改动；当前主线已经完成数据科目模块拆分和产品前缀指标树重构，来源包差异主要是结构回退风险。
- 未合入: 提交包中与本次需求无关或当前主线已有更新版本的预算输入、费用执行、BI 映射、Agent、系统配置、旧整包目录和发布脚本差异。

### 数据库影响
- 年度库 `budget_2025.db`、`budget_2026.db` 已通过幂等初始化从旧空值配置升级：`business_cost_income_item=554`、`business_cost_income_indicator=260`、`business_cost_income_source_mapping=108`、`business_cost_income_value=0`。
- 不创建来源包旧 `bcir_*` 第二套模型表；投入产出表继续使用当前主线 `business_cost_income_*` 私有表。
- 不修改 `data_account`、`data_account_metric_node`、`data_account_metric_binding` 主键和当前数据科目写入链路。

### 验证
- `PYTHONPATH=apps/api ./.venv/bin/python -m compileall apps/api/app` 通过。
- `PYTHONPATH=apps/api ./.venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"` 通过，并完成产品模板升级。
- `PYTHONPATH=apps/api ./.venv/bin/python -m pytest apps/api/test_input_output_topic_overview_router.py apps/api/test_business_cost_income_ratio_router.py apps/api/test_business_cost_income_ratio_service.py -q` 通过，10 个测试通过。
- `PYTHONPATH=apps/api ./.venv/bin/python -c "import app.main"` 通过，确认 `business-cost-income-ratio` 与 `input-output-topic-overview` 路由注册。
- `cd apps/web && npm run build` 通过，仅保留既有 Vite chunk size warning。

## v2.19-merge (2026-06-02) — TeamSubmit_20260529 费用执行明细与 BI-AI 映射外科式合并

### 变更来源
- 团队提交包: `TeamSubmit_20260529_shier_expense_budget(1)`
- Codex: 只合入部门费用侧功能增量，不整包覆盖当前主线；继续保留当前数据科目体系、部门科目体系、费用预测 `METRIC_EXPR` 规则合同和 8443/8009 测试服务器口径。

### 变更明细
- 新增: BI映射维护中的 `BI-AI科目映射表` 页签，以及 `/api/bi-ai-subject-mapping/list`、`/api/bi-ai-subject-mapping/reload` 后端接口。
- 修改: 费用执行明细导入支持 `本年实际导入 / 本年预算导入 / 上年实际导入` 三类 `import_kind`，批次列表、覆盖写入、导出和删除按导入类别隔离。
- 修改: 费用执行明细导入和导出补齐费用大类、费用类别、预算发布口径、归口管理部门2和专项管控打标字段。
- 修改: 费用预算执行报表本年实际只读取 `current_year_actual`，去年同期优先读取 `prior_year_actual` 导入明细，无导入时回退上一年度库实际数据。
- 修改: 费用类型树对业务要求固定展示的 `超额奖金` 执行零值保留，不改变其他全零科目的默认隐藏规则。
- 文档: 已补齐 System PDD、Database PDD、文件地图、团队合并说明和数据库影响确认 Excel。

### 数据库影响
- 中风险待确认: 本轮代码涉及新增 `bi_ai_subject_mapping` 私有映射表，并向 `expense_actual_import_batch`、`expense_actual_detail_raw` 补充导入类别和匹配结果字段。
- 不修改既有主键，不修改既有唯一约束，不重建 `dept_account`，不调整部门预算科目树主键。
- 已生成确认表: `docs/product/team_contributions/TeamSubmit_20260529_shier_expense_budget_db_impact.xlsx`。
- 注意: 业务已补充 `BI科目匹配表.xlsx`，当前已落库为 68 条 `bi_ai_subject_mapping` 配置；Excel 仅作为重建来源，运行时读取数据库配置。
- 用户已确认数据库影响表后执行 scoped 落库；落库前备份 `var/data/common.db` 到 `var/backups/common_before_team_submit_20260529_expense_schema_20260602_112224.db`。
- 当前现场 `var/data/common.db` 已创建 `bi_ai_subject_mapping` 并补齐费用执行导入字段；最新本年实际导入 342 行全部补齐费用大类、费用类别和预算发布口径。

### 验证
- `.venv/bin/python -m compileall -q apps/api/app` 通过。
- `PYTHONPATH=apps/api .venv/bin/python` 导入 `app.main` 通过，确认 `/api/bi-ai-subject-mapping/list`、`/api/bi-ai-subject-mapping/reload`、`/api/expense-actual-import/export`、`/api/expense-actual-import/batches/{batch_id}` 已注册。
- `npm run build` 通过，仅保留既有 Vite chunk size warning。
- `npm --workspace apps/web exec tsc -- --noEmit` 通过。
- 完整费用执行导入/BI-AI 路由清单检查通过，覆盖 list/reload/batches/export/delete/import-preview/import-apply。
- 查库确认当前 `common.db` 已存在 `bi_ai_subject_mapping`、`expense_actual_import_batch.import_kind` 和费用执行导入新增字段；`BI-AI科目映射表` 接口返回 68 行。
- 在 `var/output/merge_validation/common_team_submit_20260529_schema_check.db` 副本上执行 `ensure_expense_actual_import_schema_sync` 通过：新增表、补字段和唯一索引均创建成功，`PRAGMA foreign_key_check` 返回空。
- 使用提交包内 `resources/business_inputs/部门费用执行.xls` 在临时数据目录验证费用执行导入预览/写入：预览 342 行、期间为 2026-01 至 2026-04，owner 与预算科目匹配均为 342 行，临时库 `prior_year_actual` 写入 342 行；现场库仍未变化。
- 业务边界: 提交包内 `部门费用执行.xls` 只有 16 列，不含 R 列归口管理部门2，因此明细备注仍可提示“归口管理部门2未匹配”；未匹配行统计只按费用归属部门/预算科目是否匹配计算。
- Excel 源文件核查: 业务已提供 `BI科目匹配表.xlsx`，并落位到 `resources/business_inputs/BI科目匹配表.xlsx`；`科目和层级表.xlsx` 与 `费用整体框架.xlsx` 均不是该映射源。
- 新增脚本 `apps/api/scripts/validate_team_submit_20260529_expense_merge.py`，默认只在副本库 dry-run；用户确认数据库影响表后可用 `--apply` 备份并落库。
- `python apps/api/scripts/validate_team_submit_20260529_expense_merge.py` 默认 dry-run 通过，确认副本 schema 成功。
- `PYTHONPATH=apps/api .venv/bin/python apps/api/scripts/validate_team_submit_20260529_expense_merge.py --apply` 已执行成功：现场库存在 `bi_ai_subject_mapping`，批次表存在 `import_kind`，明细表存在 10 个新增字段，`PRAGMA foreign_key_check` 返回空。
- 查库确认最新费用执行导入批次归入 `current_year_actual`，当前有效明细 342 条，`budget_release_caliber_mapped` 非空 342 条；费用预算执行报表月报格式接口返回业务费用 48 行、IT费用 16 行，并按 TeamSubmit 口径展示 `日常外包服务费` 与 `部门内部会议费`。
- 费用相关 pytest 未执行：当前 `.venv` 未安装 `pytest`，未临时安装依赖以避免扰动环境。

## v2.18-merge (2026-06-01) — 潘潘成本收入比与投入产出专题包外科式合并

### 变更来源
- 潘潘团队提交包: `archive/team_packages/incoming/20260601/TeamSubmit_20260601_panpan_expense_budget/`
- Codex: 仅合入成本收入比实际导入、投入产出专题概览等功能增量；来源包中的 `bcir_*` 正式模型表与旧导航/旧 WorkArea 不进入当前主线。

### 变更明细
- 新增: `业务支出成本收入比实际导入` 页面，挂载在“部门费用预算管理模块”下，支持按产品和月份下载模板、上传预览、确认写入。
- 新增: `投入产出专题概览` 页面，挂载在“部门费用预算管理模块”下，支持主体、费用月份、产品群、产品范围、金额单位、全行总表/分产品明细切换和 Excel 导出。
- 新增: `apps/api/app/services/business_cost_income_import.py`，导入模板和预览/写入只使用当前年度库 `business_cost_income_value`。
- 新增: `apps/api/app/services/input_output_topic_overview.py`，专题总览只读取当前 `business_cost_income_item`、`business_cost_income_indicator`、`business_cost_income_value` 三表。
- 修改: `business_cost_income` bootstrap 在空配置时幂等初始化投入/产出细项树和 6 条默认指标，父级合计按叶子节点汇总。
- 修改: 权限 gate 补齐成本收入比和投入产出专题路径，避免新增接口绕过当前 RBAC 口径。
- 修复: 费用预算执行页面两个 TypeScript 静态错误，确保完整类型检查可通过。

### 风险评估
- 低风险: 本轮不新增数据库表、不修改主键、不调整唯一约束；明确不创建、不使用 `bcir_report_definition`、`bcir_fact_value` 等来源包旧正式模型表。
- 注意: `business_cost_income_value` 当前仍无真实业务值，页面会展示配置行和 0 值；需要通过新导入页或分析页录入实际/预算/预测后才产生非零指标。

### 验证
- `PYTHONPATH=apps/api .venv/bin/python -m compileall -q apps/api/app` 通过。
- `PYTHONPATH=apps/api .venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"` 通过，并初始化 `business_cost_income_item=18`、`business_cost_income_indicator=6`。
- 查库确认 `common.db` 与 `budget_2026.db` 均未出现 `bcir_%` 表。
- 成本收入比导入模板生成/预览服务自测通过：三张工作表 `实际数/预算数/预测数`，预览可识别有效写入单元格。
- 投入产出专题服务自测通过：A 群可生成 5 个产品的分产品明细导出工作簿。
- `npm --workspace apps/web exec tsc -- --noEmit` 通过。
- `npm run build` 通过，仅保留既有 Vite chunk size warning。

## v2.17-release-port (2026-05-22) — 测试服务器交付端口切换为 8443

### 变更来源
- 用户发布要求: 测试服务器前端端口统一使用 `8443`，重新生成 CTO 精准交付包。

### 变更明细
- 修改: `start.sh` 默认前端端口切换为 `8443`，后端仍为 `8009`。
- 修改: `apps/web/vite.config.ts` 与 `apps/web/playwright.config.ts` 默认前端访问端口切换为 `8443`。
- 修改: `apps/api/.env` 与 `apps/api/app/config.py` 的 CORS 默认白名单同步支持 `http://127.0.0.1:8443`、`http://localhost:8443`、`http://guanheng.webank.com:8443`。
- 文档: `README.md`、`docs/development/test-server-deployment.md`、`archive/handover/root_delivery_docs_20260601/交付说明_CTO_20260522_精准交付包_8443_含env_data_dist.md` 已按 8443/8009 端口口径更新。

### 验证
- `bash -n start.sh` 通过。
- `python3 -m py_compile apps/api/app/config.py apps/api/app/routers/expense_actual_import.py apps/api/app/schemas.py` 通过。
- `npm run build` 通过，仅保留既有 Vite chunk size warning。
- 当前交付包运行配置与部署说明以 `8443` 为准；下方历史记录中出现的 `5177` 仅代表此前本地开发验收端口。

## v2.16-ui-fix (2026-05-19) — BI映射维护按潘潘包设计调整

### 变更来源
- 用户验收反馈: 当前 BI映射维护表的功能设计与潘潘包不一致，需要使用潘潘包里的设计
- Codex: 对比 `archive/team_packages/incoming/20260519/潘潘_20260519_部门费用模块完善规范打包/` 后，增量合入 BI部门维护 / BI科目维护前端交互和后端引用数据逻辑
- 用户业务确认: `个金管理部 -> 消费者金融业务` 可用；`个人金融事业群` 是 `消费者金融业务` 的上级口径，不应作为 BI部门维护映射到 `消费者金融业务`

### 变更明细
- 修改: `ControlItemMappingContent.tsx` 按潘潘包设计恢复为“BI部门维护 / BI科目维护”双页签
- 修改: BI科目维护支持按分类父级折叠展示、按管控口径 + 多费用归属部门批量建映射、按预算科目树选择映射科目
- 修改: BI部门维护支持按事业群 / 费用归属部门分组展示，并在弹窗中按主体 -> 事业群 -> 费用归属部门选择目标部门
- 修改: `control_item_mapping.py` 补齐潘潘包的引用数据和自动生成逻辑，分类从部门预算科目树的二级父类推断
- 数据: 将既有 158 条 `control_item_subject_mapping.category` 从空值回填为二级分类，其中日常费用 93 条、业务费用 42 条、人力费用 17 条、IT费用 6 条
- 数据: 从潘潘来源库导入后，经业务纠偏删除 `个人金融事业群 -> 消费者金融业务`，当前保留 29 条 `manage_dept_owner_mapping`；导入前备份 `var/data/common.db` 到 `var/backups/common_before_bi_dept_mapping_import_20260519_185516.db`，纠偏前备份到 `var/backups/common_before_bi_dept_mapping_parent_fix_20260519_185646.db`
- 产物: 生成导入确认表 `outputs/acceptance/BI部门维护导入确认_20260519.xlsx` 和执行报告 `outputs/acceptance/BI部门维护导入执行结果_20260519.xlsx`

### 风险评估
- 低风险: 本轮不新增数据库表、不修改主键定义、不调整唯一约束；继续使用既有 `control_item_subject_mapping` 与 `manage_dept_owner_mapping`
- 注意: `manage_dept_owner_mapping.id` 为目标库自增主键，本轮导入不沿用来源库 id；业务唯一性仍由 `manage_department` 约束

### 验证
- `python -m py_compile apps/api/app/routers/control_item_mapping.py` 通过
- `PYTHONPATH=apps/api ./.venv/bin/python` 导入 `app.main` 通过，BI映射相关 12 个接口已注册
- `npm run build` 通过，仅保留既有 chunk size warning
- 运行态经 5177 代理验证: BI科目映射返回 158 条，分类为 `IT费用 / 业务费用 / 人力费用 / 日常费用`，BI部门维护纠偏后返回 29 条，部门树引用数据返回 10 个事业群分组

## v2.15-data-fix (2026-05-19) — 部门科目维护表按潘潘部门架构重建

### 变更来源
- 用户验收反馈: 部门科目维护表中出现“开心账户 / 开鑫贷”等旧演示口径，与潘潘部门费用架构不一致
- 用户确认: `dept_account` 直接按潘潘部门架构维护模版的数据结构更新；涉及主键变化已先输出 Excel 供确认

### 变更明细
- 新增: `apps/api/scripts/rebuild_dept_account_from_template.py`，用于从 `resources/business_inputs/部门架构维护模版.xlsx` 重建 `dept_account`
- 数据: `dept_account` 重建为两级部门架构，即 `主体 -> 事业群 -> 费用归属部门`，共 37 条，其中一级事业群 10 条、二级费用归属部门 27 条
- 数据: 删除 40 条不在确认模版中的旧主键，包括“开心账户 / 开心账户存款 / 开鑫贷”等演示数据，以及历史塞入 `dept_account` 的三级费用发生部门
- 口径: 费用发生部门继续归属于 `expense_framework_budget_department`，不再写入部门科目维护表，避免把费用整体框架快照误当成部门科目主数据
- 产物: 生成确认与执行报告 `outputs/acceptance/部门科目维护主键影响确认_20260519.xlsx`、`outputs/acceptance/部门科目维护更新执行结果_20260519.xlsx`，并在执行前备份 `var/data/common.db` 到 `var/backups/common_before_dept_account_rebuild_20260519_175847.db`

### 风险评估
- 中风险: 本轮不改表结构，但经用户确认后替换了 `dept_account.dept_code` 主键集合，删除 40 个旧主键；后续如有外部文档或旧脚本引用这些旧部门码，需要同步改为潘潘模版中的费用归属部门码
- 低风险: 未新增字段、未修改主键定义、未调整数据库钩稽关系，执行后 `PRAGMA foreign_key_check` 通过

### 验证
- `python -m py_compile apps/api/scripts/rebuild_dept_account_from_template.py` 通过
- 干跑报告: 目标 37 条，影响为删除 40 条、保留 37 条、无新增、无更新
- 正式执行后查库: `dept_account=37`、`level=1` 为 10 条、`level=2` 为 27 条、`level>2` 为 0、演示名称命中 0、父级孤儿 0
- 运行态验证: 后端 `http://127.0.0.1:8009/api/health` 返回 `{"status":"ok"}`，前端 `http://127.0.0.1:5177/` 返回 `200 OK`，经 5177 代理调用 `/api/dept-accounts` 返回 37 条且无“开心账户 / 开鑫贷”

## v2.14-data-init (2026-05-19) — 费用预测默认规则初始化

### 变更来源
- 用户验收反馈: 费用预测规则、预测录入、测算结果表结构已存在，但初始化数据为空，需要导入默认规则
- Codex: 对齐当前后端费用预测规则模板与潘潘增强版规则配置语义，按当前部门费用框架和预算科目树生成初始化数据

### 变更明细
- 新增: `apps/api/scripts/init_expense_forecast_default_rules.py`，用于幂等同步部门预算科目归口信息、导入费用预测默认规则并生成初始化录入/测算结果
- 数据: `budget_subject_catalog` 从 `expense_framework_subject` 同步 41 条归口管理部门/公式信息，保持部门预算科目树与费用整体框架一致
- 数据: 为 2026 年 `260519v1` 版本创建 156 条 `RESIDUAL_ALLOC` 默认规则、936 条规则参数、312 条年度录入初始化、1248 条测算结果和 1248 条预测录入初始化
- 规则: 默认规则使用原始规则导入格式中的 `scheme2` 参数组，包含 `allocation_mode=progressive`、`progressive_curve_type=arithmetic`、`auto_direction_mode=auto_last_vs_avg`、`last_value_source_mode=actual_first_then_forecast`、`rounding_mode=last_month_adjust`、`allow_negative=false`
- 产物: 生成导入核对表 `outputs/acceptance/费用预测默认规则导入报告_20260519.xlsx`，并在导入前备份 `var/data/common.db` 到 `var/backups/common_before_expense_forecast_defaults_20260519_170825.db`

### 风险评估
- 低风险: 本轮只导入初始化数据和新增可复跑脚本，不新增表字段，不修改主键，不调整钩稽关系
- 注意: 当前年度 `business_submission` / `capital_advice` 初始化为 0，因此默认测算结果行已生成，但金额仍需业务录入资划建议或后续接入预算目标后才会产生非零未来月预测值

### 验证
- `python -m py_compile apps/api/scripts/init_expense_forecast_default_rules.py` 通过
- 干跑结果: 计划创建规则 156 条、跳过 0 条
- 正式导入后查库: `expense_forecast_rule=156`、`expense_forecast_rule_param=936`、`expense_forecast_annual_entry=312`、`expense_forecast_calc_result=1248`、`expense_forecast_entry=1248`
- 运行态健康检查: 后端 `http://127.0.0.1:8009/api/health` 返回 `{"status":"ok"}`，前端 `http://127.0.0.1:5177/` 返回 `200 OK`

## v2.13-merge (2026-05-19) — 合并潘潘部门费用模块完善包

### 变更来源
- 潘潘: `archive/team_packages/incoming/20260519/潘潘_20260519_部门费用模块完善规范打包/`
- Codex: 按当前主线 PDD/PRD/数据规范/API 规范增量合入，仅接收费用管理功能增量，不覆盖数据库快照、env、dist 或旧运行结构

### 变更明细
- 新增: 费用预测表支持按事业群拆分查看、按预算科目查看费用归属部门明细，并将规则测算、人工覆盖、追踪明细整合进 `/api/expense-forecast/*`
- 修改: 费用预测表前端升级为潘潘增强版，支持主体/事业群/费用归属部门/预算科目多口径切换、单位切换、导入预览、按事业群导出和经营分析列
- 修改: 费用预算执行报表补入“本月环比增减额 / 本月环比%”，页面展示和导出 Excel 均保持同口径
- 修改: 费用预算执行报表导出继续使用当前主线的数据读取逻辑和上传入库口径，未回退为来源包旧路径读取方式
- 修改: 费用预测规则接口由费用预测主路由统一承载，避免旧规则路由与新规则实现重复挂载
- 文档: 收录 `docs/product/team_contributions/潘潘_20260519_pdd_patch.md`，并同步更新 System PDD、Database PDD 与文件总览

### 风险评估
- 中风险: 费用预测主路由由潘潘增强版整体替换，虽然路由导入和前端构建已通过，仍建议重点回归费用预测表的保存、导入、导出、规则测算和人工覆盖
- 低风险: 费用预算执行报表仅补充环比指标和导出字段，保留当前主线数据源与部门/科目过滤逻辑
- 数据库: 本轮未新增表、未改主键、未改钩稽关系；无需输出数据库确认 Excel

### 验证
- 后端 `python -m py_compile apps/api/app/routers/expense_forecast.py apps/api/app/routers/expense_budget_execution.py apps/api/app/main.py` 通过
- 后端 `python -m compileall -q apps/api/app` 通过
- 后端 `.venv` 环境导入 `app.main` 通过，确认 `/api/expense-forecast/group-view`、`/api/expense-forecast/subject-view`、`/api/expense-forecast/rules` 和 `/api/expense-budget-execution` 已注册
- 前端 `npm run build` 通过，仅保留既有 chunk size warning

## v2.12-fix (2026-05-14) — 修正潘潘费用模块合并验收问题

### 变更来源
- 用户验收反馈: 部门架构维护 Excel 已下载，但导入逻辑未按模版的层级空白继承方式处理
- 用户验收反馈: “费用预测逻辑配置”前端仍是简版展示，与潘潘包增强版不一致

### 变更明细
- 修改: 部门架构维护导入兼容 `数据模版` 中“主体 / 事业群 / 费用归属部门”的层级式稀疏行，子级行可继承上方事业群
- 修改: 部门架构维护导出工作表名统一为 `数据模版`，表头保持 `主体、事业群代码、事业群名称、费用归属部门代码、费用归属部门名称`
- 修改: “费用预测逻辑配置”恢复潘潘增强版前端，包含“规则管理 / 参数配置”、树形部门与预算科目选择、版本复制、导入预览、方案参数和变量映射配置
- 修复: `vite.config.ts` 的 `/api` 代理改为本地默认 `127.0.0.1:8003`，测试服务器 `start.sh` 显式注入 `127.0.0.1:8009`，避免 5177 本地开发页因代理到未启动的 8009 显示 `Internal Server Error`

### 风险评估
- 低风险: 部门架构导入仍为幂等 upsert，不覆盖 env 或数据库文件
- 低风险: 费用预测逻辑配置仅恢复前端展示和参数编辑能力，沿用当前 `/api/expense-forecast/rules*` 接口

### 验证
- 后端 `python -m py_compile apps/api/app/routers/dept_catalog.py apps/api/app/routers/expense_forecast_rules.py` 通过
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `app.main` 导入通过
- 使用 `部门架构维护模版.xlsx` 在临时数据库执行导入接口：有效维护行 37、成功 37、失败 0
- 部门架构导出接口返回工作表 `数据模版`，表头与下载 Excel 一致
- 本地 `http://127.0.0.1:5177/api/session` 从 Vite 代理返回后端正常 `401 未登录`，不再是 `500 Internal Server Error`
- 前端 `npm run build` 通过，仅保留既有 chunk size warning

## v2.11-merge (2026-05-14) — 合并测试环境服务器发布配置

### 变更来源
- 测试服务器部署资料: `archive/releases/关于测试服务器部署的内容/`
- Codex: 读取部署脚本、接口说明和截图后增量合入当前项目，不执行打包

### 变更明细
- 新增: 根目录 `start.sh` / `stop.sh`，用于一键启动/停止测试环境前后端服务
- 新增: `apps/api/.python-version` 与 `apps/api/pyproject.toml`，支持 uv 在后端目录创建隔离虚拟环境
- 新增: `docs/development/test-server-deployment.md`，记录端口、域名、CORS、启停和后续打包注意事项
- 修改: `vite.config.ts` 将测试环境前端服务切到 `0.0.0.0:8443`，允许 `guanheng.webank.com` Host，并将 `/api` 代理到后端 `8009`
- 修改: `apps/api/app/config.py` 默认 CORS 放行测试环境前端，并固定读取 `apps/api/.env`，避免从项目根目录启动时漏读环境变量
- 修改: `apps/api/.env` 放行 `127.0.0.1:8443`、`localhost:8443`、`guanheng.webank.com` 与 `10.65.*.*:8443`
- 修改: `.gitignore` 忽略 `.pids/` 与 `.logs/` 运行目录

### 风险评估
- 中风险: 默认开发端口从 5177/8003 切到测试环境 8443/8009；本轮按测试服务器发布要求处理
- 低风险: 启停脚本兼容 pnpm/npm，后端依赖以当前 `requirements.txt` 为基础补入 uv `pyproject.toml`
- 数据库: 本轮无结构变更、无数据覆盖

### 验证
- `bash -n start.sh` / `bash -n stop.sh` 通过
- 后端配置从项目根目录导入时可读取 `apps/api/.env` 中的 `CORS_ORIGINS` 与 `CORS_ORIGIN_REGEX`
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `ensure_databases()` 通过
- 后端 `app.main` 导入通过
- 前端 `npm run build` 通过，仅保留既有 chunk size warning

## v2.10-merge (2026-05-14) — 合并 Nick 模拟测算改造 v2

### 变更来源
- Nick: `archive/releases/nick_20260514_模拟测算改造_v2/`
- Codex: 仅甄别合入模拟测算模块改造，未整包覆盖来源包中的旧导航、旧后端路由、旧数据库或其它模块代码

### 变更明细
- 新增: “模拟测算（正算）/ 模拟测算（倒算）”两个入口，保留在“预算数据输入”分组下
- 新增: 正算页“开始计算”和“导出Excel”，取消旧“调整拨备，保持利润不变”列
- 新增: 正算结果中“风险成本-基础拨备”下钻展示产品风险成本、日均余额、风险成本率
- 新增: 倒算页支持净利润目标、拨备覆盖率目标和输出变量选择
- 新增: 当前 `/api/budget-simulation/export` 导出模拟参数与测算结果 Excel；历史 `/api/driver/simulation-export` 不再作为当前入口
- 修改: 当前 `/api/budget-simulation/baseline` 与 `/api/budget-simulation/result` 读取 `data_account_metric_node` / `data_account_metric_binding` / `data_account` / 年度 `budget_data`，不再依赖 `report_account`、`report_data_mapping` 或旧 `/api/driver/*` 链路作为模拟测算数据入口

### 风险评估
- 中风险: 数据科目指标绑定当前仍存在部分业务指标未完整绑定，缺口处按数据科目编码/名称兜底读取；后续应持续补齐 `data_account_metric_binding`
- 低风险: 倒算算法为目标反推建议值和结果联动，后续可按正式业务公式继续精修
- 数据库: 本轮无结构变更、无数据覆盖、无 env/dist 覆盖

### 验证
- 后端 `PYTHONPATH=apps/api uv run python -m py_compile apps/api/app/routers/budget_simulation.py` 通过
- 后端 `app.main` 导入并确认当前 `/api/budget-simulation/baseline`、`/api/budget-simulation/result`、`/api/budget-simulation/export` 已注册
- 后端带现有会话调用当前 `/api/budget-simulation/baseline`、`/api/budget-simulation/result`、`/api/budget-simulation/export` 均返回 200；旧 `/api/driver/*` 不再作为当前验证入口
- 前端 `npm run build` 通过，仅保留既有 chunk size warning

## v2.9-merge (2026-05-14) — 合并 Codex0508 全量回退包中的部门费用架构与成本收入比增量

### 变更来源
- Codex: `archive/releases/Codex_20260511_Codex0508全量回退包_含数据库_env_excel/`
- Codex: 按当前项目 PDD / PRD / 数据规范 / 接口规范 / 设计规范执行增量合并，纳入费用架构与用户确认需要的成本收入比模块主代码

### 变更明细
- 新增: “BI映射维护”页面与接口，维护“管控口径名称 + 归口管理部门 → 部门预算科目”以及“归口管理部门 → 费用归属部门”映射
- 新增: 费用执行明细导入补匹配逻辑，预算科目为空时可按 BI/管控口径映射回填匹配
- 新增: “费用预测逻辑配置”页面与接口，支持预测规则 CRUD、版本复制、模板下载、Excel 导入预览/应用和启用规则检查
- 新增: “业务支出成本收入比分析”页面与接口，支持主体、月份、事业群、产品、金额单位筛选，以及实际/预算/预测值录入
- 新增: “业务支出成本收入比维护”页面与接口，支持业务投入/产出细项树和评估指标维护
- 新增: 数据库幂等建表 `control_item_subject_mapping`、`manage_dept_owner_mapping`、`expense_forecast_rule`、`expense_forecast_rule_param`、`expense_forecast_rule_variable`、`expense_forecast_calc_result`、`expense_forecast_override`
- 新增: 年度预算库幂等建表 `business_cost_income_item`、`business_cost_income_indicator`、`business_cost_income_value`
- 保留: 未覆盖回退包中的数据库/env/旧 dist/旧导航/旧 WorkArea
- 保留: 未覆盖回退包中的 `bcir.db`，成本收入比数据结构改由年度预算库初始化创建

### 风险评估
- 中风险: 3 项（费用执行导入匹配口径、预测规则后续自动测算引擎仍需深化、成本收入比指标配置口径）
- 低风险: 4 项（新增维护页、规则 CRUD、成本收入比录入页、PDD/CHANGELOG/Files 记录）
- 数据库: 新增幂等表结构，不覆盖现有 SQLite 数据和 env

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `PYTHONPATH=backend ./.venv312/bin/python` 执行 `ensure_databases()` 通过
- 后端 `app.main` 导入并确认 `/api/control-item-mapping/*`、`/api/manage-dept-owner-mapping/*`、`/api/expense-forecast/rules*`、`/api/business-cost-income-ratio/*` 已注册
- 前端 `npm run build` 通过，仅保留既有 chunk size warning
- 本地 `http://127.0.0.1:5177/` 返回 200，已确认开发服务中的 `NavigationTree.tsx` 包含“BI映射维护”“费用预测逻辑配置”“业务支出成本收入比分析”“业务支出成本收入比维护”

## v2.8-merge (2026-05-13) — 合并 Codex0508 完整回退包登记

### 变更来源
- Codex: `archive/releases/Codex_20260511_Codex0508完整回退包_含数据库与env/`
- Codex: 按当前项目 PDD / PRD / 数据规范 / 接口规范 / 前端设计规范执行增量合并，不按回退包整包覆盖

### 变更明细
- 新增: 收录 `docs/product/team_contributions/Codex_20260511_完整回退包_pdd_patch.md`
- 修改: System PDD 登记完整回退包为内部受控回滚资产，明确恢复前需备份并由 PMO/CTO 确认
- 修改: Database PDD 明确回退包中的 `var/data/*.db`、根目录数据库、`apps/api/.env` 仅作为快照，不在常规合并中覆盖当前运行数据
- 修改: Files.md 记录本轮合并范围和安全边界
- 保留: 未合入回退包中的旧源码、旧数据库、旧 env、`dist/`、根目录数据库和 `apps/api/common.db`/`apps/api/budget.db`
- 跳过: 回退包中的 `business_cost_income_ratio` 页面/接口/`bcir.db` 尚无当前 PDD/PRD/数据模型/接口契约支撑，本轮不进入运行链路

### 风险评估
- 高风险规避: 未覆盖当前 `var/data/*.db` 与 `.env`，避免回退 2026-05-12 以后预算输出、产品预算工作台、智能报告/PPT 和统一 UI 规范相关成果
- 中风险: 1 项（回退包中存在未立项功能，已登记但未合入）
- 低风险: 2 项（PDD/CHANGELOG/Files 记录）
- 数据库: 本轮无结构变更、无数据导入、无快照覆盖

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `PYTHONPATH=backend .venv312/bin/python` 执行 `ensure_databases()` 通过
- 后端 `app.main` 导入通过，仅保留既有 LangGraph/LangChain deprecation warning
- 前端 `npm run build` 通过，仅保留既有 chunk size warning

---

## v2.7-feature (2026-05-12) — 新增预算输出展示报表一期

### 变更来源
- 用户: 预算管理模块需要形成“预算工作台和规则配置 → 预算输入 → 预算输出”闭环，并以 `预算分析报表.xlsx` 为最终展示样式目标
- Codex: 基于现有展示版本槽位、报告科目树、产品科目树和 `budget_summary` / `compare_budget_summary` 增量实现

### 变更明细
- 新增: 左侧导航顶层分组“预算输出”，一期入口为“预算展示报表”
- 新增: 预算展示报表前端页面，包含“全行总表 / 分产品概览 / 单产品明细”三个页签
- 新增: 年份、预算基准版本、预测版本多选和产品范围筛选；默认按当前年份自动识别年初预算基准与最新预测版本
- 新增: 产品节点选择能力，父级产品节点按其下级产品汇总，默认全行可见
- 新增: Excel 式表格交互，报告科目行默认展开到2级，月度列在版本表头内展开/收起
- 新增: `/api/budget-output/display-report` 只读接口，按报告科目树聚合真实预算数据
- 更新: `CONTEXT.md` 记录预算输出、预算展示报表、展示版本槽位和产品节点汇总等领域语言

### 风险评估
- 中风险: 2 项（预算展示报表聚合口径、产品父节点汇总口径）
- 低风险: 3 项（新增导航、前端页面、只读接口 DTO）
- 数据库: 本轮无表结构变更

### 验证
- 后端 `python3 -m compileall apps/api/app/routers/budget_output.py apps/api/app/schemas.py apps/api/app/main.py` 通过
- 前端 `npm run build` 通过，仅保留既有 chunk size warning
- 本地登录后调用 `/api/budget-output/display-report?show_levels=1&product_codes=Z0001&product_codes=Z0201` 返回真实版本、产品块与报告科目行数据
- 前端开发服务已启动在 `http://127.0.0.1:5177/`

---

## v2.6-merge (2026-05-11) — 合并 Codex0508 费用同步上传规范包

### 变更来源
- Codex: `Codex_20260511_Codex0508项目规范打包`，费用数据同步管理上传化与 PDD 补丁
- Codex: 在当前主干上执行增量合并，保留潘潘 0511 费用增强、模拟测算、工作台、参数模板和智能报告等已有能力

### 变更明细
- 修改: 数据同步管理页将“费用整体框架”入口收敛为“初始化框架导入”，强调仅用于历史初始化或批量导入
- 修改: 初始化框架导入预览、确认与完成提示减少对产品部门映射的运行时暴露，日常配置维护以系统主数据为准
- 确认: 当前主线已具备 `/api/expense-budget-execution/admin/framework-preview`、`/framework-sync`、`/actual-sync` 上传接口，未使用来源包旧文件覆盖
- 新增: 收录 `docs/product/team_contributions/Codex_20260511_pdd_patch.md`

### 风险评估
- 中风险: 1 项（费用同步入口文案与操作语义调整）
- 低风险: 2 项（前端提示与 PDD/CHANGELOG 记录）
- 数据库: 本轮无表结构变更

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `PYTHONPATH=backend .venv312/bin/python` 执行 `ensure_databases()` 通过
- 后端 `app.main` 导入并确认 `/api/expense-budget-execution/admin/framework-preview`、`/framework-sync`、`/actual-sync` 已注册
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告
- 本地 `http://127.0.0.1:5177/` 已能服务新版 `DataSyncManagementContent.tsx`，确认包含“初始化框架导入”“预览导入结果”“导入初始化框架”

---

## v2.5-merge (2026-05-11) — 合并潘潘 0511 费用模块修复与导出增强

### 变更来源
- 潘潘: 费用模块修复与导出增强，覆盖部门预算科目维护、部门科目维护、费用执行明细导入、费用预测表和费用预算执行报表
- Codex: 在当前主干上执行增量合并，保留模拟测算、工作台、参数模板、智能报告和数据科目指标树等已有能力

### 变更明细
- 新增: 部门预算科目“归口管理部门”字段维护、搜索与 Excel 导出
- 新增: 部门科目主体维度，并在部门名称调整时同步费用框架、费用预测、费用执行和原始导入匹配引用
- 新增: 费用预测年度级“业务报送”“资划建议”录入表和接口逻辑
- 修改: 费用预测表新增全年预测差额、预算执行率、业务报送、资划建议、金额单位切换、字段选择导出和按事业群导出
- 修改: 费用执行明细导入优先使用系统主数据口径，减少对外部框架 Excel 的运行时依赖
- 修改: 费用预算执行报表支持月报格式、部门模式、科目模式导出，Excel 汇总行保留公式并跟随页面金额单位
- 保留: 未覆盖来源包中的旧版 API 基址、智能报告、预算预测驱动、模拟测算等无关差异

### 风险评估
- 高风险: 2 项（费用预测/执行导出逻辑、费用主数据引用同步）
- 中风险: 3 项（新增年度预测表、部门/预算科目 DTO 扩展、费用报表筛选口径）
- 低风险: 2 项（前端展示列、PDD/文件清单记录）

### PDD 更新
- System PDD: 新增 §0.12 本轮需求变更（2026-05-11）— merge-release
- Database PDD: 新增 §0.8 本轮同步说明（2026-05-11）— merge-release
- Files.md: 追加 2026-05-11 Panpan 合并摘要
- Team contribution: 收录 `docs/product/team_contributions/潘潘_20260511_pdd_patch.md`

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `PYTHONPATH=backend .venv312/bin/python` 执行 `ensure_databases()` 通过
- 数据库确认 `dept_account.entity_name`、`budget_subject_catalog.manage_department`、`expense_forecast_annual_entry` 已存在
- 后端 `app.main` 导入并确认费用模块相关路由注册通过
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.4-merge (2026-05-11) — 合并模拟测算模块

### 变更来源
- Kevin: 新增预算预测驱动后的模拟测算模块
- Codex: 在当前主干上执行增量合并，保留工作台、参数模板、智能报告、费用模块和数据科目指标树等已有能力

### 变更明细
- 新增: “预算数据输入 / 模拟测算”导航入口与工作区页面
- 新增: 情景参数表，支持选择管理贷款时点规模、贷款收益率、联合贷款收益率、风险成本率及贷款产品，并自动读取 2026 年基准情景
- 新增: 测算结果表，展示盈利性指标、风险指标，以及“调整拨备、保持利润不变”口径
- 新增: 模拟测算基准和结果接口；当前入口已收敛为 `/api/budget-simulation/baseline` 与 `/api/budget-simulation/result`
- 修正: 百分比类模拟参数前端提交时自动归一化，输入 `5` 或 `5%` 均按 `5%` 测算
- 保留: 本轮未覆盖来源包中的数据库文件和无关智能报告/PPT改动，避免回退当前主线

### 风险评估
- 中风险: 2 项（新增预算预测驱动路由接口、模拟测算联动口径）
- 低风险: 3 项（新增页面、导航挂载、前端 DTO）
- 数据库: 不新增表结构；当前实现只读取标准指标树、数据科目绑定和年度预算库，不再复用 `driver_indicator`、`driver_account_mapping` 或 `report_data_mapping`

### PDD 更新
- System PDD: 新增 §0.11 本轮需求变更（2026-05-11）— merge-release
- Files.md: 追加 2026-05-11 合并摘要

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `app.main` 导入并确认当前 `/api/budget-simulation/baseline`、`/api/budget-simulation/result` 已注册；历史 `/api/driver/*` 已退休
- 运行中后端对两个新接口返回 `401 未登录`，说明服务可达且鉴权链路生效
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.3-merge (2026-05-09) — 合并工作台和参数模板

### 变更来源
- ZLC: 增加工作台和参数模板
- Codex: 在当前主干上执行增量合并，保留费用模块、预算预测驱动、智能报告与数据科目指标树等已有能力

### 变更明细
- 新增: 预测预算工作台后端概览接口与前端页面，展示开鑫贷/小小账户预测行和绑定概览
- 新增: 预算基本假设接口与参数模板维护页面，支持参数目录、参数值、规则模板和引用关系查看
- 新增: `assumption_parameter`、`assumption_value`、`assumption_rule_template`、`forecast_workbench_layout`、`forecast_line_binding` 等表的幂等建表和默认种子
- 修改: `data_account` 兼容新增 `budget_rule_code`、`budget_rule_config_json`，为后续模板绑定保留字段
- 修改: 导航树与工作区新增“预测预算工作台”“参数与模板维护”入口，权限按数据录入用户及以上开放
- 保留: 当前主线已有的费用管理、预算预测驱动、智能报告、产品层级和数据科目指标树逻辑，未用来源包旧版本覆盖

### 风险评估
- 高风险: 1 项（新增数据库表与现有 `common.db` 自愈迁移）
- 中风险: 3 项（新增 API 路由、权限映射、前后端 DTO）
- 低风险: 2 项（工作台/参数模板展示页面、PDD/文件清单记录）

### PDD 更新
- System PDD: 新增 §0.9 本轮需求变更（2026-05-09）— merge-release
- Database PDD: 新增 §0.5 本轮同步说明（2026-05-09）— merge-release
- Files.md: 追加 2026-05-09 合并摘要

### 验证
- 后端 `python -m compileall apps/api/app` 通过
- 后端 `PYTHONPATH=backend ./.venv/bin/python` 执行 `ensure_databases()` 通过，并确认新增表种子入库
- 后端 `app.main` 导入通过，仅有既有 LangGraph deprecation warning
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.2-merge (2026-05-08) — 合并费用管理模块与预算预测驱动增强

### 变更来源
- Kevin/Codex: 预算预测驱动因素模块与数据科目绑定增强
- Panpan: 费用管理五大核心模块

### 变更明细
- 新增: 部门预算科目维护、费用执行明细导入、费用预测表、费用预算执行报表、数据同步管理五个费用入口
- 新增: 费用管理相关表结构，包括 `budget_subject_catalog`、`expense_forecast_entry`、`expense_actual_detail_raw` 等
- 新增: 费用模块后端路由、前端页面、导航入口和权限映射
- 新增: `xlrd==2.0.1` 依赖，用于读取 `.xls` 费用执行源文件
- 修改: 预算预测驱动模块复用报告科目分类体系，并支持人工维护驱动指标-产品-数据科目绑定
- 修改: 预算预测驱动模板增加报告科目、数据科目编码、数据科目名称，导入可精确写入数据科目
- 保留: 当前主线的 `data_account.product_codes` 多产品范围表达、产品层级和预算预测驱动逻辑，未用来源包旧模型覆盖

### 风险评估
- 高风险: 3 项（新增费用预测写库、费用执行导入写库、费用相关数据库表）
- 中风险: 4 项（新增 API 路由、权限映射、导航入口、前后端 DTO）
- 低风险: 3 项（PDD、说明文档、模板与页面展示）

### PDD 更新
- System PDD: 新增 §0.8 本轮需求变更（2026-05-08）— merge-release
- Database PDD: 新增 §0.3 本轮同步说明（2026-05-08）— merge-release
- Files.md: 追加 2026-05-08 合并摘要

### 验证
- 后端 `py_compile` 通过
- 后端 `app.main` 无写库导入检查通过
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.1 (2026-05-06) — 产品多层与Excel导入改造

### 变更来源
- ZLC: 20 项变更

### 变更明细
- 新增: `product_codes TEXT` 字段替代 `applies_to_all_products` 布尔值，支持"全部产品 / 公司级 / 指定多产品"三类语义
- 新增: `ProductType.parent_code`、`ProductType.level` 字段，支持产品科目多层树形结构
- 新增: `ProductMultiSelectDialog.tsx` 分层多选产品弹窗，支持父级展开到叶子节点
- 新增: Excel 导入"新增/更新"与"覆盖"两种模式（upsert/replace）
- 修改: 产品编码规则从 `Z+4位` 放宽为 `Z+4~8位`，兼容层级编码
- 修改: 数据科目 CRUD 全链路适配 `product_codes`
- 修改: 预算数据导入结果区分新增/覆盖/失败统计
- 移除: `data_account.applies_to_all_products` 字段及关联 CHECK 约束

### 已知待解决问题
- 产品科目层级已由 `product_type.parent_code`/`level` 固化到 schema 与初始化迁移。
- 已退役全局部门-产品映射；部门责任归属由费用模块使用 `dept_account` 表达，产品维度由 `product_type` 表达。
- `budget_summary` 重建不再通过产品反推部门，避免旧映射造成的组织维耦合。

### 风险评估
- 高风险: 4 项（核心数据模型变更，影响公式引擎、预算汇总、导入导出链路）
- 中风险: 4 项
- 低风险: 2 项

### PDD 更新
- System PDD: 新增 §0.7 本轮需求变更（2026-05-06）— ZLC
- Database PDD: 新增 §0.2 本轮同步说明（2026-05-06）— ZLC
- Files.md: ZLC 已追加 2026-05-06 更新摘要

### 数据库迁移
- `data_account`: `ALTER TABLE ADD COLUMN product_codes TEXT`，数据已从 `applies_to_all_products` + `product_code` 迁移
- `product_type`: `ALTER TABLE ADD COLUMN parent_code TEXT`，`ALTER TABLE ADD COLUMN level INTEGER DEFAULT 1`

---

---

## v2.0 (2026-04-29) — PDD 文档体系建立与项目初始化

### 变更来源
- 项目初始化阶段，未按团队成员拆分

### 变更明细
- 新增: 完整 PDD 文档体系 (System/Database/Agent/Rules/ERD/Files)
- 新增: FastAPI 后端 + Vite React 前端项目骨架
- 新增: 三库架构 (common.db / budget_{year}.db / compare.db)
- 新增: LangGraph Agent 智能体框架
- 新增: 飞书机器人 WebSocket 通道
- 新增: Excel 导入导出功能
- 新增: 公式引擎与预算汇总预聚合
- 新增: 多版本管理与多年度对比透视
- 新增: RLBA 用户权限体系

### 风险评估
- 高风险: 0 项（初始化阶段）
- 中风险: 0 项
- 低风险: 0 项

### PDD 更新
- System PDD: v1.0 初始版本
- Database PDD: v2.0 初始版本
- Agent PDD: 初始版本
- Rules PDD: 初始版本
- Files.md: 初始版本

---
