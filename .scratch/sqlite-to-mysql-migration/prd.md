# 银行 AI 预算管理系统 — 数据库 SQLite → MySQL 迁移 PRD

## 1. 项目信息

| 项 | 内容 |
|---|------|
| 语言 | 中文 |
| 技术栈 | Python FastAPI + aiomysql/PyMySQL + MySQL 8.0+ |
| 项目名称 | `sqlite_to_mysql_migration` |
| 原始需求 | 将预算管理系统数据库从 4 个 SQLite 文件迁移至 1 个 MySQL 8.0+ 实例 |

### 当前现状

| 数据库文件 | 大小 | 表数 | 用途 |
|-----------|------|------|------|
| `common.db` | 37 MB | 45 | 系统主库（用户、指标树、机构产品、审计等） |
| `budget_2025.db` | 4.7 MB | 10 | 2025 年度预算数据 |
| `budget_2026.db` | 140 MB | 10 | 2026 年度预算数据 |
| `compare.db` | 418 MB | 5 | 预算对比分析 |

- **连接方式**：异步 `aiosqlite`（路由/服务层）+ 同步 `sqlite3`（初始化脚本），纯 raw SQL，无 ORM
- **代码规模**：100+ 文件分散使用 `aiosqlite.connect(path)`，41 个路由文件
- **SQLite 特有语法分布**：PRAGMA（1200+ 处）、GLOB（346 处）、`INSERT OR IGNORE`（9 处）、`json_extract`（17 处）、参数占位符 `?` 全局使用

---

## 2. 产品定义

### 2.1 产品目标

| # | 目标 | 成功标准 |
|---|------|---------|
| G1 | **数据库引擎切换**：将全部 SQLite 数据平稳迁移至 MySQL 8.0+，系统功能无回归 | 全部现有 API 通过回归测试；关键业务页面可正常操作 |
| G2 | **数据库布局简化**：4 文件 → 1 database（`banking_budget`），通过 `budget_year` 字段区分年度 | 所有跨年度/跨模块查询不再依赖 ATTACH，能在单 database 内完成 |
| G3 | **SQL 方言统一**：消除全部 SQLite 特有语法（PRAGMA、GLOB、`?` 占位符等），代码库中 SQL 均为 MySQL 兼容 | 全文搜索无残留 `PRAGMA`、`GLOB`、`sqlite_master`、`ATTACH` 关键字 |

### 2.2 用户故事

| # | 用户故事 | 验收条件 |
|---|---------|---------|
| US1 | **作为系统管理员**，我希望能用一套 MySQL 连接配置启动系统，不再需要管理 4 个分散的 SQLite 文件 | `.env` 中仅需配置 MySQL 连接参数，系统启动自动连接 MySQL |
| US2 | **作为预算管理员**，我希望在年度预算录入页面（机构及产品数据录入）能正常读写 2025/2026 年预算数据，迁移后数据不丢失、不错误 | 录入、保存、公式重算功能与迁移前一致；关键业务口径数值一致 |
| US3 | **作为报表查看者**，我希望预算展示报表（全行总表/分产品概览/单产品明细）和预算对比分析报表迁移后结果与迁移前一致 | 相同筛选条件下，报表数值、行数、排序一致 |
| US4 | **作为开发者**，我希望迁移后的代码不再依赖 `aiosqlite`，统一使用 MySQL 驱动，且能正常运行全部测试 | `aiosqlite` 从依赖中移除；全量测试通过 |
| US5 | **作为运维人员**，我希望有清晰的迁移脚本，支持一键执行、断点续传和迁移后数据校验 | `migrate_sqlite_to_mysql.py` 支持 `--dry-run`、`--resume`、`--verify-only` |

---

## 3. 技术规范

### 3.1 需求池

#### P0 — 必须完成（阻塞上线）

| ID | 需求 | 说明 |
|----|------|------|
| P0-1 | MySQL 数据库创建 | 单 database `banking_budget`，字符集 `utf8mb4`，排序规则 `utf8mb4_unicode_ci` |
| P0-2 | 连接层改造 | 移除 `aiosqlite`/`sqlite3`，新增 `aiomysql`（异步）+ `PyMySQL`（同步），实现连接池管理 |
| P0-3 | Schema DDL 改写 | 全部 CREATE TABLE 从 SQLite 语法转 MySQL：类型映射（`INTEGER PK` → `INT AUTO_INCREMENT`、`REAL` → `DOUBLE`、布尔 `INTEGER` → `TINYINT(1)`）、CHECK 约束保留（MySQL 8.0.16+ 支持）、移除全部 PRAGMA |
| P0-4 | 年度表合并 | 年度表增加 `budget_year` 列，重构主键和唯一约束使其包含 `budget_year`；`common` 和 `compare` 表直接合并到 `banking_budget` |
| P0-5 | 参数占位符全局替换 | 所有 SQL 中 `?` → `%s`（涉及 100+ 文件） |
| P0-6 | SQLite 特有语法改写 | PRAGMA 全部删除/用 SHOW COLUMNS 替代；GLOB → REGEXP/LIKE；`INSERT OR IGNORE` → `INSERT IGNORE`；`INSERT OR REPLACE` → `ON DUPLICATE KEY UPDATE`；`json_extract` → `JSON_EXTRACT`；`GROUP_CONCAT` 语法适配；`||` → `CONCAT()` |
| P0-7 | 路由层驱动替换 | 41 个 router 文件中 `aiosqlite.connect(path)` 替换为 MySQL 连接池获取 |
| P0-8 | 数据迁移脚本 | 逐 SQLite 表读取 → MySQL 批量 INSERT；处理 NULL/布尔/日期类型转换；支持 `--dry-run`、`--resume`、`--verify-only` |
| P0-9 | 数据一致性校验 | 迁移后逐表行数对比 + 主键集合对比 + 关键字段 hash 对比 + NULL/空字符串差异报告 |
| P0-10 | 测试全量通过 | pytest 全量通过（测试库改为 MySQL） |

#### P1 — 重要（上线前完成）

| ID | 需求 | 说明 |
|----|------|------|
| P1-1 | 视图/触发器改写 | `data_account` VIEW、`data_account_metric_binding` VIEW、`budget_data` trigger 转为 MySQL 兼容写法或应用层维护 |
| P1-2 | 跨库引用消除 | 所有 `ATTACH DATABASE` / `DETACH DATABASE` 调用移除；跨库逻辑改为 MySQL 跨 database 全限定表名或应用层合并（视合并为单 database 后大部分自然消除） |
| P1-3 | 关键业务口径校验 | `budget_data`、`budget_summary`、`budget_pivot_aggregate`、`compare_summary` 按当前版本重建后与迁移前一致 |
| P1-4 | API smoke 测试 | 覆盖核心 API：机构产品指标快照、数据录入版本、预算输出报表、预算汇总、对比汇总、费用预测元数据 |
| P1-5 | 依赖清理 | 从 `pyproject.toml` / `requirements.txt` 移除 `aiosqlite`；更新 `.env.example` |

#### P2 — 锦上添花（可排后续迭代）

| ID | 需求 | 说明 |
|----|------|------|
| P2-1 | SQL 方言适配器封装 | 将 SQL 方言差异集中到 `sql_dialect.py`，避免业务代码直接拼接专有语法 |
| P2-2 | 连接池监控 | 增加连接池状态指标（活跃连接数、等待队列长度）供运维观测 |
| P2-3 | 迁移耗时优化 | 对大表（如 compare.db 418 MB）使用分批迁移 + 并行写入加速 |

### 3.2 关键约束与假设

#### 约束

| # | 约束 | 详情 |
|---|------|------|
| C1 | 纯 raw SQL，无 ORM | 不使用 SQLAlchemy 等 ORM 框架，保持现有代码风格 |
| C2 | 禁止大爆炸式替换 | 不允许一次提交覆盖全部文件，必须逐模块迁移，每个模块验证通过后再进入下一个 |
| C3 | 迁移只读源库 | 迁移脚本不得修改 SQLite 源数据，确保可随时回滚 |
| C4 | MySQL 最低版本 8.0.16 | CHECK 约束需要 8.0.16+ 才真正执行 |
| C5 | TEXT/JSON 字段不得缩水 | `payload_json`、`config_json`、`basis_json`、`formula`、`before_data`/`after_data` 等大字段保持 TEXT/LONGTEXT 或 JSON 类型 |

#### 假设

| # | 假设 | 风险 |
|---|------|------|
| A1 | MySQL 实例已就绪，网络可达 | 需提前确认 |
| A2 | 所有 `budget_2025.db` 和 `budget_2026.db` 的表结构完全一致 | 如果不一致，合并时需要额外处理 |
| A3 | 未来年度库（`budget_2027.db` 等）也遵循相同表结构 | 如结构变更，需要额外迁移策略 |
| A4 | 迁移窗口内系统可停机（不需要热迁移） | 如需热迁移需要额外方案 |

### 3.3 迁移执行顺序

```
P0-1 (MySQL建库) → P0-2 (连接层) → P0-3 (Schema DDL) → P0-4 (年度表合并)
    → P0-5 (占位符替换) → P0-6 (SQL语法改写) → P0-7 (路由驱动替换)
    → P0-8 (数据迁移) → P0-9 (数据校验) → P0-10 (测试验证)
```

其中 P0-5 和 P0-6 可在同一模块内同时进行，按模块推进（system → org_product → budget_data → compare → expense_forecast → smart_report）。

---

## 4. 待确认问题

| # | 问题 | 影响范围 |
|---|------|---------|
| Q1 | 迁移期间系统是否需要保持在线？是否需要"先双写后切换"？ | 决定是否需要灰度策略 |
| Q2 | `budget_2025.db` 和 `budget_2026.db` 的表结构是否 100% 一致？有无年度独有表或列？ | 影响 P0-4 年度表合并方案 |
| Q3 | 未来是否还有新的年度库（如 `budget_2027.db`）需要迁移？流程如何标准化？ | 影响迁移脚本设计 |
| Q4 | MySQL 实例部署在何处？本地还是远程？网络延迟对连接池配置的影响？ | 影响 P0-2 连接池参数 |
| Q5 | 现有 `verify_current_database_inventory.py` 是否需要同步改为 MySQL 版本？ | 影响 P0-10 测试策略 |
| Q6 | 迁移后是否立即删除 `var/data/*.db`，还是保留一段观察期？ | 影响回滚方案 |
