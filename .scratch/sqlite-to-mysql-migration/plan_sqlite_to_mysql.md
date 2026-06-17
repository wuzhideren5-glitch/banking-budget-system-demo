# SQLite 迁移 MySQL 重构方案

## 现状概要

| 数据库 | 大小 | 表数 | 用途 |
|--------|------|------|------|
| common.db | 37 MB | 45 | 系统主库（用户、指标树、组织产品） |
| budget_2026.db | 140 MB | 10 | 2026预算数据 |
| budget_2025.db | 4.7 MB | 10 | 2025预算数据 |
| compare.db | 418 MB | 5 | 预算对比分析 |

- 连接方式：异步 `aiosqlite` + 同步 `sqlite3`，无 ORM
- 需改写的 SQLite 特有语法：PRAGMA (1209处)、GLOB (346处)、INSERT OR IGNORE (9处)、json_extract (17处)

---

## Task 1：MySQL 环境搭建与连接层改造

**目标**：建立 MySQL 数据库实例，替换连接驱动

### 1.1 MySQL 数据库创建
- 本地 MySQL 创建 3 个 database：`banking_budget_common`、`banking_budget_2026`、`banking_budget_compare`
- 字符集 `utf8mb4`，排序规则 `utf8mb4_unicode_ci`

### 1.2 依赖替换
- `pyproject.toml` / `requirements.txt`：移除 `aiosqlite`，新增 `aiomysql`（异步驱动）和 `PyMySQL`（同步驱动）
- 可选添加连接池库

### 1.3 配置层改造
- `apps/api/app/core/config.py`：新增 MySQL 连接参数（host、port、user、password、database）
- `.env` / `.env.example`：添加 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB_COMMON`、`MYSQL_DB_BUDGET`、`MYSQL_DB_COMPARE`
- 创建连接池工厂函数替代当前的 `aiosqlite.connect(path)`

### 涉及文件
- `apps/api/pyproject.toml`、`apps/api/requirements.txt`
- `apps/api/app/core/config.py`
- `apps/api/.env`、`apps/api/.env.example`
- 新建 `apps/api/app/core/database.py`（连接池管理）

---

## Task 2：Schema DDL 改写

**目标**：将所有 CREATE TABLE 语句从 SQLite 语法转为 MySQL 语法

### 2.1 数据类型映射
- `INTEGER PRIMARY KEY` → `INT PRIMARY KEY AUTO_INCREMENT`
- `TEXT` (短文本) → `VARCHAR(255)` 或 `VARCHAR(512)`
- `TEXT` (长文本/JSON) → `TEXT` 或 `LONGTEXT`
- `REAL` → `DOUBLE`
- `BLOB` → `LONGBLOB`
- 布尔字段 `INTEGER DEFAULT 0` → `TINYINT(1) DEFAULT 0`

### 2.2 约束改写
- 移除所有 `PRAGMA foreign_keys = ON`（MySQL 默认启用 InnoDB 外键）
- `CREATE TABLE IF NOT EXISTS` 保持不变（MySQL 兼容）
- `DROP TABLE IF EXISTS` 保持不变

### 2.3 初始化逻辑改造
- `apps/api/app/init_db.py`：`executescript()` 改为逐条执行（MySQL 不支持批量脚本）
- `apps/api/app/db_bootstrap/schemas.py`：改写 COMMON_SCHEMA、BUDGET_SCHEMA、COMPARE_SCHEMA

### 涉及文件
- `apps/api/app/db_bootstrap/schemas.py`（732 行，核心改写）
- `apps/api/app/db_bootstrap/runtime_metric_tree.py`
- `apps/api/app/init_db.py`

---

## Task 3：SQL 语法适配

**目标**：将代码中的 SQLite 特有语法改写为 MySQL 兼容语法

### 3.1 GLOB → REGEXP
- `NOT GLOB '[0-9]*'` → `NOT REGEXP '^[0-9]'`
- `GLOB '*keyword*'` → `LIKE '%keyword%'`
- 主要集中在 `runtime_metric_tree.py`

### 3.2 INSERT 语法
- `INSERT OR IGNORE` → `INSERT IGNORE`
- `INSERT OR REPLACE` → `REPLACE INTO`

### 3.3 PRAGMA 清理
- 删除所有 `PRAGMA foreign_keys = ON`（15+ 处）
- `PRAGMA table_info(table_name)` → `SHOW COLUMNS FROM table_name` 或 `SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?`（40+ 处）

### 3.4 JSON 函数
- `json_extract(col, '$.key')` → `JSON_EXTRACT(col, '$.key')`（MySQL 5.7+ 原生支持，语法相同）

### 3.5 GROUP_CONCAT
- SQLite `GROUP_CONCAT(col, ',')` → MySQL `GROUP_CONCAT(col SEPARATOR ',')`

### 3.6 参数占位符
- SQLite 使用 `?` 占位符 → MySQL (PyMySQL/aiomysql) 使用 `%s`
- 这是全局改写，涉及所有 SQL 查询

### 涉及文件
- 所有 `apps/api/app/services/*.py`
- 所有 `apps/api/app/routers/*.py`
- `apps/api/app/db_bootstrap/runtime_metric_tree.py`

---

## Task 4：路由层驱动替换

**目标**：将 41 个 router 文件中的 `aiosqlite` 调用替换为 `aiomysql` 连接池

### 4.1 连接获取模式改写
```python
# 旧（SQLite）
async with aiosqlite.connect(db_path) as db:
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()

# 新（MySQL）
async with get_mysql_pool().acquire() as conn:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
```

### 4.2 事务处理
- SQLite 的隐式事务 → MySQL 显式 `await conn.begin()` / `await conn.commit()`
- 确保 `db.commit()` 调用对应 MySQL 的 commit

### 涉及文件
- `apps/api/app/routers/` 下所有 41 个路由文件
- `apps/api/app/services/` 下所有服务文件

---

## Task 5：数据迁移

**目标**：将现有 SQLite 数据导入 MySQL

### 5.1 迁移脚本
- 新建 `apps/api/scripts/migrate_sqlite_to_mysql.py`
- 逐表读取 SQLite 数据 → 批量 INSERT 到 MySQL
- 处理数据类型转换（NULL、布尔、日期格式）
- 支持断点续传（记录已迁移表）

### 5.2 数据验证
- 迁移后对比每张表的行数
- 抽样校验关键字段数据一致性

---

## Task 6：测试验证与清理

**目标**：确保全部测试通过，清理 SQLite 残留

### 6.1 测试更新
- 测试中的 SQLite 连接改为 MySQL 测试库
- 或使用 MySQL 测试容器（pytest-mysql）
- 运行全量测试

### 6.2 清理
- 移除 `aiosqlite` 依赖
- 更新文档说明新的数据库配置
- `.env.example` 更新

---

## 执行顺序与依赖

```
Task 1 (环境+连接层) → Task 2 (Schema DDL) → Task 3 (SQL语法) → Task 4 (路由驱动) → Task 5 (数据迁移) → Task 6 (测试验证)
```

严格串行：每个 Task 依赖前一个的完成。

---

## 前置条件

- 本地已安装 MySQL 8.0+
- 已创建 MySQL 用户并授权
- Python 环境可安装 `aiomysql` 和 `PyMySQL`

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| 参数占位符全局替换遗漏 | 全文搜索 `?` 占位符，逐文件确认 |
| PRAGMA table_info 改写量大 | 封装统一的 `get_table_columns()` 工具函数 |
| 数据迁移丢失 | 迁移后自动行数校验 |
| 并发性能差异 | MySQL 连接池 + InnoDB 行锁天然优于 SQLite |

---

# Codex 补充：可执行迁移方案与验收门禁

> 本节补充原计划遗漏的架构决策、双后端策略、跨库设计、测试门禁和回滚要求。  
> 在本节补齐并评审通过前，不建议直接开始 Task 1 的驱动替换。

## 0. 迁移原则

1. **禁止大爆炸式替换**：迁移期必须保留 SQLite 后端，新增 MySQL 后端，通过配置切换或双跑验证逐步迁移。
2. **先抽象，再改 SQL**：不能在 41 个 router 和所有 service 中直接批量替换 `aiosqlite.connect()`；必须先建立统一数据库访问层。
3. **先定数据模型，再迁移数据**：年度库、主库、对比库在 MySQL 下的映射必须先定稿，否则后续 SQL、权限、备份和迁移脚本都会返工。
4. **迁移不等于清理**：`aiosqlite`、SQLite 脚本和 `var/data/*.db` 只能在 MySQL 全量验收、回滚演练和交付门禁通过后再移除。
5. **业务口径优先于表行数**：行数校验只是最低门槛，必须加入关键业务口径校验，包括预算汇总、透视汇总、机构产品指标运行引用、费用预测规则、智能报告/PPT配置。

## 1. 必须先做的架构决策

### 1.1 MySQL 数据库布局

当前 SQLite 布局不是固定 3 个库，而是：

- `common.db`：主数据、用户、审计、机构产品指标、智能报告/PPT配置。
- `budget_2025.db`、`budget_2026.db`、未来 `budget_{year}.db`：年度预算事实和年度私有读模型。
- `compare.db`：多年度对比读模型。

MySQL 迁移前必须从下列方案中选定一个，并写入设计决策：

| 方案 | 描述 | 优点 | 风险 |
| --- | --- | --- | --- |
| A. 单 database + 年度字段 | 所有年度表合并到一个 `banking_budget`，年度通过 `budget_year` 字段区分 | 查询和事务最简单，部署成本低 | 需要重构所有年度表主键、唯一约束和查询条件 |
| B. 多 database | `banking_budget_common`、`banking_budget_budget_2025`、`banking_budget_budget_2026`、`banking_budget_compare` | 最贴近现有文件模型 | 跨库 join、权限、迁移、备份、动态年度创建更复杂 |
| C. 单 database + 年度表前缀 | 如 `budget_2026_budget_data`、`budget_2025_budget_data` | 保留年度隔离，少用跨 database 权限 | 表名动态化复杂，SQL 生成风险高 |

**建议优先评审 A 或 B。** 如果继续保留“年度分库”语义，必须补充 `create_budget_year_database(year)` 和 `list_budget_years()` 的 MySQL 版本，用来替代当前 `list_budget_database_files()`。

### 1.2 跨库引用与查询

当前存在 SQLite `ATTACH` 和跨文件逻辑引用，例如年度库读取 `common.db.period`、Agent 查询同时使用 common/budget/compare。MySQL 下必须明确：

- common 与 budget 是否允许跨 database join。
- 跨库查询使用同一 MySQL 连接还是多个连接后在应用层合并。
- 年度预算写入和 common 审计是否需要同事务。
- `period`、`data_account`、`org_product_tree_snapshot` 等 common 字典是否在年度库内冗余快照。

验收要求：

- 所有 `ATTACH DATABASE` / `DETACH DATABASE` 调用都有 MySQL 替代设计。
- 所有跨库逻辑引用在文档中列清楚，并有对应测试。

### 1.3 视图、触发器与派生表

当前 schema 依赖 SQLite view / trigger：

- `data_account` 由 `data_account_metric_node` 派生。
- `data_account_metric_binding` 由指标树派生。
- `budget_data` 有更新时间 trigger。

MySQL 迁移前必须逐项决定：

| 对象 | 当前 SQLite 行为 | MySQL 方案 |
| --- | --- | --- |
| `data_account` view | 从指标树派生运行引用 | 保留 MySQL VIEW，或改为物化表并由保存链路刷新 |
| `data_account_metric_binding` view | 从指标树派生绑定 | 保留 MySQL VIEW，或改为物化表 |
| `budget_data` trigger | insert/update 时维护 `update_time` | MySQL trigger，或应用层统一写入 |

验收要求：

- `verify_current_database_inventory.py` 的 MySQL 版本仍能验证上述合同。
- 如果改为物化表，必须补充重建脚本、幂等测试和异常恢复策略。

## 2. 数据访问层改造

### 2.1 新增统一 Database Gateway

新增：

- `apps/api/app/core/database.py`
- `apps/api/app/core/sql_dialect.py`
- `apps/api/app/core/db_introspection.py`

目标：

- 封装连接创建、连接池、事务、游标 row 类型、参数占位符。
- 统一提供 `execute`、`fetchone`、`fetchall`、`executemany`、`transaction`。
- 提供 SQLite / MySQL 双实现。
- 提供同步和异步两套接口，或明确哪些初始化脚本继续使用同步驱动。

建议接口草案：

```python
class DatabaseGateway:
    async def fetch_all(self, db: DatabaseName, sql: Sql, params: Sequence[Any] = ()) -> list[Row]: ...
    async def fetch_one(self, db: DatabaseName, sql: Sql, params: Sequence[Any] = ()) -> Row | None: ...
    async def execute(self, db: DatabaseName, sql: Sql, params: Sequence[Any] = ()) -> int: ...
    async def execute_many(self, db: DatabaseName, sql: Sql, rows: Sequence[Sequence[Any]]) -> int: ...
    async def transaction(self, dbs: Sequence[DatabaseName] = ()): ...
```

### 2.2 SQL Dialect Adapter

不能只靠全文替换 `?` 为 `%s`。必须建立 dialect adapter：

| 能力 | SQLite | MySQL |
| --- | --- | --- |
| 参数占位符 | `?` | `%s` |
| upsert | `ON CONFLICT (...) DO UPDATE` | `ON DUPLICATE KEY UPDATE` |
| ignore insert | `INSERT OR IGNORE` | `INSERT IGNORE` 或 `ON DUPLICATE KEY UPDATE` |
| replace | `INSERT OR REPLACE` | 谨慎使用 `REPLACE INTO`，优先 `ON DUPLICATE KEY UPDATE` |
| last id | `last_insert_rowid()` / `cursor.lastrowid` | `cursor.lastrowid` |
| changed rows | `changes()` | cursor rowcount，注意 MySQL matched/changed 差异 |
| metadata | `PRAGMA table_info` / `sqlite_master` | `INFORMATION_SCHEMA` |
| concat/search | `||` / `INSTR` | `CONCAT()` / `LOCATE()` |
| attach | `ATTACH DATABASE` | 跨 database 全限定表名或应用层合并 |

验收要求：

- 禁止业务模块直接拼接 MySQL/SQLite 专有 SQL，除非集中在 dialect adapter。
- 所有 `PRAGMA`、`sqlite_master`、`rowid`、`ATTACH`、`last_insert_rowid()` 都必须有迁移清单和替代实现。

## 3. Schema 迁移补充要求

### 3.1 逐表 Schema Mapping

原计划中的全局类型映射不够安全。必须新建：

- `.scratch/sqlite-to-mysql-migration/schema_mapping.md`

每张表至少记录：

- SQLite 表名。
- MySQL 表名。
- 主键策略。
- 唯一约束。
- 外键。
- 索引。
- TEXT 字段类型：`VARCHAR(n)` / `TEXT` / `MEDIUMTEXT` / `LONGTEXT`。
- JSON 字段是否使用 MySQL `JSON` 类型。
- 是否为 view / trigger / 派生表。
- 是否参与年度库或 compare 库。

### 3.2 TEXT / JSON 字段不得一刀切

以下字段倾向使用 `LONGTEXT` 或 `JSON`，不能改成 `VARCHAR(255)`：

- `payload_json`
- `config_json`
- `basis_json`
- `formula`
- `before_data` / `after_data`
- 智能报告/PPT模板配置字段
- 机构产品树、指标树、数据录入快照

### 3.3 CHECK 约束与 MySQL 版本

MySQL 8.0.16+ 才真正执行 CHECK。需要：

- 固定 MySQL 最低版本。
- 对关键 CHECK 补充应用层校验。
- 在迁移验证中检测 CHECK 是否实际生效。

## 4. 数据迁移设计补充

### 4.1 迁移脚本必须支持 dry-run 和幂等

`migrate_sqlite_to_mysql.py` 必须支持：

- `--dry-run`
- `--only common|budget|compare|year`
- `--year 2025 --year 2026`
- `--truncate-target`
- `--resume`
- `--verify-only`
- `--report var/output/sqlite_to_mysql_migration_<timestamp>.md`

### 4.2 数据一致性校验

最低校验：

- 每张表行数一致。
- 主键集合一致。
- 关键表字段 hash 一致。
- NULL / 空字符串 / 0 的差异报告。
- 中文字符、emoji、长 JSON 可读。

关键业务校验：

- `verify_current_database_inventory.py` 的 MySQL 版本全绿。
- 机构产品指标 `data_account` / `data_account_metric_node` / `data_account_metric_binding` 运行引用一致。
- `budget_data`、`budget_summary`、`budget_pivot_aggregate` 按当前版本重建后与迁移前关键口径一致。
- `compare_summary` 行数与关键聚合一致。
- 智能报告、PPT、Agent 查询至少跑一条 smoke。

### 4.3 双跑对账

上线前必须双跑：

1. SQLite 读当前 `var/data`。
2. MySQL 读迁移结果。
3. 对同一组 API 请求比较响应 JSON。

建议覆盖 API：

- `/api/version-snapshot`
- `/api/system/databases`
- `/api/org-product-tree/db-snapshot`
- `/api/org-product-metrics/bootstrap`
- `/api/org-product-metrics/db-snapshot`
- `/api/org-product-data-entry/versions`
- `/api/org-product-output/run`
- `/api/budget-output/display-report`
- `/api/budget-summary/aggregate`
- `/api/compare-summary/aggregate`
- `/api/expense-forecast/meta`
- `/api/agent/chat` 的只读查询 smoke

## 5. 测试策略补充

### 5.1 测试分层

| 层级 | 后端 | 目标 |
| --- | --- | --- |
| Unit | SQLite in-memory 或 fake gateway | 保留快速逻辑测试 |
| Contract | SQLite + MySQL 双跑 | 验证 repository/gateway 行为一致 |
| Integration | MySQL test container | 验证真实 MySQL DDL、事务、字符集、锁 |
| Migration | SQLite fixture -> MySQL | 验证数据迁移和对账 |
| E2E | MySQL 后端 + 前端 | 验证关键页面和导入/导出 |

### 5.2 必须新增的测试

- SQL dialect adapter 单测。
- `DatabaseGateway` 事务提交/回滚测试。
- MySQL schema 初始化测试。
- SQLite -> MySQL 迁移 fixture 测试。
- 年度库动态创建/发现测试。
- 跨库 join 或应用层合并测试。
- `verify_current_database_inventory_mysql.py` 或统一 inventory verifier。
- 关键 API 双后端响应对账测试。

### 5.3 验收命令

迁移完成不得只跑全量 pytest；至少需要：

```bash
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile apps/api/app apps/api/scripts
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python apps/api/scripts/verify_worktree_organization.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npm run build
npx tsc -p apps/web/tsconfig.json --noEmit
pytest -q apps/api/tests
pytest -q apps/api/tests/mysql
python apps/api/scripts/migrate_sqlite_to_mysql.py --dry-run --verify-only
python apps/api/scripts/mysql_sqlite_api_diff.py --scenario smoke
```

## 6. 执行顺序修订

原计划的串行顺序需要改为：

```text
Phase 0 决策与盘点
  -> Phase 1 DB Gateway + Dialect Adapter
  -> Phase 2 MySQL Schema Mapping + MySQL 初始化
  -> Phase 3 逐模块 SQL 迁移（双后端测试）
  -> Phase 4 数据迁移脚本 + 对账
  -> Phase 5 MySQL 灰度运行
  -> Phase 6 切换默认后端
  -> Phase 7 移除 SQLite 依赖与归档旧 DB
```

### Phase 0：决策与盘点

- 选定 MySQL 数据库布局。
- 写 `schema_mapping.md`。
- 写跨库引用替代方案。
- 盘点所有 SQLite 特性：`PRAGMA`、`sqlite_master`、`rowid`、`ATTACH`、trigger、view、`ON CONFLICT`、`last_insert_rowid()`、`changes()`。

### Phase 1：DB Gateway + Dialect Adapter

- 新增统一 DB 访问层。
- 保持默认后端为 SQLite。
- 新代码不得再直接调用 `aiosqlite.connect()` 或 `sqlite3.connect()`，除迁移/验证脚本外。

### Phase 2：MySQL Schema

- 生成 MySQL DDL。
- 在 MySQL test database 初始化。
- 验证表、索引、view、trigger、约束。

### Phase 3：逐模块迁移

建议顺序：

1. system/user/session/operation_log
2. org_product tree/metric/data_entry/output
3. budget_data writer + budget_summary
4. compare summary
5. expense forecast/execution
6. smart report/PPT/agent

每个模块完成标准：

- SQLite 测试仍过。
- MySQL contract 测试过。
- API diff smoke 过。

### Phase 4：数据迁移与对账

- 迁移 common。
- 迁移所有 budget year。
- 迁移 compare。
- 输出迁移报告。

### Phase 5：灰度运行

- 配置 `DATABASE_BACKEND=mysql`。
- 跑启动、页面 smoke、导入导出 smoke。
- 保留 SQLite 数据作为回滚源。

### Phase 6：默认切换

- 默认后端改为 MySQL。
- SQLite 后端仍保留至少一个版本周期。

### Phase 7：清理

只有满足以下条件才允许移除 SQLite：

- MySQL 运行至少一轮完整验收。
- 回滚演练通过。
- 所有交付包不再依赖 `var/data/*.db`。
- 文档和运维脚本已更新。

## 7. 回滚方案

必须补充：

- 切换前冻结 SQLite 快照，存放 `var/data/backups/sqlite_to_mysql_<timestamp>/`。
- MySQL 迁移过程只读源 SQLite，不修改源库。
- 切换后保留 SQLite 只读回滚窗口。
- 若 MySQL 验证失败，配置改回 `DATABASE_BACKEND=sqlite`，并清理未完成的 MySQL 写入。

## 8. 计划验收标准

该迁移计划补齐后，才算“可执行”：

- [ ] MySQL 数据库布局已决策。
- [ ] 跨库查询替代方案已写明。
- [ ] `schema_mapping.md` 已逐表列出。
- [ ] DB Gateway 和 SQL Dialect Adapter 设计已评审。
- [ ] 双后端测试策略已落到具体测试文件。
- [ ] 迁移脚本参数、dry-run、verify-only、报告格式已定义。
- [ ] API diff smoke 场景已列出。
- [ ] 回滚方案已定义。
- [ ] 不再承诺早期移除 `aiosqlite`，而是以双后端稳定后再移除。

## 9. 当前计划结论

原计划可作为方向草稿，但不能作为直接实施计划。  
补齐本节后，建议先开一个小型 prototype 分支，只迁移 `users/user_sessions/operation_log` 三类低耦合表，验证 Gateway、Dialect、MySQL schema、迁移脚本、API diff 和回滚链路，再扩大到机构产品和预算事实主链路。
