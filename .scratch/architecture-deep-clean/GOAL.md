# GOAL: 银行业务预算系统架构深度清理

Status: current-architecture-updated
Owner: 架构师 / CTO 评审
Date: 2026-05-19

## 1. 总目标

把当前多次合并形成的混合代码仓库，重构为“单一事实源清晰、Module 职责单一、Interface 小而稳定、数据库表简单直接”的预算系统。

本次架构清理的核心不是继续兼容所有历史入口，而是删除已经退出主线的旧路径，把正式业务能力收敛到少数 deep Module：

- **数据科目维护表** 是预算配置、公式加工、预算展示、预算输入、模拟测算和费用预测指标表达式的数据科目主事实源。
- **标准数据科目指标树** 是指标口径主事实源。
- **BudgetDataWriter** 是所有 `budget_data` 写入的唯一 Module。
- **预算展示报表** 使用预算系统真实数据和正式展示投影，不再依赖 Excel 底稿、旧报告科目编码或静态 mock。
- 旧 `report_account` / `report_data_mapping` 已删除，不再保留为兼容入口、历史对照入口或旧接口过渡层。

验收结果应当让维护者能回答三个问题：

1. 一个业务事实在哪里维护，只有一个答案。
2. 一个页面或路由属于哪个专业 Module，只有一个答案。
3. 一个表为什么存在、是否源表或投影表、能否重建，只有一个答案。

## 2. 当前架构诊断

### 2.1 数据库事实源混杂

当前运行数据库为：

- `var/data/common.db`
- `var/data/budget_2025.db`
- `var/data/budget_2026.db`
- `var/data/compare.db`

`common.db` 当前同时承载基础主数据、数据科目指标树、费用框架、费用预测、智能报告、智能 PPT、预算假设、用户会话和审计等大量表。它已经从“公共字典库”膨胀成多个业务 Module 的混合库。

本次抽样发现：

- `data_account`、`data_account_metric_node`、`data_account_metric_binding` 已形成正式的数据科目体系。
- `report_account` / `report_data_mapping` 已从当前 schema 和运行库删除；后续不得通过兼容别名恢复。
- `driver_category`、`driver_indicator`、`driver_product`、`driver_account_mapping` 已随旧页面退休，模拟测算不再依赖第二套驱动身份表。
- `forecast_workbench_layout`、`forecast_line_binding`、`assumption_parameter`、`assumption_value`、`assumption_rule_template` 已随隐藏预测工作台/假设参数页面退休，避免形成第二套预算预测配置语言。
- `budget_summary` 与 `compare_budget_summary` 是投影表，但很多调用点需要知道它们的重建时机、展示层级和来源规则，Interface 过宽。
- Database PDD / ERD 的“分库存放”只列出少数核心表，与运行库实际表集合不一致，PDD 不能直接指导清理。

### 2.2 Module 过浅且职责泄漏

现有代码中大量 Module 的 Interface 几乎等于 implementation：

- `apps/api/app/init_db.py` 超过 3000 行，同时负责建表、迁移、历史兼容、默认种子、跨年度库修补和业务表补齐。删除测试结论：如果删除它，复杂性不会集中到一个更合理的 Module，而会散落到所有启动和迁移路径，说明当前 Module 太浅且 Interface 无法表达专业职责。
- `apps/api/app/main.py` 超过 2200 行，同时注册路由、维护认证、预算版本上下文、公式计算、汇总重建、对比同步、导出任务和数据科目引用计数。调用者必须理解太多运行顺序和隐含状态。
- `apps/api/app/routers/budget_output.py`、`expense_forecast.py`、`expense_budget_execution.py`、`budget_simulation.py` 都是大路由文件，路由、查询、业务规则、导出、DTO 组装混在一个 Module 内。
- 前端 `DataAccountContent.tsx`、`BudgetInputContent.tsx`、`ExpenseBudgetExecutionContent.tsx`、`PivotChartContent.tsx` 等大组件把页面状态、数据加载、表格渲染、业务规则和导出操作混在一起，缺少深的 read-model Module。

### 2.3 PDD 多轮补丁堆叠，权威关系不清

当前文档同时存在：

- System PDD
- Database PDD
- Database ERD
- Rules PDD
- UI Unified PDD
- Agent PDD
- 多个 team contribution patch

这些文档记录了合并历史，但没有明确区分“当前权威约束”和“历史补丁记录”。典型冲突包括：

- `CONTEXT.md` 已定义旧报告科目表已删除，不能成为兼容入口或新业务主事实源。
- System PDD 已要求预算展示报表通过标准指标树、数据科目绑定和年度预算事实/投影实现。
- Database PDD 已把 `report_account` / `report_data_mapping` 标为已删除旧表，新预算输出、模拟测算、费用预测指标表达式和 AI 行为解析到 **标准数据科目指标树** 与 **数据科目维护表**。

清理前必须先把 PDD 从“合并流水账”收敛为“当前目标架构说明 + 历史记录归档”。

## 3. 目标架构原则

### 3.1 单一事实源

同一业务事实只能有一个源表：

- 数据科目身份：只在 `data_account.data_acct_code`，且必须等于产品前缀的 `data_account_metric_binding.metric_node_code`。
- 指标口径：只在 `data_account_metric_node`。
- 产品编码：`product_code` 是年度事实查询和展示维度；`data_account_metric_binding.scope_code` 只能由唯一指标号码前缀派生，用于绑定校验和一致性检查。产品名称只从 `product_type` 读取。
- 预算/实际明细：只在年度库 `budget_data`，由 `budget_actual` 区分。
- 预算汇总/对比：`budget_summary`、`compare_budget_summary` 只能是可重建投影，不允许成为反向维护入口。
- 旧报告科目表：已删除；不得定义数据科目身份、产品范围、公式口径、旧驱动身份或查询别名。

### 3.2 Deep Module 优先

每个专业 Module 必须提供小 Interface 和足够深的 implementation：

- caller 不需要知道底层表组合、历史字段、迁移别名或投影重建细节。
- tests 只跨 Module Interface 验证业务结果。
- 如果一个 helper 删除后复杂性不会在多个 caller 中重新出现，则删除它或内联。
- 如果一个 Module 只是给 SQL、DTO、React state 换名字，视为 shallow Module，需要合并或加深。

### 3.3 历史痕迹只允许在删除证据和过滤防线中存在

历史兼容逻辑不得散落在正式业务 Module 内。旧报告科目不再有 adapter；仅允许出现在删除脚本、删除报告、测试夹具和运行时过滤防线中。

允许存在的历史处理：

- 只读对照 adapter：用于审计和排查历史来源。
- 旧字段过滤：丢弃退役 query key 或过滤旧知识库记忆，不把旧请求翻译成正式 Module Interface。
- 运行时校验：发现旧编码、旧表或旧字段时失败/清理，而不是自动翻译成正式 Module Interface。

不允许继续存在的兼容形态：

- 旧表继续被新功能写入。
- 新页面通过旧报告科目、旧驱动分类或旧工作台表定义业务身份。
- 旧请求字段被迁移为当前指标字段。
- PDD 为历史入口保留同等权威。

## 4. 目标数据库形态

### 4.1 `common.db`: 基础主数据与系统治理

目标只保留跨年度、跨模块共享且不可从年度库重建的事实：

- `data_account`
- `data_account_metric_node`
- `data_account_metric_binding`
- `product_type`
- `dept_account`
- `budget_subject_catalog`
- `period`
- `users`
- `user_sessions`
- `operation_log`
- `databases`
- `edit_show_version`
- 必要的系统配置表

需要审计并决定删除、迁移或降级为 adapter 的表：

- `report_account`（已删除）
- `report_data_mapping`（已删除）
- `driver_category`
- `driver_indicator`
- `driver_product`
- `driver_account_mapping`
- `forecast_workbench_layout`（已退休）
- `forecast_line_binding`（已退休）
- `assumption_parameter`（已退休）
- `assumption_value`（已退休）
- `assumption_rule_template`（已退休）
- `smart_report_*`
- `smart_ppt_*`
- `expense_*`
- `business_cost_income_*`

原则：如果表表达的是某个专业 Module 的私有 implementation，就不应混在 `common.db` 的公共事实层中。若短期不迁库，也必须在 PDD 中标注“Module 私有表”，禁止其他 Module 直接读写。

### 4.2 `budget_{year}.db`: 年度预算事实与投影

目标表：

- `version`
- `budget_data`
- `budget_summary`
- `settings`

`budget_data` 只能通过 **BudgetDataWriter** 写入。任何路由、导入、Agent、费用预测、模拟测算、Excel 上传都不得绕过该 Module。

`budget_summary` 只能由汇总重建 Module 生成，不能被页面或导入流程手工维护。

### 4.3 `compare.db`: 对比展示快照

目标表：

- `compare_budget_summary`
- `compare_sync_job_log`
- `settings`

`compare.db` 是只读展示快照库。它的 Interface 应该是“同步展示版本槽位”和“读取对比快照”，而不是暴露底层插入、清空和重建细节。

## 5. 目标 Module 地图

### 5.1 数据科目维护 Module

职责：

- 维护 **标准数据科目指标树**。
- 维护 **数据科目维护表**。
- 生成 **唯一指标号码**。
- 管理产品范围绑定。
- 维护公式、手工补录开关、值类型。

不得承担：

- 报告科目展示层级的主事实维护。
- 预算明细值写入。
- 费用预测规则维护。
- 旧产品预算工作台草稿存储。

### 5.2 BudgetDataWriter Module

职责：

- 校验 `current_month` 窗口。
- 校验预算/实际口径。
- 校验公式科目写保护。
- 统一 upsert `budget_data`。
- 统一维护 `need_calc`、`value_source`、`manual_value`、`formula_value`。

不得承担：

- 页面展示查询。
- Excel 行解析。
- 报告/部门/产品树展开。
- 汇总投影生成。

### 5.3 预算输入 Module

职责：

- 读取当前产品可见的数据科目。
- 组装预算输入 read model。
- 调用 **BudgetDataWriter** 写入。

不得承担：

- 自己实现 `budget_data` SQL 写入。
- 自己决定公式口径。
- 自己维护数据科目绑定。

### 5.4 预算展示报表 Module

职责：

- 从正式预算事实和投影读取 **全行总表**、**分产品概览**、**单产品明细**。
- 使用 **展示版本槽位** 和 **报表展示版本** 组装列组。
- 生成 Excel 导出。

不得承担：

- 维护报告科目、数据科目或产品科目。
- 使用静态 Excel 底稿作为数据源。
- 通过旧报告科目表定义新业务身份。

### 5.5 模拟测算 Module

职责：

- 只维护模拟测算参数输入、基准读取和结果计算。
- 读取 **数据科目维护表** 作为可配置对象。
- 调用 **BudgetDataWriter** 或计算投影 Module 输出结果。

不得承担：

- 另建一套驱动分类主事实源来替代 **标准数据科目指标树**。
- 绕开预算输入 Module 直接写入预算明细。
- 恢复旧产品预算工作台入口。

### 5.6 费用 Module

职责：

- 维护费用执行、费用预测、部门预算科目和费用框架。
- 费用预测落入自己的规则与结果表。
- 若需要影响预算系统主表，必须通过正式 adapter 调用 **BudgetDataWriter** 或投影同步 Module。

不得承担：

- 把费用科目表作为全局数据科目或报告科目替代品。
- 在 `common.db` 中暴露可被任意 Module 直接读写的私有中间表。

### 5.7 智能报告 / 智能 PPT / Agent Module

职责：

- 作为只读优先的分析与生成 Module。
- 通过正式查询 Interface 获取预算、数据科目、产品、版本、展示快照。
- 高危写入必须走已授权的业务 Module Interface。

不得承担：

- 自己拼接跨库 SQL 去解释主数据身份。
- 自己创建新的指标、报告、产品或预算事实。
- 把模板占位符或 AI 识别结果升级为主事实源。

## 6. PDD 清理目标

PDD 必须从“补丁记录”改为“当前权威架构”：

1. `CONTEXT.md` 保留 domain language，并补充本次清理后的正式 Module 名称。
2. `Banking_Budget_Database_PDD.md` 只描述当前目标表结构、约束、投影和迁移 adapter；历史补丁移入附录或归档。
3. `Banking_Budget_Database_ERD.md` 必须与实际运行库和目标库一致；每张表标注事实表、投影表、adapter 表或待删除表。
4. `Banking_Budget_System_PDD.md` 只保留当前功能架构，删除与主线冲突的旧合并说明。
5. `Banking_Budget_Files.md` 改成当前文件地图，不再把所有历史 patch 作为同等权威。

验收标准：任何开发者只读 PDD，就能知道某张表是否允许新业务依赖，某个页面是否是正式入口，某个历史表何时删除。

## 7. 删除清单目标

以下内容需要逐项通过 deletion test：

- 旧产品预算工作台相关 active source、路由、表、DTO、文档入口。
- 报告科目维护作为新业务主事实源的所有依赖。
- 旧预算预测驱动分类表和工作台表中与 **标准数据科目指标树** 重复的定义。
- `init_db.py` 中过期的历史迁移、旧字段兼容、旧种子。
- `main.py` 中不属于 app bootstrap 的业务函数。
- 前端大组件内可下沉为 read-model Module、grid Module、export Module 的混合逻辑。
- PDD 中“本轮同步说明”式历史流水账。

删除不是第一步直接物理删除。每一项必须先确认：

- 是否仍有运行数据引用。
- 是否有正式 Module Interface 可替代。
- 是否需要一次性迁移。
- 是否需要短期 adapter。
- 是否可通过测试证明删除后业务结果不变。

## 8. 验收标准

### 8.1 数据库验收

- 每张表有唯一归属 Module。
- 每张表标注为事实表、投影表、adapter 表或待删除表。
- `common.db` 不再是所有 Module 的私有表垃圾桶。
- `budget_data` 无任何绕过 **BudgetDataWriter** 的写入路径。
- `budget_summary`、`compare_budget_summary` 可从正式事实重建。
- 新业务不依赖 `report_account.product_code`，也不恢复任何 `report_account` 兼容入口。
- 新业务不依赖 `driver_*` 作为数据科目身份。

### 8.2 后端验收

- `init_db.py` 被拆为 schema bootstrap、contract check、seed data、retired cleanup 四类 Module。
- `main.py` 只保留 app bootstrap、middleware 和 router wiring。
- 每个路由文件只负责 HTTP Interface；业务规则在专业 Module 内。
- 跨库查询通过正式 read-model Module 完成。
- 每个写入场景有对应 integration test。

### 8.3 前端验收

- 页面组件只负责交互编排和渲染。
- 数据加载、DTO 转换、表格行列模型、导出操作下沉到专业 Module。
- 预算输入、模拟测算、预算展示、透视、智能报告对同一数据口径展示一致。
- 不再保留旧工作台或旧预算指标录入的活跃入口。

### 8.4 PDD 验收

- PDD 不再互相矛盾。
- 当前权威、历史记录、迁移说明分区清楚。
- Database PDD / ERD 与运行库一致。
- 每个 Module 都能在 PDD 中找到职责和禁止事项。

## 9. 建议执行顺序

1. 建立数据库表归属清单：对 `common.db`、`budget_2025.db`、`budget_2026.db`、`compare.db` 每张表标注 owner Module、表类型、引用点、删除风险。
2. 收敛 PDD 权威：先把当前架构目标写入 Database PDD / System PDD / ERD，历史流水账归档。
3. 切断 `budget_data` 旁路写入：所有写入统一走 **BudgetDataWriter**。
4. 抽出预算展示、预算输入、模拟测算 read-model Module，先加深 Interface，再删除重复 SQL。
5. 确认旧报告科目表删除后的防线：新业务只从 **标准数据科目指标树** 与 **数据科目维护表** 取身份。
6. 清理 `driver_*` / `forecast_workbench_*` / `assumption_*` 重叠表，保留真正有业务价值的专业 Module，删除隐藏页面和重复配置语言。
7. 拆 `init_db.py` 和 `main.py`，把历史迁移/兼容逻辑从运行主线删除或收敛到退休清理与拒绝校验。
8. 前端按页面重构大组件，先从数据科目维护、预算输入、预算展示报表、费用预测四个高风险页面开始。
9. 最后做运行库迁移和删除历史表，生成 release package。

## 10. Architecture deepening opportunities

1. **数据科目维护表 Module 加深**
   - Files: `apps/api/app/data_account_write.py`, `apps/api/app/routers/data_accounts.py`, `apps/web/src/app/components/DataAccountContent.tsx`, `var/data/common.db`
   - Problem: 数据科目身份已经收敛，但页面、路由、PDD 和历史报告/驱动依赖仍泄漏业务身份规则。
   - Solution: 让数据科目维护 Module 成为唯一创建、修改、绑定、校验数据科目身份的 seam。
   - Benefits: 提高 locality；新增或修复数据科目规则只改一个 Module，所有调用方获得 leverage。

2. **BudgetDataWriter Module 加深**
   - Files: `apps/api/app/budget_data_writer.py`, `apps/api/app/main.py`, `apps/api/app/routers/budget_input_runtime.py`, `apps/api/app/routers/budget_actual_batch.py`, `apps/api/app/routers/expense_forecast.py`
   - Problem: `budget_data` 写入规则有集中趋势，但仍有很多调用点需要理解窗口、公式、投影刷新和标脏。
   - Solution: 把所有预算/实际写入压到一个 deep Interface，导入和页面只提交业务意图。
   - Benefits: 写入一致性和测试 surface 收敛，避免多个 caller 各自实现财务口径。

3. **预算展示报表 read-model Module 加深**
   - Files: `apps/api/app/routers/budget_output.py`, `apps/web/src/app/components/BudgetDisplayReportContent.tsx`, `docs/product/Banking_Budget_System_PDD.md`
   - Problem: 预算展示报表曾夹在旧报告科目表、Excel 样式参考和正式预算投影之间。
   - Solution: 定义正式 read model：输入为展示版本槽位、产品范围和视图类型，输出为全行总表/分产品概览/单产品明细。
   - Benefits: caller 不需要知道报告树、投影表和月度列细节；测试可以直接验证报表 Interface。

4. **Schema/Migration Module 加深**
   - Files: `apps/api/app/init_db.py`, `docs/product/Banking_Budget_Database_PDD.md`, `docs/product/Banking_Budget_Database_ERD.md`
   - Problem: 建表、当前合同校验、历史兼容和种子混成一个 shallow Module。
   - Solution: 拆成 schema bootstrap、contract check、seed data、retired cleanup。
   - Benefits: 每次发版只评审对应当前合同；历史兼容被删除或变成明确拒绝校验。

5. **模拟测算 Module 去重**
   - Files: `apps/api/app/routers/budget_simulation.py`, `var/data/common.db`
   - Problem: `driver_*`、`forecast_workbench_*`、`assumption_*` 曾与 **标准数据科目指标树** 重复表达配置对象。
   - Solution: 保留模拟测算 Module，删除旧/隐藏页面、重复 Interface 和重复身份定义表。
   - Benefits: 模拟测算获得稳定 seam，数据科目和产品身份的 locality 回到主数据 Module。

6. **PDD 权威层加深**
   - Files: `CONTEXT.md`, `docs/product/Banking_Budget_System_PDD.md`, `docs/product/Banking_Budget_Database_PDD.md`, `docs/product/Banking_Budget_Database_ERD.md`, `docs/product/Banking_Budget_Files.md`
   - Problem: 文档现在记录了很多 merge history，但当前架构约束不够清晰。
   - Solution: 当前权威与历史记录分离，所有表和 Module 都有 owner、职责和禁止事项。
   - Benefits: AI 和开发者都能从 PDD 获得高 leverage，不再每次从历史补丁里推理当前真相。

## 11. 非目标

- 不在本 GOAL 中直接重写所有业务功能。
- 不无备份删除运行库数据。
- 不把历史兼容逻辑伪装成正式功能。
- 不为了“拆文件”而制造更多 shallow Module。
- 不在未形成正式 Module Interface 前直接大规模迁库。
