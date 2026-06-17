# 产品及指标树模块代码评审 Comments

评审时间：2026-06-16  
评审对象：机构及产品、机构及产品指标树、运行指标树同步链路  
评审范围：`apps/api/app/routers/org_product_metrics.py`、`apps/api/app/services/org_product_metric_runtime_sync.py`、`apps/api/app/services/org_product_metric_runtime_snapshot.py`、`apps/web/src/app/components/OrgProductMetricContent.tsx`、`apps/api/app/db_bootstrap/retired_deletion.py`、`apps/api/scripts/verify_current_database_inventory.py`、当前 `apps/var/data/common.db`

## 总体结论

本轮“产品及指标树重新梳理”还不能直接作为主线交付。核心问题不是页面能否展示，而是主数据语义仍然混杂：旧 JSON 指标表、运行指标树、指标功能族、指标表名这几个概念在代码和数据库里没有完全切开。

当前最需要优先修的是三类阻断问题：

1. 已退休的 `org_product_metric_table` 仍以物理表存在，并且有 46 行 JSON payload。
2. `data_account_metric_node.functional_group_code` 被后端当成“指标表名”读取，但当前库里大量值是 `01`、`05`、`14` 等功能族/本地段，导致指标树被拆成伪表。
3. 运行树同步函数现在要求所有中间父节点必须显式命名，但测试和旧导入负载仍存在只提供叶子节点的路径，导致关键回归测试失败。

## 检视板块 1：主数据存储边界

### 问题 1：退休表 `org_product_metric_table` 仍然存在且有数据

代码中已经把 `_ensure_metrics_table` 改成 no-op，说明设计上不希望再创建 `org_product_metric_table`：

- `apps/api/app/routers/org_product_metrics.py`：`_ensure_metrics_table()` 注释表明 `org_product_metric_table` 是 `data_account_metric_node` 的重复 JSON 投影。
- `apps/api/app/services/org_product_metric_runtime_sync.py`：`sync_existing_org_product_metric_tables()` 会把旧 JSON 表同步进运行树后 `DROP TABLE org_product_metric_table`。

但当前数据库检查结果显示：

```text
org_product_metric_table_count|46
metric_node_count|2912
table_catalog_count|12
```

并且旧表中仍有 A01、A02、A03、A04、A05、AA 等 payload：

```text
A01|业务状况表|78432
A02|业务状况表|72850
AA|业务状况表|31565
AA|损益表|11701
```

### 影响

这会让系统重新进入“双主数据”状态：一份在 `data_account_metric_node`，一份在 `org_product_metric_table.payload_json`。后续只要某个导入、校验、脚本或旧接口读取旧表，就可能把重复节点、旧字段或旧层级重新带回页面。

### 建议

1. 把 `org_product_metric_table` 明确加入退休表治理，或者在启动 bootstrap 中强制调用 `sync_existing_org_product_metric_tables()` 后删除。
2. `apps/api/app/db_bootstrap/retired_deletion.py` 的 `RETIRED_TABLES` 当前没有 `org_product_metric_table`，建议补上或单独建立“迁移后必须不存在”的 guard。
3. `verify_current_database_inventory.py` 不应只检查旧 JSON 内容，也应把物理 `org_product_metric_table` 存在本身作为失败条件。

## 检视板块 2：指标表名 vs 指标功能族

### 问题 2：`functional_group_code` 被当作表名使用，但库里多数不是表名

`apps/api/app/services/org_product_metric_runtime_snapshot.py` 在还原 `/api/org-product-metrics/db-snapshot` 时直接使用：

```python
table_name = _clean(row["functional_group_code"])
key = (product_code, table_name)
```

注释也写着 `functional_group_code now carries the visible metric table name`。但是当前库里 `functional_group_code` 的分布显示，它并不是稳定的业务表名：

```text
业务状况表|608
业务支出评估|494
05|414
14|138
01|112
15|105
16|104
19|84
17|71
18|66
10|65
```

也就是说，`db-snapshot` 会把一个产品的指标拆成很多张名为 `01`、`05`、`14` 的伪表，而不是稳定落在 `业务状况表`、`损益表`、`资产负债表（余额）` 等指标表。

### 影响

前端加载逻辑在 `OrgProductMetricContent.tsx` 中优先使用 `/api/org-product-metrics/db-snapshot`，只有 DB 没数据时才回退 localStorage。因此如果后端 snapshot 分组错，前端会忠实展示错误结构。

相关前端逻辑：

- `apps/web/src/app/components/OrgProductMetricContent.tsx`：初始化时并发读取 `bootstrap`、`table-catalog`、`db-snapshot`。
- 同文件中 `storageFallback = hasMetricTables(fromDb) ? {} : migratedStored ?? {}`，表示 DB 有数据时本地缓存不会覆盖 DB。

### 建议

1. 不要继续复用 `functional_group_code` 同时表示“指标功能族”和“指标表名”。
2. 建议在 `data_account_metric_node` 增加或明确使用独立字段承载指标表名，例如 `metric_table_name` / `table_name`。
3. 如果短期不能改 schema，至少在 runtime snapshot 层建立白名单映射：只有 catalog 中存在的表名才能作为 table_name，否则按导入来源或默认表进行归类，并把异常计入校验报告。
4. 增加测试：构造 `functional_group_code='05'` 和 `functional_group_code='业务状况表'` 混合数据，验证 `/db-snapshot` 不产生 `05` 这种伪表。

## 检视板块 3：运行树同步与父节点命名

### 问题 3：同步函数要求隐式父节点必须已有名称，现有回归测试大量失败

执行：

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q apps/api/test_org_product_metric_runtime_refs.py apps/api/test_verify_current_database_inventory_script.py
```

结果：

```text
15 failed, 64 passed
```

代表性失败：

```text
OrgProductMetricRuntimeSyncError: 指标节点 A01.01 缺少名称。所有节点必须在指标树定义中显式命名，不允许自动推导。
OrgProductMetricRuntimeSyncError: 指标节点 A01.05 缺少名称。所有节点必须在指标树定义中显式命名，不允许自动推导。
OrgProductMetricRuntimeSyncError: 指标节点 B01.05 缺少名称。所有节点必须在指标树定义中显式命名，不允许自动推导。
```

触发点在 `apps/api/app/services/org_product_metric_runtime_sync.py` 的 `_node_name()`。现在 `_all_node_codes()` 会自动补齐父节点，但 `_node_name()` 对补齐出来的父节点不允许兜底命名。

### 影响

如果导入 Excel 或旧 payload 只包含叶子指标，保存时会因为父节点缺失名称失败。更严重的是，这会造成“同一批树，有的来源能保存，有的来源不能保存”的不稳定状态。

### 建议

有两个方向，需要明确取舍：

1. 严格模式：导入/保存前必须展开完整父链，所有父节点必须来自 Excel 或现有运行树，缺失即返回可读错误，并在导入预览阶段提示到具体 code。
2. 兼容模式：允许根据已有 runtime tree、catalog 或旧 payload 补齐父节点名，但补齐来源必须可追踪，不能静默用 code 当 name。

当前代码和测试不一致。建议先决定模式，再同步修测试。以业务交付稳定性看，建议采用“严格模式 + 导入预览报错”，避免自动生成假父节点。

## 检视板块 4：数据库 schema 与代码假设不一致

### 问题 4：runtime snapshot 查询假设存在 `allow_manual_entry`，当前库查询失败

尝试直接调用 `load_org_product_metric_table_rows_from_runtime_tree(conn)` 时失败：

```text
sqlite3.OperationalError: no such column: allow_manual_entry
```

这说明当前 `apps/var/data/common.db` 的 `data_account_metric_node` schema 与服务代码假设不一致。服务查询字段包括：

```sql
allow_manual_entry, value_type, budget_formula, actual_formula
```

但当前库未完成对应迁移或启动 bootstrap 尚未落地。

### 影响

`/api/org-product-metrics/db-snapshot` 在真实当前库上可能直接 500。前端虽然 catch 了错误并返回空 entities，但这会导致页面回退到 seed/localStorage，掩盖真实 DB 读取失败。

### 建议

1. 在启动 `ensure_databases()` 中确保 `data_account_metric_node` 补齐 `allow_manual_entry`、`value_type`、`budget_formula`、`actual_formula` 等运行字段。
2. `/db-snapshot` 不建议悄悄失败后让前端回退，本模块应把 DB schema 错误暴露为明确错误，避免用户看到旧缓存还以为保存成功。
3. 增加一个集成测试：用当前迁移后的 `common.db` schema 调用 `load_org_product_metric_table_rows_from_runtime_tree()`，确保不依赖测试内存库的简化 schema。

## 检视板块 5：门禁与测试

### 问题 5：测试已经暴露回归，但当前状态没有被拦住

本次重点测试失败集中在：

- `apps/api/test_org_product_metric_runtime_refs.py`
- `apps/api/test_verify_current_database_inventory_script.py`

失败方向包括：

- 同步只给叶子节点时无法补齐父节点名称。
- canonical expense merge 不能正确改名/去重。
- inventory 脚本把 `data_account_metric_binding` 物理表视为退休，但部分测试仍按物理表合同断言。
- `org_product_metric_table` 存在时 runtime ref 校验路径与当前“binding 必须是 view”的门禁互相抢先，导致期望错误不再出现。

### 建议

1. 先统一 `data_account_metric_binding` 的最终形态：如果必须是 view，所有测试和文档都应改为 view 合同；如果仍允许物理表，门禁不能直接判死。
2. 把 `org_product_metric_table` 是否允许存在作为单独最高优先级测试，不要和 runtime ref materialization 测试混在一起。
3. 在发布包校验里加入以下断言：

```sql
SELECT type, name
FROM sqlite_master
WHERE name IN (
  'org_product_metric_table',
  'data_account',
  'data_account_metric_binding',
  'data_account_metric_node'
);
```

期望：

- `org_product_metric_table` 不存在。
- `data_account_metric_node` 是 table。
- `data_account`、`data_account_metric_binding` 的最终形态必须与架构合同一致。

## 建议修复顺序

1. 先修 DB contract：删除/迁移 `org_product_metric_table`，补齐 `data_account_metric_node` schema，明确 `data_account_metric_binding` 是 table 还是 view。
2. 再修语义字段：把“指标表名”和“指标功能族”拆开，不能再共用 `functional_group_code`。
3. 再修同步规则：确定隐式父节点的处理策略，并让导入预览、保存接口、测试一致。
4. 最后修前端：前端不要在 `/db-snapshot` schema 失败时静默回退旧缓存，应提示“DB 指标树读取失败”。

## 本次验证命令

```bash
sqlite3 apps/var/data/common.db ".tables" | tr ' ' '\n' | rg 'org_product|data_account'
sqlite3 apps/var/data/common.db "SELECT 'org_product_metric_table_count', COUNT(*) FROM org_product_metric_table;"
sqlite3 apps/var/data/common.db "SELECT functional_group_code, COUNT(*) FROM data_account_metric_node WHERE is_active=1 AND COALESCE(product_code,'')<>'' AND node_code<>product_code GROUP BY functional_group_code ORDER BY COUNT(*) DESC LIMIT 30;"
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q apps/api/test_org_product_metric_runtime_refs.py apps/api/test_verify_current_database_inventory_script.py
```

## 评审结论

不建议现在把这次“产品及指标树重新梳理”标为完成。它已经朝“运行树唯一主线”方向走了，但当前实现仍有旧表残留、字段语义复用、schema 不一致和回归测试失败。建议先按上述顺序修完，再做一次浏览器页面验证和 DB inventory 验证。
