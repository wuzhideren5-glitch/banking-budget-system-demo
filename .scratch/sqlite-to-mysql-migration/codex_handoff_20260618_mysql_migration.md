# Codex Handoff - SQLite to MySQL Migration Fix

日期：2026-06-18  
工作区：`/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)`  
目标：继续修复“SQLite 重构到 MySQL 后项目崩溃”的问题，按原迁移计划把运行态业务链路切到 MySQL，并保留 SQLite 作为备份/测试 fallback。

## 1. 当前结论

本轮 Codex 已完成最后几个直接 `aiosqlite_compat` 残留模块的迁移处理，并跑通过主要验证门。

当前状态：

- 后端运行中：`http://127.0.0.1:8009`
- 前端运行中：`http://127.0.0.1:8443`
- 后端健康检查：`/api/health` 返回 `{"status":"ok"}`
- 全量测试：`967 passed, 43 warnings, 6 subtests passed`
- MySQL inventory：`failed_items: []`
- SQLite -> MySQL verify-only：
  - `common` 通过
  - `budget --year 2026` 通过
  - `compare` 通过
- `verify_worktree_organization.py` 通过
- `git diff --check` 通过
- 直接 `aiosqlite_compat / aiosqlite.connect` 残留：仅剩 `apps/api/app/core/aiosqlite_compat.py` 自身，不再出现在 `apps/api/app` 业务服务和 `apps/api/scripts` 中。

注意：我没有把长期 goal 标为 complete，因为还没有把“原始需求文档”逐条做最终验收矩阵；但从运行、测试、迁移校验角度，本轮崩点已实质性修复。

## 2. 本轮 Codex 直接改过的核心文件

### 2.1 `apps/api/app/services/smart_report_service.py`

处理目标：智能报告模块仍直接 `import app.core.aiosqlite_compat as aiosqlite`，运行态读写 `common.db / budget_YYYY.db` 时仍通过 SQLite 兼容层。

已做：

- 移除直接 `aiosqlite_compat` import。
- 增加本地 `_connect_db(path)`：
  - `settings.data_dir/common.db`
  - `settings.data_dir/budget_YYYY.db`
  - 以上路径走 MySQL pool。
  - 临时目录、测试库、非运行态文件路径走 sqlite3 fallback。
- 增加 `_mysql_sql()` 方言转换：
  - `?` -> `%s`
  - `ON CONFLICT(...) DO UPDATE` -> `ON DUPLICATE KEY UPDATE`
  - `excluded.col` -> `VALUES(col)`
  - `GROUP_CONCAT(x, ' / ')` -> `GROUP_CONCAT(x SEPARATOR ' / ')`
  - `||` 字段拼接改为 `CONCAT(...)`
- `_sum_budget_summary()` 中：
  - MySQL 运行态不再要求 `budget_YYYY.db` 文件存在。
  - MySQL 路径下不再执行 SQLite schema ensure。
- 定向验证：
  - `pytest apps/api/tests/chart/test_smart_report_service_catalog.py -q`
  - 结果：`4 passed`
- MySQL 只读探针通过：
  - `templates: 5`
  - `blueprints: 0`
  - `instances: 11`
  - `calc_metrics: 0`

### 2.2 `apps/api/app/services/budget_output_display_config.py`

处理目标：预算输出展示配置模块仍直接使用 `aiosqlite_compat`，且依赖 `aiosqlite.Row` 的行访问行为。

已做：

- 移除直接 `aiosqlite_compat` import。
- 增加本地 `_connect_db(path)` 双路径适配。
- 增加 `_Row`，保持 `row["column"]` 和 `row[0]` 都可用。
- 增加 MySQL 方言处理：
  - `?` -> `%s`
  - 字面量 `%` 转义，修复 aiomysql 对 `LIKE 'PRODUCT.%'` 的格式化误判。
  - `INSERT OR IGNORE` -> `INSERT IGNORE`
  - `ON CONFLICT(row_key) DO UPDATE` -> `ON DUPLICATE KEY UPDATE`
  - `excluded.col` -> `VALUES(col)`
  - `'org_product_runtime_ref:' || d.data_acct_code` -> `CONCAT(...)`
  - `PRAGMA foreign_keys` -> `SET FOREIGN_KEY_CHECKS`
  - `PRAGMA table_info(...)` -> `INFORMATION_SCHEMA.COLUMNS`
  - MySQL 下跳过 SQLite 的 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` schema ensure DDL。
- 删除 `db.row_factory = aiosqlite.Row` 等残留写法。
- 定向测试：
  - `pytest apps/api/tests/budget/test_budget_output_display_config.py -q`
  - 结果：`9 passed`
- MySQL 只读探针：
  - `load_budget_output_display_config_response()`
  - 结果：`items: 1049`，`candidates: 2332`

### 2.3 `apps/api/app/services/budget_output_display.py`

处理目标：预算输出展示主报表模块仍直接连接 SQLite 兼容层，并且用本地 `.db` 文件存在性判断年度预算库是否可读。

已做：

- 移除直接 `aiosqlite_compat` import。
- 增加本地 `_connect_db(path)` 双路径适配。
- 增加 `_Row`，保持 dict/index 双访问。
- 改用 `org_product_runtime_products_cte_for_db(db)`，按当前连接类型选择 SQLite/MySQL CTE。
- 增加 `_path_available(path)`：
  - MySQL 运行态路径即使本地 `.db` 文件不存在，也视为可读。
  - 修复 `budget_YYYY.db` 迁移后因为文件判断而跳过年度预算数据的问题。
- 改造以下路径判断：
  - `_choose_database_for_year()`
  - `_fetch_versions_for_budget_file()`
  - `_build_display_version_specs()`
- 删除遗留调试打印：
  - `[BUDGET_DISPLAY] ...`
  - `[DEBUG] ...`
- 定向测试：
  - `pytest apps/api/tests/budget/test_budget_output_display_config.py apps/api/tests/budget/test_budget_display_structure.py -q`
  - 结果：`12 passed`
- MySQL 主链路探针：
  - 调用 `build_budget_output_display_report(year=2026, ...)`
  - 结果：
    - `years: [2026, 2025]`
    - `versions: 4`
    - `total_rows: 54`
    - `product_tree: 1`
    - `product_overview_blocks: 21`
    - `product_detail_blocks: 13`

### 2.4 `apps/api/scripts/migrate_sqlite_to_mysql.py`

处理目标：`--verify-only --only common` 因 `user_sessions` 行数多 1 报失败。

调查结果：

- SQLite `user_sessions`：495 行。
- MySQL `user_sessions`：496 行。
- MySQL 比 SQLite 多 1 条 session。
- SQLite 没有缺失 MySQL 中已有的源记录。
- 这是运行中系统产生的会话数据，不是迁移缺失。

已做：

- 将 `user_sessions` 加入 `TARGET_SUPERSET_TABLES`。
- 语义：MySQL 目标允许包含运行期新增记录，但仍校验所有 SQLite 源记录在 MySQL 中存在且内容一致。

验证：

- `migrate_sqlite_to_mysql.py --verify-only --only common`
- 结果：通过。
- 输出中 `user_sessions: source=495 target=496 ... OK`。

## 3. 本轮验证命令与结果

以下命令均在工作区根目录执行。

### 3.1 直接残留扫描

```bash
rg -n "app\.core\.aiosqlite_compat|aiosqlite\.connect|aiosqlite\.Connection|import aiosqlite" apps/api/app apps/api/scripts --glob '!apps/api/app/core/aiosqlite_compat.py'
```

结果：无输出。

说明：`apps/api/app/core/aiosqlite_compat.py` 自身仍存在，这是兼容层文件；业务服务和脚本已无直接残留。

### 3.2 定向测试

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests/chart/test_smart_report_service_catalog.py -q
```

结果：`4 passed`

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests/budget/test_budget_output_display_config.py -q
```

结果：`9 passed`

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests/budget/test_budget_output_display_config.py apps/api/tests/budget/test_budget_display_structure.py -q
```

结果：`12 passed`

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests/scripts/test_verify_current_database_inventory_script.py -q
```

结果：`40 passed`

### 3.3 全量测试

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q --maxfail=5
```

结果：

```text
967 passed, 43 warnings, 6 subtests passed in 41.30s
```

### 3.4 MySQL inventory

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_mysql_inventory.py --json
```

结果：

```text
passed: 198
failed: 0
warnings: ["Unexpected table: 'current_fact'"]
failed_items: []
```

说明：`current_fact` 是额外表 warning，不影响当前门禁。

### 3.5 SQLite -> MySQL verify-only

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only common
```

结果：通过。

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only budget --year 2026
```

结果：通过。

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only compare
```

结果：通过。

### 3.6 工作区组织与 diff 检查

```bash
find apps/api/app apps/api/scripts apps/api/tests -name '__pycache__' -type d -prune -exec rm -rf {} +
rm -rf .pytest_cache apps/api/.pytest_cache
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
git diff --check
```

结果：

```text
worktree_organization=ok
```

`git diff --check` 无输出，表示通过。

### 3.7 服务健康

```bash
curl -sS --max-time 5 http://127.0.0.1:8009/api/health
```

结果：

```json
{"status":"ok"}
```

```bash
curl -sS --max-time 5 -I http://127.0.0.1:8443/
```

结果：`HTTP/1.1 200 OK`

### 3.8 HTTP 接口注意

直接无 cookie curl：

```bash
curl -i http://127.0.0.1:8009/api/budget-output/display-config
curl -i http://127.0.0.1:8009/api/budget-output/display-report?year=2026
```

返回 `401 Unauthorized`，这是未登录场景的预期行为。不能用无登录 curl 的空解析结果判断接口数据为空。

离线服务层 MySQL 探针已证明预算输出主链路可从 MySQL 返回数据。后续如果要做 UI 级验证，应该用浏览器已登录 session 或先调用登录接口获取 cookie。

## 4. 后续 agent 接手要特别注意

### 4.1 不要误判 `user_sessions`

`user_sessions` 是运行期表。当前 MySQL 比 SQLite 多 1 条 session 是正常的运行时新增，不是迁移缺失。

脚本规则已改为：MySQL 目标允许是 SQLite 源的超集，但源记录必须全部存在且 hash 一致。

### 4.2 不要把无登录 HTTP 401 当成业务失败

预算输出接口受登录态保护。无 cookie curl 返回：

```json
{"detail":"未登录，请先登录"}
```

这是正常行为。要验证接口数据，请使用登录后的 cookie，或在服务层做 MySQL 探针。

### 4.3 不要恢复 `aiosqlite_compat` 直接 import

本轮已清掉业务服务里的直接残留。后续如果新增迁移，应继续使用：

- MySQL pool
- 明确的 path/dialect 判断
- 或统一的 DatabaseGateway/adapter

不要重新写：

```python
import app.core.aiosqlite_compat as aiosqlite
async with aiosqlite.connect(...)
```

### 4.4 当前 adapter 有重复，后续可抽象

`smart_report_service.py`、`budget_output_display_config.py`、`budget_output_display.py` 目前各自有本地 `_connect_db/_Row/_mysql_sql` 适配代码。

这是为了快速收敛崩点和降低交叉修改风险。后续可以抽到共享模块，例如：

```text
apps/api/app/core/mysql_sqlite_adapter.py
```

但抽象前必须保留以下行为：

- `row["column"]` 和 `row[0]` 双访问。
- MySQL 路径识别必须排除 `tempfile.gettempdir()` 下的测试库。
- `PRAGMA table_info(...)` 要映射到 `INFORMATION_SCHEMA.COLUMNS`。
- 字面量 `%` 必须转义，避免 aiomysql 格式化误判。
- `?` 参数位必须转换成 `%s`。
- MySQL 运行态不要依赖 `.db` 文件存在。

### 4.5 工作区很脏，不要随手 revert

当前 worktree 包含大量 Qoder/前序迁移改动。本轮 Codex 直接关注的核心文件是：

```text
apps/api/app/services/smart_report_service.py
apps/api/app/services/budget_output_display_config.py
apps/api/app/services/budget_output_display.py
apps/api/scripts/migrate_sqlite_to_mysql.py
.scratch/sqlite-to-mysql-migration/codex_handoff_20260618_mysql_migration.md
```

不要用 `git reset --hard`、`git checkout --` 等命令回滚用户或 Qoder 的其他改动。

## 5. 建议下一步

1. 做一次“原始需求文档 vs 当前实现”的逐项验收矩阵。
   - 参考目录：
     - `.scratch/sqlite-to-mysql-migration/prd.md`
     - `.scratch/sqlite-to-mysql-migration/plan_sqlite_to_mysql.md`
     - `.scratch/sqlite-to-mysql-migration/architecture.md`
     - `.scratch/sqlite-to-mysql-migration/qa-report.md`
   - 输出建议：
     - `.scratch/sqlite-to-mysql-migration/final_acceptance_matrix_20260618.md`

2. 登录态 UI 验证预算输出页面。
   - 重点页面：
     - 预算输出展示配置
     - 预算输出展示报表
     - 智能报告模板/实例列表
   - 不要只用未登录 curl。

3. 可选重构 adapter。
   - 把三个服务里的 `_connect_db/_Row/_mysql_sql` 抽到共享模块。
   - 抽象后必须重新跑：
     - 全量 pytest
     - common/budget/compare verify-only
     - MySQL inventory
     - 预算输出主链路 MySQL 探针

4. 再次确认是否可以把长期 goal 标为 complete。
   - 需要逐项证明：
     - 原需求文档要求已覆盖。
     - SQLite 备份仍保留。
     - MySQL 为运行态主库。
     - 核心业务页面和迁移脚本可用。
     - 无业务服务直接依赖 `aiosqlite_compat`。

## 6. 快速复验命令

后续 agent 可从以下最小命令开始：

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q --maxfail=5
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_mysql_inventory.py --json
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only common
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only budget --year 2026
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only compare
find apps/api/app apps/api/scripts apps/api/tests -name '__pycache__' -type d -prune -exec rm -rf {} +
rm -rf .pytest_cache apps/api/.pytest_cache
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
git diff --check
```

服务健康：

```bash
curl -sS --max-time 5 http://127.0.0.1:8009/api/health
curl -sS --max-time 5 -I http://127.0.0.1:8443/
```

预算输出服务层 MySQL 探针：

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python - <<'PY'
import asyncio
from app.core.config import settings
from app.core.database import init_pool, get_pool
from app.core.db_paths import budget_db_path
from app.services.budget_output_display import build_budget_output_display_report

async def editable_context_provider():
    return budget_db_path(2026), 2026, None

async def main():
    pool = init_pool(settings)
    await pool.init()
    try:
        report = await build_budget_output_display_report(
            year=2026,
            budget_version_id=None,
            forecast_version_ids=None,
            product_codes=None,
            editable_context_provider=editable_context_provider,
            data_dir=settings.data_dir,
        )
        print({
            "years": report.available_years[:5],
            "versions": len(report.versions),
            "total_rows": len(report.total_rows),
            "product_tree": len(report.product_tree),
            "selected_products": len(report.selected_products),
            "product_overview_blocks": len(report.product_overview_blocks),
            "product_detail_blocks": len(report.product_detail_blocks),
        })
    finally:
        await get_pool().close()

asyncio.run(main())
PY
```

预期输出形态：

```text
{
  "years": [2026, 2025],
  "versions": 4,
  "total_rows": 54,
  "product_tree": 1,
  "selected_products": 0,
  "product_overview_blocks": 21,
  "product_detail_blocks": 13
}
```
