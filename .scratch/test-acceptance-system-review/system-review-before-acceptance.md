# 测试验收前系统梳理

日期：2026-06-19
范围：当前工作树 `/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)`
依据：`CONTEXT.md`、`docs/development/current-system-map.md`、`docs/development/active-worktree-manifest.md`、`预算管理系统_测试验收方案.md`、当前代码与本机运行态检查。

## 1. 总体结论

系统可以进入“功能测试准备”阶段，但不应直接判定“验收可放行”。

已确认的正向信号：

- 后端 `/api/health` 返回 `{"status":"ok"}`。
- `8009` 后端与 `8443` 前端均有进程监听。
- 前端本地地址当前是 `http://127.0.0.1:8443` / `http://localhost:8443`，浏览器首屏可打开登录页。
- `npx tsc -p apps/web/tsconfig.json --noEmit` 通过。
- `npm --workspace apps/web run build` 通过，仅有 Vite chunk size warning。
- 核心后端聚焦测试 22 条通过：退休表、`BudgetDataWriter`、运行指标身份、机构产品预算同步、权限策略。
- 当前 live SQLite inventory 显示 `retired_tables=none`，并且 `metric_identity_contract`、`org_product_metric_guard`、`org_product_metric_runtime_refs`、`business_data_account_refs` 等关键合同为 ok。

当前阻断/风险：

- `verify_worktree_organization.py` 失败：根目录有非 allowlist 文件、`scripts/`、`.DS_Store`、同名 symlink、`__pycache__`，并且文档清单漏登记若干脚本、服务和业务输入 workbook。
- `verify_current_database_inventory.py` 失败：`retired_workspace_menus=failed`，具体由两处 `direct_metric_identity_write` 触发：
  - `apps/api/app/init_db.py` 直接 `DELETE FROM data_account_metric_node`
  - `apps/api/app/services/v03_metric_node_catalog.py` 直接 `UPDATE data_account_metric_node`
- `npm run verify:delivery` 对当前工作区失败：当前目录不是干净 internal-runtime 交付包，包含 `.git`、`node_modules`、`.venv`、`archive`、运行日志和缓存目录等。
- 验收方案写了 `https://localhost:8443`，但当前 Vite/Playwright/实际服务是 HTTP 8443。`https://localhost:8443` 会 TLS 失败，`http://localhost:8443` 返回 200。
- 浏览器验收现在停在登录页，后续页面级验收需要明确测试账号和密码，不建议用未确认凭据自动登录。

## 2. 当前真实框架

### 2.1 代码入口

- 前端当前入口：`apps/web/`
  - Vite + React。
  - 左侧导航和页面挂载在 `apps/web/src/app/workspaceCatalog.tsx`。
  - 页面组件在 `apps/web/src/app/components/`。
  - 前端请求封装在 `apps/web/src/lib/`，当前多数页面已经从直接拼 `/api/...` 下沉到 lib Module。
- 后端当前入口：`apps/api/`
  - FastAPI 入口为 `apps/api/app/main.py`。
  - HTTP Interface 在 `apps/api/app/routers/`。
  - 业务读写 Module 在 `apps/api/app/services/` 与少量顶层 Module，如 `budget_data_writer.py`。
  - 数据库启动、合同校验、退休表删除在 `apps/api/app/db_bootstrap/` 和 `apps/api/app/init_db.py`。
- 当前资源入口：`resources/`
  - `download_template/` 保存当前下载/导入模板。
  - `business_inputs/` 保存仍支持当前系统的业务底稿。
  - `knowledge_base/` 保存 Agent 知识库和提示词资源。
- 当前运行态：`var/`
  - `var/data/` 是 live SQLite 数据目录。
  - `var/logs/`、`var/pids/`、`var/run/`、`var/output/` 是本地运行状态，不是源码。
- 历史归档：`archive/`
  - 只作追溯，不能作为当前功能入口或验收依据。

### 2.2 当前前端信息架构

当前导航树与验收方案大体对齐：

- 预算管理
  - 规则配置台：机构及产品、机构及产品指标
  - 预算数据输入：机构及产品数据录入、机构及产品预测输出
  - 预算输出报表展示：预算展示报表
  - 模拟测算模块：模拟测算（正算）、模拟测算（倒算）、智能预算模拟
- 部门费用预算管理模块
  - 部门科目维护、部门预算科目维护、BI映射维护、预算录入、费用执行明细导入、费用预测逻辑配置、部门费用预测、费用预算执行报表、业务支出成本收入比实际导入、业务支出成本收入比维护、投入产出专题概览
- 多维分析工具
  - 当前可编辑年度多版本透视报表、多年度对比透视报表、多年度数据透视图、智能分析报告、智能演示PPT
- 系统配置中心
  - 用户和权限管理、系统设定控制、数据同步管理、预算事实刷新跑批、Agent对话测试
- 帮助与使用说明

注意：部门费用里的“预算录入”是费用预算录入，不是旧经营预算录入入口。经营预算事实唯一用户侧录入口是“机构及产品数据录入”。

## 3. 核心业务 Module 和数据流

### 3.1 经营预算主线

经营预算主线的当前 domain 语言是：

1. **机构及产品** 维护产品和组织树。
2. **机构及产品指标体系** 维护唯一主指标体系、公式、汇总规则和唯一指标号码。
3. **机构及产品指标运行引用** 由机构及产品指标同步到 `data_account`、`data_account_metric_node`、`data_account_metric_binding`。
4. **机构及产品数据录入** 是唯一用户侧预算/实际/预测事实录入口。
5. **BudgetDataWriter** 是 `budget_data` 唯一写入 Module。
6. **预算事实刷新跑批** 负责公式重算、指标树 rollup、`budget_summary` / `budget_pivot_aggregate` / compare 读模型刷新。
7. **预算展示报表**、**多维分析工具**、**Agent**、**智能报告/PPT** 和 **智能预算模拟** 读取预算事实或派生读模型，不成为第二套主数据维护面。

必须保持的 interface 合同：

- `data_account.data_acct_code == data_account_metric_binding.metric_node_code`
- 唯一指标号码由产品前缀和产品内指标码组成，例如 `A05.01.01.001`
- `budget_data.value_source` 使用 `manual`、`formula`、`rollup`、`none`
- 用户不能手工覆盖 `rollup` 行
- 旧 `product_type`、旧 `report_account` / `report_data_mapping`、旧 `driver_*`、旧 `/api/budget-input/*`、旧预算 Excel 导入链路不能恢复

### 3.2 部门费用预算主线

部门费用预算管理模块是独立闭环：

1. **部门科目维护** 管 `dept_account`。
2. **部门预算科目维护** 管 `budget_subject_catalog`。
3. **BI映射维护** 管 `bi_ai_subject_mapping` 和 `manage_dept_owner_mapping`。
4. **费用执行明细导入** 将外部实际明细写入 `expense_actual_detail_raw`。
5. **费用预测逻辑配置** 管费用预测规则、参数、变量、模拟和重算。
6. **部门费用预测** 读取实际、规则、人工覆盖和年度输入，形成预测表。
7. **费用预算执行报表** 读取费用私有表与年度预算读模型，形成月报/部门/科目视图。
8. **业务支出成本收入比 Module** 使用 `business_cost_income_*` 年度私有表。

关键口径：

- 费用执行明细是费用闭环实际数 Adapter，不是经营预算全局事实表。
- 费用预算执行报表不是预算展示报表。
- 费用预测规则旧 `driver_*` 合同必须被拒绝，不自动迁移。

### 3.3 多维分析与智能能力

- 多维分析工具读取 `budget_summary`、`budget_pivot_aggregate`、`compare_budget_summary`、`compare_pivot_aggregate`。
- 智能分析报告和智能演示 PPT 读取当前预算系统形成的结果口径，不维护主数据。
- Agent 当前以登录会话、只读查询、安全澄清和透视建议为主。高风险写入必须二次确认，不能直接绕过正式录入流程。
- 智能预算模拟在产品定位上应保持“目标解析 -> 用户确认 -> 方案生成 -> 方案对比/传导拆解 -> 导出/确认”的业务工作台形态，不应退回成泛化 solver demo。

## 4. 验收方案需要校准的地方

### 4.1 前端地址协议

方案写的是：

- 后端 `http://127.0.0.1:8009`
- 前端 `https://localhost:8443`

当前实际：

- 后端 `http://127.0.0.1:8009/api/health` 正常。
- 前端 Vite 是 `http://127.0.0.1:8443`，Playwright 默认 `http://127.0.0.1:8443`。
- `https://localhost:8443` TLS 失败。

验收建议：把本地验收地址改为 HTTP 8443，除非后续明确启用 HTTPS 反代或证书。

### 4.2 经营预算 Excel 导入

方案中 `3.2 Excel 导入` 和回归项“预算底稿 Excel + 费用执行明细”容易混淆当前口径。

当前 `CONTEXT.md` 明确：

- 旧预算录入页面、旧 `/api/budget-input/*` 和旧预算 Excel 导入链路已物理退休。
- 经营预算事实用户侧录入口是 **机构及产品数据录入**。

验收建议：

- 费用执行明细 Excel 导入继续作为 P0/P1 场景。
- 机构及产品指标公式 Excel 导入可验，但它是指标/公式配置导入，不是旧预算事实 Excel 导入。
- 如果要验经营预算事实 Excel 导入，必须先确认当前产品是否真的保留了新口径导入入口；不能按旧 `/api/budget-input/*` 验。

### 4.3 退休入口验证要作为硬门禁

方案已经列出退休模块确认清单，这一项必须保留，而且要自动化优先：

- `report_account` / `report_data_mapping` 不存在
- `driver_*` 不存在
- `product_type` 不存在
- `/api/budget-input/*` 不注册
- 旧预算 Excel 导入链路不存在
- 旧数据科目独立配置入口不存在
- 旧报告科目维护入口不存在
- 潘潘旧费用类独立保护页不存在

当前 live DB `retired_tables=none` 是好信号，但 verifier 仍发现代码层直接写运行指标身份表，需要修复后才能把退休门禁视为通过。

## 5. 当前运行库盘点

`verify_current_database_inventory.py` 输出的 live row counts：

- `var/data/common.db`
  - tables=44
  - `data_account_metric_node`: 2444
  - `budget_output_display_item`: 1049
  - `bi_ai_subject_mapping`: 66
  - `dept_account`: 37
  - `budget_subject_catalog`: 59
  - `expense_actual_detail_raw`: 698
  - `expense_actual_import_batch`: 4
  - `expense_forecast_rule`: 156
  - `expense_forecast_entry`: 1248
  - `expense_forecast_calc_result`: 1248
  - `users`: 7
  - `operation_log`: 3133
- `var/data/budget_2025.db`
  - tables=9
  - `budget_data`: 0
  - `budget_summary`: 0
  - `budget_pivot_aggregate`: 0
  - `version`: 3
- `var/data/budget_2026.db`
  - tables=9
  - `budget_data`: 4158
  - `budget_summary`: 4848
  - `budget_pivot_aggregate`: 3852
  - `version`: 2
- `var/data/compare.db`
  - tables=4
  - `compare_budget_summary`: 4848
  - `compare_pivot_aggregate`: 0
  - `compare_sync_job_log`: 544

验收含义：

- 2026 年度库有可验经营预算事实和汇总数据。
- 2025 年度库当前事实/汇总为空，若验多年度对比，需要确认 compare 读模型是否足够，或先准备 2025 明细/汇总测试数据。
- 费用模块有实际导入、规则、预测结果数据，可做页面级验收。
- 用户表存在 7 个用户，但浏览器验收需要明确测试账号，不应猜测登录。

## 6. 已执行检查

### 6.1 通过

```bash
git diff --check
npx tsc -p apps/web/tsconfig.json --noEmit
npm --workspace apps/web run build
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/db/test_retired_deletion.py \
  tests/budget/test_budget_data_writer.py \
  tests/org_product/test_runtime_metric_identity.py \
  tests/org_product/test_org_product_budget_sync.py \
  tests/system/test_auth_access_policy.py -q
curl -sS http://127.0.0.1:8009/api/health
curl -sS -I http://localhost:8443
```

结果：

- `git diff --check`: 通过。
- `tsc`: 通过。
- `vite build`: 通过，chunk warning。
- 聚焦 pytest：22 passed。
- API health：ok。
- HTTP 8443：200 OK。

### 6.2 失败

```bash
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npm run verify:delivery
```

失败含义：

- `verify_worktree_organization.py` 是当前工作树组织门禁，失败不能忽略。
- `verify_current_database_inventory.py` 是数据库/退休口径/运行指标身份门禁，失败不能忽略。
- `npm run verify:delivery` 当前是在整个工作区直接跑 internal-runtime 包校验，失败不等于系统运行失败，但说明不能把当前目录直接当交付包验收。

## 7. 验收前 P0/P1 风险清单

### P0 阻断

1. 修复 `verify_current_database_inventory.py` 的 `direct_metric_identity_write`。
   - 当前运行指标身份应通过 **机构及产品指标体系** 同步 Module 维护。
   - `init_db.py` 和 `v03_metric_node_catalog.py` 的直接写法降低 locality，会绕过唯一主指标体系 interface。

2. 修复 `verify_worktree_organization.py`。
   - 把根目录临时/分析文件归入 `.scratch/`、`docs/` 或 `archive/`。
   - 移除或归档 `.DS_Store`、同名 symlink、`__pycache__`。
   - 同步更新 `README.md`、`docs/development/current-system-map.md`、`docs/product/Banking_Budget_Files.md`、`resources/business_inputs/README.md` 等清单。

3. 校准验收方案前端 URL。
   - 当前应按 HTTP 8443 验。
   - 若验收环境要求 HTTPS，必须先配置 Vite/反代/证书，而不是直接按文档访问。

4. 明确测试账号。
   - 浏览器当前卡在登录页。
   - 页面级验收需要 admin / budget_mgr / dept_mgr / viewer 等测试账号和密码，且要覆盖权限矩阵。

### P1 严重

1. 验收方案中“预算底稿 Excel 导入”需重定口径。
   - 不要恢复旧 `/api/budget-input/*`。
   - 将经营预算事实验证重点放到“机构及产品数据录入 -> BudgetDataWriter -> budget_data -> 跑批 -> 报表”。

2. 多年度对比需补数据口径说明。
   - `budget_2025.db` 当前 `budget_data` / `budget_summary` 为空。
   - 如果验多年度对比的来源是 `compare.db`，要把这个明确写成验收前置条件。

3. 智能预算模拟数值单位要做页面级 sanity check。
   - 过去此页面出现过 `万元` / `亿` 显示链路不一致风险。
   - 即使后端测试和 build 通过，也要看浏览器结果卡、可行方案、传导拆解、导出 Excel 的单位一致性。

4. 交付验收必须用干净包。
   - 当前工作区含 `.git`、依赖缓存、运行日志、archive 等，不是交付包。
   - 内部完整运行包必须包含 `apps/web/dist` 且只允许 `var/data` 作为 live 数据目录。

## 8. 建议验收路线

### 8.1 先做门禁修复

最低门禁：

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npx tsc -p apps/web/tsconfig.json --noEmit
npm --workspace apps/web run build
```

如果要做交付包验收，再用 packaging script 产出干净包后跑：

```bash
npm run verify:delivery
```

不要在含 `.git`、`node_modules`、`.venv`、`archive` 的开发工作区上把 `verify:delivery` 当作交付结论。

### 8.2 再做功能主线验收

优先顺序：

1. 登录与权限：管理员、录入用户、浏览用户。
2. 机构及产品：产品树维护、停用/删除保护、导航同步。
3. 机构及产品指标：公式、横纵汇总、唯一指标号码、运行引用同步。
4. 机构及产品数据录入：可编辑/公式锁定、保存草稿、确认同步、`BudgetDataWriter` 错误展示。
5. 预算事实刷新跑批：公式、rollup、summary、compare。
6. 预算展示报表：全行、分产品、单产品、版本槽位、导出。
7. 部门费用闭环：BI映射、费用执行明细导入、费用预测逻辑、部门费用预测、费用预算执行报表。
8. 多维分析：当前年度透视、多年度对比透视、透视图、导出。
9. 智能能力：Agent 只读查询、澄清、写入拒绝/确认；智能报告/PPT；智能预算模拟。
10. 退休入口：旧表、旧 API、旧前端入口、旧 driver、旧 product_type、旧 report_account。

### 8.3 每条业务链路要同时看三层证据

每个 P0/P1 验收项建议同时记录：

- 页面证据：8443 页面可见状态、关键数字、提示、导出文件。
- API/DB 证据：相关 endpoint 或 SQLite row count/关键 SQL。
- 自动化证据：pytest / Playwright / verifier 输出。

只看其中一层都不够。

## 9. Architecture deepening candidates

以下是本次按 `improve-codebase-architecture` 发现的 deepening opportunities。这里只列 candidate，不直接设计新 interface。

### 1. 运行指标身份写入 Module

Files：

- `apps/api/app/init_db.py`
- `apps/api/app/services/v03_metric_node_catalog.py`
- `apps/api/app/services/org_product_metric_runtime_sync.py`
- `apps/api/app/db_bootstrap/runtime_metric_tree.py`
- `apps/api/scripts/verify_current_database_inventory.py`

Problem：

当前 verifier 只允许极少数 Module 写 `data_account` / `data_account_metric_node` / `data_account_metric_binding`，但仍发现 `init_db.py` 与 `v03_metric_node_catalog.py` 直接写运行指标身份表。这让 **机构及产品指标体系** 的唯一主指标 interface 变 shallow：维护者需要跨多个文件理解哪些写法是合法修复、哪些是旧口径回流。

Solution：

把所有运行指标身份修复/清理动作收敛到一个深 Module，由它表达“哪些场景允许改变运行引用、哪些必须拒绝”。`init_db.py` 只调用这个 Module，不能内联写运行身份 SQL。

Benefits：

- Locality：指标身份写入规则集中，不会散落在启动、修复脚本和 catalog helper 里。
- Leverage：verifier、bootstrap、测试和未来 MySQL 迁移共享同一判断。
- Tests：测试 surface 可以变成“给定旧/新合同，Module 允许或拒绝哪些写入”，而不是 grep 多处 SQL。

### 2. FastAPI composition root Module

Files：

- `apps/api/app/main.py`
- `apps/api/app/routers/*`
- `apps/api/app/services/*`

Problem：

`main.py` 约 428 行，承担 settings、db pool、auth middleware、agent、smart report/PPT、刷新状态、预算跑批、导出、费用模块等大量 wiring。它的 interface 对维护者是 shallow：想改一个业务 Module 的启动依赖，需要同时理解多个 unrelated wiring。

Solution：

按业务主线把 router/service wiring 拆到少量 composition Module：认证系统、经营预算、部门费用、多维/智能、系统配置。`main.py` 只保留 app 创建和 include 这些组合 Module。

Benefits：

- Locality：某条业务主线的依赖注入集中。
- Leverage：新增 router 或替换 adapter 时不必碰全局组合根。
- Tests：可以对每个 composition Module 做 router 注册和依赖注入 smoke。

### 3. 机构及产品指标前端页面 Module

Files：

- `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx`
- `apps/web/src/lib/org-product/orgProductMetricApi.ts`
- `apps/web/src/lib/org-product/orgProductFormulaRefs.ts`
- `apps/web/src/lib/org-product/orgProductMetricCode.ts`

Problem：

`OrgProductMetricContent.tsx` 约 5194 行，是当前最大前端风险点。它承载指标表、公式导入、校验、保存刷新、UI 状态和业务规则。Deletion test：删除这个页面不会让复杂性消失，复杂性会在多个调用点重生，说明这里应该有深 Module，但现在 interface 太宽。

Solution：

按“表格展示模型、公式编辑/校验、Excel 公式导入、保存刷新命令、运行引用同步状态”拆出纯 view model 和 command Module，页面只编排交互。

Benefits：

- Locality：公式和唯一指标号码规则更容易测试。
- Leverage：Playwright 页面测试可以减少，更多规则可用纯 TS 测试覆盖。
- Tests：覆盖 MTR-002、MTR-006、MTR-007、MTR-B02、MTR-B03、MTR-B06 时会更稳定。

### 4. 验收方案与当前系统地图的同步 Module

Files：

- `预算管理系统_测试验收方案.md`
- `CONTEXT.md`
- `docs/development/current-system-map.md`
- `apps/web/src/app/workspaceCatalog.tsx`
- `apps/api/scripts/verify_worktree_organization.py`
- `apps/api/scripts/verify_current_database_inventory.py`

Problem：

验收方案有全量价值，但部分口径与当前系统地图不一致，例如 HTTPS 8443、经营预算 Excel 导入。当前缺少一个深 Module 或脚本把“验收项 -> 当前导航/API/DB/verifier”对齐，导致验收人员可能按退休入口测试，或者误把正确退休当功能缺失。

Solution：

维护一份验收映射表，按当前导航和 domain term 映射每个测试项，标注 current / retired / needs-test-data / package-only。再用脚本检查方案中的已知退休词和当前导航差异。

Benefits：

- Locality：验收口径偏差集中发现。
- Leverage：测试分配、bug 归因和上线阻断标准共享同一张图。
- Tests：可以把“退休模块不可恢复”从手工清单推进成自动化门禁。

### 5. 智能预算模拟单位与结果展示 Module

Files：

- `apps/web/src/app/components/budget/IntelligentBudgetSimulationContent.tsx`
- `apps/web/src/lib/budget/intelligentBudgetSimulationApi.ts`
- `apps/api/app/routers/intelligent_budget_simulation.py`
- `apps/api/app/services/intelligent_budget_*`

Problem：

智能预算模拟当前是验收方案中的智能能力项，过去页面级风险集中在结果卡、方案表、传导拆解和金额单位。`formatAmount` / backend 原始单位 / 导出单位若没有统一 interface，很容易出现后端测试通过但页面数字不可信。

Solution：

把“金额单位、目标约束、可行方案、传导拆解、导出字段”的 display contract 做成独立 Module，并对同一 payload 同时测试页面显示和导出。

Benefits：

- Locality：单位换算和可见文案集中。
- Leverage：结果卡、比较表、弹窗、导出 Excel 共享同一语义。
- Tests：IBS-002、IBS-003、IBS-005 和数值 sanity check 更可重复。

## 10. 下一步建议

建议先处理两条线：

1. 验收前置修复线：让 `verify_worktree_organization.py` 和 `verify_current_database_inventory.py` 变绿，校准验收方案 URL 和经营预算 Excel 导入口径。
2. 页面验收准备线：明确测试账号、准备 2025/2026/compare 数据说明、按导航树跑 P0/P1 页面验收并记录页面/API/DB 三层证据。

在这两条完成前，可以开始探索性测试和测试用例分配，但不建议给出“可正式验收通过”的结论。
