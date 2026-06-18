# SQLite → MySQL 迁移 QA 测试报告（终版）

> **QA 工程师**: Edward（严过关）| **日期**: 2026-05-07 | **轮次**: Round 2 (终轮)

---

## 1. 测试概要

| 指标 | Round 1 | Round 2 | 变化 |
|------|---------|---------|------|
| 总文件数 | 230 | 230 | — |
| `py_compile` 通过 | 230/230 | 230/230 | ✅ |
| aiosqlite.connect 残留 | 92 处 | **0 处** | ✅ 清零 |
| ON CONFLICT 残留 | 7 处 | **0 处** | ✅ 清零 |
| sqlite_master 残留 | 28 处 | **0 处** | ✅ 清零 |
| PRAGMA 残留 | 7 处 | **0 处** | ✅ 清零 |
| ATTACH DATABASE 残留 | 0 | **0** | ✅ |
| GLOB 残留 | 0 | **0** | ✅ |
| AUTOINCREMENT 残留 | 6 处 | **0 处** | ✅ 清零 |
| `?` 占位符残留 | ~50 处 | **73 处** | ❌ 新增/未修复 |
| 路由判定 | Send To: Engineer | **Known Issues** | — |

---

## 2. 编译完整性验证 ✅

| 项目 | 结果 |
|------|------|
| `python -m py_compile` | **230/230 全部通过** |
| 语法错误 | 0 |

---

## 3. 残留模式回归扫描

### 3.1 aiosqlite.connect — ✅ 全部清零

```
aiosqlite.connect → 0 处（排除迁移脚本/内省工具）
```

Round 1 的 28 个漏迁文件全部修复。所有业务代码现已使用 `pool.acquire()`。

### 3.2 ON CONFLICT — ✅ 全部清零

```
ON CONFLICT → 0 处
```

`business_cost_income_commands.py`、`business_cost_income_import.py`、
`expense_forecast_write_commands.py`、`annual_aggregation.py` 均已替换。

### 3.3 sqlite_master — ✅ 全部清零

```
sqlite_master → 0 处（排除 db_introspection.py 文档注释）
```

13 个文件、28 处 sqlite_master 查询已全部替换为 `INFORMATION_SCHEMA.TABLES` 或 `db_introspection.table_exists()`。

### 3.4 PRAGMA — ✅ 全部清零

```
PRAGMA → 0 处（排除迁移脚本和内省工具）
```

### 3.5 ATTACH DATABASE — ✅ 始终清零

### 3.6 GLOB — ✅ 始终清零

### 3.7 INTEGER PRIMARY KEY AUTOINCREMENT — ✅ 全部清零

| 文件 | Round 1 | Round 2 |
|------|---------|---------|
| `db_bootstrap/business_cost_income.py` | 4 处 | **0** ✅ |
| `routers/org_product_helpers.py` | 1 处 | **0** ✅ |
| `services/global_refresh_status.py` | 1 处 | **0** ✅ |

---

## 4. 随机抽检：5 个原问题文件连接方式验证 ✅

| 文件 | aiosqlite.connect | pool.acquire | import aiomysql | sqlite_master | PRAGMA | ON CONFLICT |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| `services/business_cost_income_commands.py` | 0 | 24 | ✅ | 0 | 0 | 0 |
| `services/expense_forecast_cell_commands.py` | 0 | 2 | ✅ | 0 | 0 | 0 |
| `services/budget_output_display.py` | 0 | 16 | ✅ | 0 | 0 | 0 |
| `services/budget_summary_rebuild.py` | 0 | 2 | ✅ | 0 | 0 | 0 |
| `services/expense_budget_execution_budget_source.py` | 0 | 12 | ✅ | 0 | 0 | 0 |

---

## 5. Round 1 Appendix A 关键文件验证 ✅

| 文件 | 检查项 | 结果 |
|------|--------|------|
| `core/database.py` | 8 个 async 方法 | ✅ |
| `core/db_introspection.py` | 9 处 INFORMATION_SCHEMA | ✅ |
| `core/config.py` | 8 个 MYSQL 参数 | ✅ |
| `main.py` | 2 处 init_pool 调用 | ✅ |
| `db_bootstrap/schemas.py` | 35 AUTO_INCREMENT, 0 AUTOINCREMENT, 13 budget_year | ✅ |
| `budget_data_writer.py` | 2 ON DUPLICATE KEY UPDATE, 7 get_pool, 0 ON CONFLICT | ✅ |
| `pyproject.toml` | aiomysql ✅, PyMySQL ✅, aiosqlite 已移除 ✅ | ✅ |

---

## 6. 遗留问题：`?` 参数占位符未全部替换 ⚠️

### 问题描述

MySQL 驱动（aiomysql / PyMySQL）要求使用 `%s` 作为参数占位符，而非 SQLite 的 `?`。Round 1 发现的 ~50 处 `?` 未完全修复，Round 2 扫描发现 **73 处**残留。

### 影响范围

| 目录 | 实例数 | 文件数 |
|------|--------|--------|
| `services/` | 56 | 23 |
| `routers/` | 17 | 3 |
| **合计** | **73** | **26** |

### 受影响文件清单

**services/ (23 个文件)**

| # | 文件 | 估计 `?` 数 |
|---|------|:--:|
| 1 | `services/business_cost_income_commands.py` | 6 |
| 2 | `services/business_cost_income_import.py` | 5+ |
| 3 | `services/budget_output_display.py` | 2 |
| 4 | `services/budget_output_display_config.py` | 6+ |
| 5 | `services/expense_forecast_write_commands.py` | 4 |
| 6 | `services/expense_budget_execution_budget_source.py` | 2 |
| 7 | `services/expense_budget_entry_store.py` | 2+ |
| 8 | `services/annual_aggregation.py` | 3+ |
| 9 | `services/auth_sessions.py` | 2 |
| 10 | `services/agent_compare_version.py` | 1+ |
| 11 | `services/agent_pivot_suggestion.py` | 1+ |
| 12 | `services/bi_department_mapping.py` | 1+ |
| 13 | `services/chart_data.py` | 1+ |
| 14 | `services/expense_actual_import_apply.py` | 1+ |
| 15 | `services/expense_forecast_data_context.py` | 5+ |
| 16 | `services/expense_forecast_metric_sources.py` | 1+ |
| 17 | `services/expense_forecast_rule_read_model.py` | 1+ |
| 18 | `services/expense_master_data.py` | 1+ |
| 19 | `services/global_refresh_status.py` | 2+ |
| 20 | `services/metric_tree_rollups.py` | 2+ |
| 21 | `services/org_product_metric_runtime_sync.py` | 1+ |
| 22 | `services/pivot_aggregate.py` | 1+ |
| 23 | `services/system_versions.py` | 1+ |

**routers/ (3 个文件)**

| # | 文件 | 估计 `?` 数 |
|---|------|:--:|
| 1 | `routers/org_product_data_entry.py` | 5+ |
| 2 | `routers/org_product_helpers.py` | 8+ |
| 3 | `routers/org_product_output.py` | 4+ |

### 风险等级

**高** — 使用 aiomysql 执行含 `?` 占位符的 SQL 时，aiomysql 不会将其识别为参数占位符，导致：
- 参数未被正确绑定（`TypeError` 或参数数量不匹配）
- 或者 `?` 被当作字面量传递，产生 SQL 语法错误

### 示例（`business_cost_income_commands.py:468-474`）

```python
pool = get_pool()
async with pool.acquire() as db:
    cur = await db.execute(
        """
        SELECT COALESCE(MAX(sort_order), -1) + 1
        FROM business_cost_income_item
        WHERE product_code = ? AND section = ? AND parent_id IS ?
        """,
        (normalized_product, section, parent_id),
    )
```

应修改为：
```python
WHERE product_code = %s AND section = %s AND parent_id IS %s
```

---

## 7. 路由判定

### 判定结果：**Known Issues**（输出终版报告）

```
Round 1 → Send To: Engineer  →  28 个文件修复完成
Round 2 → 6 大模式全部清零, 但 ? 占位符未彻底修复
         → 已达最大轮次 (2/2), 输出报告标注遗留问题
```

| 类别 | 状态 | 说明 |
|------|:--:|------|
| py_compile | ✅ | 230/230 |
| aiosqlite.connect 残留 | ✅ | 0 |
| ON CONFLICT 残留 | ✅ | 0 |
| sqlite_master 残留 | ✅ | 0 |
| PRAGMA 残留 | ✅ | 0 |
| AUTOINCREMENT 残留 | ✅ | 0 |
| GLOB / ATTACH | ✅ | 0 |
| 连接方式（pool.acquire） | ✅ | 已验证 5/5 |
| **`?` 占位符** | ⚠️ | 73 处 / 26 个文件 |
| db_paths.py 残留引用 | ℹ️ | 4 处（低优先级） |

---

## 8. 建议修复方案

1. **全局查找替换 `?` → `%s`**：对 26 个受影响文件执行正则替换，将 SQL 语句中的 `= ?`、`, ?`、`(?)` 等模式替换为对应的 `%s`
2. **`db_paths.py` 清理**：移除 4 个残留引用后删除文件
3. **修复后建议 Run Round 3**：针对 `?` → `%s` 替换做专项扫描确认

---

> **总结**: 迁移核心工作（驱动替换、DDL 重写、连接池、Schema 内省）已完成且质量良好。唯一遗留问题是 73 处 `?` 占位符需要替换为 `%s`，建议工程师优先修复后进行一次专项验证。
