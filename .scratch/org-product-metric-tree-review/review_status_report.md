# 机构及产品列表模块 — Comments 整改状态检视报告

检视时间：2026-06-16
Comments 来源：`.scratch/org-product-tree-review/comments.md`（6项）+ `.scratch/org-product-metric-tree-review/comments.md`（5项）
检视方法：逐一比对源代码 + 运行两套测试 + 查询当前 DB 状态

---

## 一、机构及产品树（org-product-tree-review，6 项）

### 问题 1：后端缺少树合同强校验 — **未改**

代码中不存在 `validate_org_product_tree_contract()` 函数。保存接口 `/api/org-product-tree/save-refresh` 仍只通过 `_flatten_org_product_tree()` 校验空值和重复码。评审要求的根节点必须 AAA/level0、层级合法性、代码格式、核心节点保护这些强校验全都没有实现。

**建议：**
1. 在后端建立 `validate_org_product_tree_contract(tree)` 函数，保存前必须通过。
2. 校验至少包含：唯一根（AAA/微众集团/level0）、合法层级（AA/AB 只能 level1、level2 挂 level1、level3 挂 level2）、代码格式（产品码 = 父机构码 + 两位数字）、核心节点保护。
3. 给保存接口增加失败用例测试：非法根、level3 直接挂 level1、重复代码、空名称、非法产品码都应 400。

### 问题 2：删除/改码不做下游引用检查 — **未改**

不存在 `/api/org-product-tree/save-preview` 影响分析接口。前端 `handleDeleteCurrent()` 仍然是简单 confirm dialog，不展示下游指标、录入快照、输出快照、预算事实的影响数量。

**建议：**
1. 保存前增加影响分析接口 `/api/org-product-tree/save-preview`。
2. 如果删除/改码节点命中已有指标、录入快照、输出快照或预算事实，默认阻断保存。
3. UI 上在删除确认前展示影响清单：产品数、指标数、录入版本数、预算事实行数。
4. 对"只改名称不改代码"放行；对"改代码/删除"走严格审批或二次确认。

### 问题 3：sync 函数命名误导 / 无物化表 — **未改**

`sync_org_product_runtime_catalog_from_tree()` 函数名没改，下游仍依赖 `org_product_runtime_products_cte()` 动态展开 JSON。没有物化运行表、没有版本号、没有健康检查。

**建议：**
1. 如果坚持 CTE 动态展开，把函数名改为 `validate_org_product_tree_and_drop_retired_product_type()`。
2. 如果业务上需要稳定运行清单，物化 `org_product_runtime_product` 表，保存树时事务内重建。
3. 增加 `/api/org-product-tree/db-snapshot` 的合同校验和健康检查。

### 问题 4：Excel 导入缺少审计 summary — **未改**

导入接口 `/api/org-product-tree/import-excel` 仍只返回 `{"tree": ...}`。没有节点统计、跳过行、错误行、重复码检测、根节点迁移信息。

**建议：**
1. 导入接口返回 `summary`：节点数、各层级数量、跳过行、错误行、根节点信息。
2. 旧格式导入统一迁移成 AAA 根，不只依赖前端 `prepareOrgProductTreeFromStorage()`。
3. 导入预览阶段就做后端强合同校验，不要等保存时才失败。

### 问题 5：数据录入/预测输出依赖前端事件 — **未改**

`OrgProductDataEntryContent.tsx` 和 `OrgProductForecastOutputContent.tsx` 仍依赖 `org-product-tree-saved` window event 联动。没有服务端版本校验，`entity_code` 失效也不会拦截保存。

**建议：**
1. 在 `org_product_tree_snapshot` 中维护 `updated_at`，前端每次保存数据录入/输出前校验树版本是否变化。
2. 如果当前选择的 `entity_code` 已不在树中，页面必须显式提示并阻止保存。
3. 数据录入和预测输出页面在关键提交前重新拉取树快照，不要只依赖 window event。

### 问题 6：agent_product_intent 测试失败 — **未改**

运行结果仍然是 **4 failed**：
- `test_catalog_digest_sources_metrics_from_org_product_metric_code`
- `test_metric_binding_lookup_expands_parent_product_scope_from_org_product_tree`
- `test_metric_binding_lookup_ignores_orphan_runtime_bindings`
- `test_metric_lookup_ignores_orphan_runtime_nodes`

`_lookup_metric_nodes()` 和 `_bindings_for_metric_nodes()` 返回空列表，产品树范围扩展与指标运行引用的合同未对齐。

**建议：**
1. 先修指标运行引用确认逻辑，再恢复这些测试。
2. 给产品树范围扩展单独加测试：选择 A 时必须包含 A01-A05，选择 AA 时必须包含 AA 下全部机构/产品。
3. AI 查询不要读取旧 `org_product_metric_table` 作为确认来源，应统一读取 runtime tree 中已启用的 org-product metric refs。

### 机构及产品树小结：6 项全部未动。

---

## 二、机构及产品指标树（org-product-metric-tree-review，5 项）

### 问题 1：退休表 `org_product_metric_table` 仍存在 — **部分改了**

**已做的：**
- `_ensure_metrics_table()` 已改为 no-op（不再创建该表）。
- `sync_existing_org_product_metric_tables()` 迁移函数已写好（读取旧行 → 同步运行树 → DROP TABLE）。

**没做的：**
- 该表**未加入** `RETIRED_TABLES` 清单（`retired_deletion.py` 第 11-38 行）。
- 当前库仍有 **46 行**数据。
- 迁移函数在启动 bootstrap 流程中未被调用。
- `verify_current_database_inventory.py` 未将表的存在本身作为失败条件。

**建议：**
1. 把 `org_product_metric_table` 加入 `RETIRED_TABLES`，或在启动 bootstrap 中强制调用 `sync_existing_org_product_metric_tables()` 后删除。
2. `verify_current_database_inventory.py` 把物理 `org_product_metric_table` 存在本身作为失败条件。

### 问题 2：`functional_group_code` 复用为表名 — **未改**

`org_product_metric_runtime_snapshot.py` 第 137 行仍直接 `table_name = _clean(row["functional_group_code"])`。无白名单映射，"01"、"05"、"14" 等数字码仍会被当作伪表名分组。没有新增独立字段（如 `metric_table_name`）来承载指标表名。

当前库 `functional_group_code` 分布（大量非表名值）：
```
业务状况表|608
业务支出评估|494
05|414
14|138
01|112
15|105
```

**建议：**
1. 不要继续复用 `functional_group_code` 同时表示"指标功能族"和"指标表名"。
2. 在 `data_account_metric_node` 增加独立字段（如 `metric_table_name`）承载指标表名。
3. 短期不改 schema 的话，至少在 snapshot 层建立白名单映射：只有 catalog 中存在的表名才能作为 table_name。
4. 增加测试：构造 `functional_group_code='05'` 和 `functional_group_code='业务状况表'` 混合数据，验证 `/db-snapshot` 不产生伪表。

### 问题 3：`_node_name()` 父节点命名不一致 — **已改**

`_node_name()` 已改为对中间 GROUP 节点允许以 code 兜底命名（兼容模式）。代码注释（第 405-407 行）明确写了策略选择："严格校验（缺失报错）放在导入预览层，不在同步层阻断。"

`_all_node_codes()` 自动生成隐式父码，`_node_name()` 现在能兼容处理这些节点。两者之间的不一致已解决。

### 问题 4：`allow_manual_entry` 列 schema 不一致 — **代码已改，库未落地**

**已做的：**
- `schemas.py` 规范 CREATE TABLE 包含 `allow_manual_entry`、`value_type`、`budget_formula`、`actual_formula`、`annual_agg_rule`。
- `runtime_metric_tree.py` 的 `_ensure_metric_node_v02_columns()` 迁移逻辑已写好（ALTER TABLE 自动添加缺失列）。
- `_assert_current_metric_tree_physical_schema()` 在迁移后验证精确列集合。

**没做的：**
- 当前 `common.db` 的 `data_account_metric_node` 实际只有 16 列，缺少上述运行字段。
- 说明 bootstrap 尚未在当前库上执行过。

**建议：**
1. 在当前库上执行一次完整 bootstrap（`ensure_databases()`），落地字段迁移。
2. `/db-snapshot` 不要把 DB schema 错误悄悄吞掉后让前端回退旧缓存，应暴露为明确错误。

### 问题 5：`data_account_metric_binding` 是 table 还是 view — **规范代码已改，测试未统一**

**已做的：**
- `schemas.py` 已定义为 VIEW（`CREATE VIEW IF NOT EXISTS data_account_metric_binding AS ...`）。
- bootstrap 的 `_ensure_metric_binding_view()` 会强制 DROP TABLE 再 CREATE VIEW。
- `_assert_current_metric_tree_physical_schema()` 明确要求必须是 view。
- `verify_current_database_inventory.py` 对物理 table 报 `binding_physical_table_retired` 违规。

**没做的：**
以下 6 个测试文件仍用 `CREATE TABLE data_account_metric_binding`，与规范 VIEW 合同不一致：
- `test_budget_output_display_config.py`（第 48、113、354、414 行）
- `test_budget_actual_batch_service.py`（第 35 行）
- `test_expense_forecast_metric_sources.py`（第 26 行）
- `test_budget_summary_export_service.py`（第 125 行）
- `test_budget_summary_rebuild.py`（第 51、232 行）

当前库中 `data_account_metric_binding` 仍是物理 table。

**建议：**
1. 更新上述 6 个测试文件，统一使用 VIEW 合同或统一的 test fixture。
2. 在当前库上执行 bootstrap，让 `_ensure_metric_binding_view()` 把物理 table 转为 VIEW。

### 机构及产品指标树小结：1 项已改好、2 项部分改了、1 项代码改了库没落地、1 项未改。

---

## 三、测试运行结果

| 测试套件 | 通过 | 失败 |
|---------|------|------|
| 套件 1（org-product-tree） | 23 | **4** |
| 套件 2（metric-tree） | 70 | **9** |
| **合计** | **93** | **13** |

套件 1 的 4 个失败全在 `test_agent_product_intent_catalog.py`，是产品树范围扩展与指标运行引用未对齐。

套件 2 的 9 个失败分布：
- `test_org_product_metric_runtime_refs.py`（2 个）：canonical expense merge 改名逻辑不完整，"常规人力" 未重命名为 "直接费用"。
- `test_verify_current_database_inventory_script.py`（7 个）：inventory 脚本校验规则与测试预期不一致（如报 `binding_physical_table_retired` 而测试期望更具体的违规类型）。

当前 DB 状态：
- `org_product_metric_table` 仍存在（46 行）
- `data_account_metric_binding` 仍为物理 table
- `data_account_metric_node` 只有 16 列，缺少运行字段
- `product_type` 不存在（正确）
- `org_product_tree_snapshot` 存在且数据正常（21 节点，层级正确）

---

## 四、总体结论

**两个模块的 comments 还没改完，还不能作为主线交付。**

### 完全没动的（7 项，需要虾从头做）

1. **后端树合同强校验** — 需要新增 `validate_org_product_tree_contract()`
2. **删除/改码影响分析** — 需要新增 save-preview 接口 + 前端影响清单 UI
3. **sync 函数命名/物化** — 改名或物化运行表
4. **Excel 导入审计 summary** — 导入接口需要返回行级统计
5. **前端服务端版本联动** — 需要 updated_at 校验 + entity_code 失效拦截
6. **agent_product_intent 测试修复** — 需要对齐产品树范围与指标运行引用合同
7. **`functional_group_code` 语义拆分** — 需要独立字段或白名单映射

### 改了一半需要收尾的（3 项）

1. **`org_product_metric_table` 退休治理** — 加入 `RETIRED_TABLES` 并在启动时调用迁移函数
2. **`data_account_metric_binding` 测试统一** — 6 个测试文件从 CREATE TABLE 改为 VIEW 合同
3. **`data_account_metric_node` schema 落地** — 需要在当前库上执行一次完整 bootstrap

### 已经改好的（2 项）

1. **`_node_name()` 兼容模式** — 中间 GROUP 节点允许 code 兜底
2. **bootstrap schema 定义和迁移逻辑** — 代码层面已就绪

### 建议执行顺序

1. 先修 DB contract：在当前库执行完整 bootstrap（落地 schema 迁移 + 退休表清理 + binding 转 VIEW）
2. 修语义字段：把"指标表名"和"指标功能族"拆开
3. 修后端树合同校验 + 删除影响分析 + Excel 导入审计
4. 修 agent_product_intent 测试 + 统一测试文件 VIEW 合同
5. 修 sync 函数命名 + 前端版本联动
6. 最后做一次浏览器验证 + 全量测试
