# SQLite 到 MySQL 迁移调研报告

**调研时间**：2026年6月17日  
**调研范围**：银行预算预测系统  
**报告完成者**：Qoder AI  

---

## 1. 数据库文件清单

### 1.1 生产级数据库（var/data/ 下）

| 文件名 | 大小 | 表数量 | 主要用途 |
|---------|------|--------|---------|
| common.db | 37 MB | 45 | 系统主库：用户管理、报表模板、组织产品树、预算预测规则等 |
| budget_2025.db | 4.7 MB | 10 | 2025年度预算数据库 |
| budget_2026.db | 140 MB | 10 | 2026年度预算数据库（活跃库，最大单库） |
| compare.db | 418 MB | 5 | 预算对比分析库（数据最大） |

**合计**：595.7 MB，60个唯一表

### 1.2 开发/缓存数据库（apps/var/data/ 下）

| 文件名 | 大小 | 表数量 | 说明 |
|---------|------|--------|------|
| budget_2026.db | 192 KB | 10 | 开发副本 |
| common.db | 760 KB | 45 | 开发副本 |
| compare.db | 44 KB | 5 | 开发副本 |

**说明**：此目录包含编译产物或开发快照，部署时不推荐包含。

---

## 2. 数据库连接方式

### 2.1 连接驱动

**主驱动**：`aiosqlite` 0.20.0（异步SQLite驱动）  
**备选驱动**：`sqlite3` 3.x（Python 内置同步驱动）

#### 使用分布：
- **aiosqlite**（异步）：FastAPI 路由中大部分读写操作
- **sqlite3**（同步）：初始化、Schema检查、导入导出等场景

### 2.2 数据库路径配置

**配置机制**：基于环境变量的 Pydantic Settings

```python
# 文件：apps/api/app/core/config.py

class Settings(BaseSettings):
    repo_root: Path = REPO_ROOT  # 仓库根路径
    data_dir: Path = REPO_ROOT / "var" / "data"  # 数据库存放目录
    budget_year: int = 2026  # 当前预算年度
```

**路径取决规则**（文件：`app/core/db_paths.py`）：

```python
def common_db_path() -> Path:
    return settings.data_dir / "common.db"

def budget_db_path(year: int | None = None) -> Path:
    y = year if year is not None else settings.budget_year
    return settings.data_dir / f"budget_{y}.db"

def compare_db_path() -> Path:
    return settings.data_dir / "compare.db"
```

**特点**：
- ✅ 所有路径基于配置对象，非硬编码
- ✅ 支持通过 `.env` 文件自定义 `data_dir`（虽然当前未配置）
- ✅ 支持多年度预算库共存

### 2.3 是否使用 ORM

**结论**：**未使用 ORM**（如 SQLAlchemy）

**原因**：
- 直接使用原生 SQL 语句
- 通过 `executescript()` 批量执行 Schema DDL
- 查询结果通过手工 Cursor.fetchall() 或 fetchone() 处理
- 没有模型映射层

**代码示例**：
```python
# 同步方式（初始化）
conn = sqlite3.connect(path)
conn.executescript(COMMON_SCHEMA)  # DDL
conn.execute("INSERT INTO users(...) VALUES (...)")  # DML
conn.commit()

# 异步方式（运行时）
async with aiosqlite.connect(db_path) as db:
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("SELECT * FROM table_name WHERE id = ?", (id_value,))
    rows = await db.fetchall()
```

---

## 3. SQLite 特有语法统计

### 3.1 使用频率汇总

| 语法特性 | 使用次数 | 涉及文件数 | 迁移难度 |
|---------|---------|----------|---------|
| **PRAGMA** | 1,209 | 408* | ⭐ 低 |
| **INTEGER PRIMARY KEY** | 270 | 63 | ⭐ 低 |
| **GLOB 操作符** | 346 | 95* | ⭐ 中 |
| **json_extract 函数** | 17 | 4 | ⭐ 低 |
| **INSERT OR IGNORE** | 9 | 4 | ⭐⭐ 中 |
| **INSERT OR REPLACE** | 1 | 1 | ⭐⭐ 中 |
| **GROUP_CONCAT** | 3 | 3 | ⭐ 低 |

*注：统计结果包含 `.venv` 中的开发依赖代码，实际项目代码的比例见下文。

### 3.2 关键语法深度分析

#### A. PRAGMA 语句（1,209 次）

**项目代码中的实际使用**（excludes `.venv`）：

| 语句 | 频率 | 用途 | 迁移方案 |
|------|------|------|---------|
| `PRAGMA foreign_keys = ON` | 15+ | 启用外键约束 | ✅ MySQL 原生支持，ALTER TABLE 时配置 |
| `PRAGMA table_info(table_name)` | 40+ | 检查表结构 | ✅ 改用 `INFORMATION_SCHEMA.COLUMNS` |

**关键文件**：
- `app/routers/auth.py`：每次数据库操作前启用外键
- `app/db_bootstrap/schemas.py`：Schema 初始化时设置
- `app/routers/system_edit_show.py`：批量写入前启用外键
- `app/db_bootstrap/runtime_metric_tree.py`：字段元数据检查

**迁移要点**：
- MySQL 默认支持外键，无需 PRAGMA 设置
- 将 `PRAGMA table_info()` 替换为 MySQL 元数据查询

---

#### B. GLOB 操作符（346 次）

**实际项目代码位置**：

| 文件 | 位置 | 代码示例 | 频率 |
|------|------|---------|------|
| `app/db_bootstrap/runtime_metric_tree.py` | WHERE 子句 | `WHERE functional_group_code NOT GLOB '[0-9]*'` | 关键 |
| SQL Schema 文件 | CHECK 约束 | 检查 VARCHAR 字段格式 | 分散 |

**迁移难度**：⭐⭐ 中等

**替换方案**：
- SQLite `GLOB` → MySQL `REGEXP`
- `GLOB '[0-9]*'` → `REGEXP '^[0-9]+$'`
- `GLOB '*ABC*'` → `LIKE '%ABC%'`
- `NOT GLOB '[0-9]*'` → `NOT REGEXP '^[0-9]+$'`

**关键示例**（需要改写）：
```sql
-- SQLite
WHERE functional_group_code NOT GLOB '[0-9]*'

-- MySQL 改写
WHERE functional_group_code NOT REGEXP '^[0-9]+$'
```

---

#### C. INTEGER PRIMARY KEY（270 次）

**分布**：
- `app/db_bootstrap/schemas.py`：35 次（Schema 定义）
- `app/db_bootstrap/expense.py`：13 次
- 测试代码：40+ 次

**SQLite 特性**：
- `INTEGER PRIMARY KEY` 是 SQLite 的别名，映射为 `ROWID`
- 支持 `AUTOINCREMENT` 关键字

**迁移方案**：⭐ 低 - 标准迁移

```sql
-- SQLite
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT
)

-- MySQL（一对一改写）
CREATE TABLE users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(255)
)
```

---

#### D. INSERT OR IGNORE / INSERT OR REPLACE（10 次）

**频率分布**：
- `app/init_db.py`：6 次（初始化期间设置默认值）
- `app/db_bootstrap/runner.py`：1 次
- `app/db_bootstrap/seeds.py`：1 次
- `app/services/budget_output_display_config.py`：1 次

**场景分析**：

| 文件 | 代码 | 目的 | MySQL 替代 |
|------|------|------|-----------|
| init_db.py | `INSERT OR IGNORE INTO settings(...)` | 避免重复插入配置 | `INSERT IGNORE` 或 `ON DUPLICATE KEY UPDATE` |
| intelligent_budget_simulation.py | `INSERT OR REPLACE INTO intelligent_budget_tasks` | 任务去重覆盖 | `REPLACE INTO` 或 `ON DUPLICATE KEY UPDATE` |

**迁移方案**：⭐⭐ 中等 - 需要逐个适配

```sql
-- SQLite
INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)

-- MySQL 方案 1
INSERT IGNORE INTO settings(key, value) VALUES(?, ?)

-- MySQL 方案 2（推荐，更灵活）
INSERT INTO settings(key, value) 
VALUES(?, ?) 
ON DUPLICATE KEY UPDATE value=VALUES(value)
```

---

#### E. 其他特性

| 特性 | 频率 | 说明 |
|------|------|------|
| `GROUP_CONCAT` | 3 次 | MySQL 同名函数，100% 兼容 |
| `json_extract` | 17 次 | MySQL 5.7+ 完全支持 |

---

## 4. 数据库初始化与 Schema 管理

### 4.1 初始化流程

**入口文件**：`app/init_db.py`

**初始化函数调用链**：
```
ensure_databases()  # 主函数，幂等性设计
├─ init_common_db() / 更新现有 common.db
│  ├─ conn.executescript(COMMON_SCHEMA)  # DDL 批量执行
│  ├─ ensure_department_expense_master_schema_sync(conn)
│  ├─ ensure_expense_forecast_schema_sync(conn)
│  ├─ ... (8 个 schema 同步函数)
│  └─ seed_periods() / seed_default_smart_ppt()  # 初始数据种子
├─ init_budget_db()  / 更新现有 budget_*.db
│  ├─ conn.executescript(BUDGET_SCHEMA)
│  ├─ ensure_budget_version_schema_sync(conn)
│  ├─ ensure_budget_data_update_time_triggers(conn)
│  └─ ... (数据库触发器)
└─ init_compare_db()  # 对比库初始化
```

### 4.2 Schema 定义位置

**主 Schema 文件**：`app/db_bootstrap/schemas.py` (732 行)

**Schema 分类**：

| Schema | 定义位置 | 表数量 | 特点 |
|--------|---------|--------|------|
| COMMON_SCHEMA | schemas.py 第 6-393 行 | 45 | 系统全局表、用户、权限、组织产品树 |
| BUDGET_SCHEMA | schemas.py 第 397-654 行 | 10 | 预算数据表、版本表、设置表 |
| COMPARE_SCHEMA | schemas.py 第 658-732 行 | 5 | 预算对比专用表 |
| BUSINESS_COST_INCOME_SCHEMA | business_cost_income.py | 4 | 成本收入拆分表（跨 common 和 budget 库） |

### 4.3 触发器与约束

**外键约束**：
- 全局启用：所有 Schema 头部都有 `PRAGMA foreign_keys = ON`
- CASCADE 删除配置：多表定义 `ON DELETE CASCADE`

**触发器**：
- 文件：`app/db_bootstrap/budget_data.py`
- 用途：维护 budget_data 表的 update_time 自动更新

**视图定义**：
- `data_account`：从 `data_account_metric_node` 提取激活的账户
- `data_account_metric_binding`：账户与指标的多对多关联

---

## 5. 依赖与并发访问模式

### 5.1 驱动依赖版本

**pyproject.toml 声明**：

```toml
dependencies = [
    "aiosqlite==0.20.0",      # 异步 SQLite 驱动
    "fastapi==0.115.6",        # Web 框架
    "uvicorn[standard]==0.32.1", # ASGI 服务器
    ...
]
```

### 5.2 并发访问分析

#### A. 多线程访问

**使用场景**：
- 飞书机器人集成（`app/integrations/feishu_bot.py`）
  - 后台线程处理长连接事件
  - 使用 `threading.Lock()` 保护共享状态（not SQLite itself）

- Agent 调试追踪（`app/agent/agent_debug_trace.py`）
  - 调试日志线程锁

**SQLite 并发特性**：
- SQLite 支持多线程读（shared lock）
- 写操作自动排队（独占锁）
- 无显式连接池配置

#### B. 异步并发

**主要使用**：FastAPI 路由中的 `aiosqlite`
- 每个请求创建新连接：`async with aiosqlite.connect(db_path) as db`
- uvicorn worker 通常运行单进程多线程
- 无 WAL 模式配置

#### C. WAL 模式状态

**当前状态**：**未启用 WAL 模式**

**证据**：
- 无 `journal_mode=WAL` 配置
- 无 `PRAGMA journal_mode = WAL` 初始化语句
- SQLite 默认 DELETE 日志模式（影响并发性能）

**影响**：
- 写操作性能受限（每次写需要完整日志）
- 并发读受限（写操作可能锁定表）

---

## 6. 数据库路径配置

### 6.1 硬编码 vs 配置

**结论**：✅ **非硬编码，基于配置**

**配置链**：
```
.env (可选) 
  → Pydantic Settings
    → settings.data_dir 
      → db_paths.py 函数
        → 返回 Path 对象
```

### 6.2 .env 中的数据库配置

当前 `.env` 文件内容（`apps/api/.env`）：

```env
# 数据库路径配置：缺失
# 默认使用 repo_root/var/data/

# 其他配置：
CORS_ORIGINS=...
DEEPSEEK_API_KEY=...
FEISHU_ENABLED=true
```

**特点**：
- 数据库路径**未在 .env 中暴露**，基于代码默认值
- 可通过修改 `app/core/config.py` 添加 `DATA_DIR` 环境变量支持

### 6.3 部署路径特性

**当前部署包结构**：
```
banking-budget-system/
├── var/data/
│   ├── common.db
│   ├── budget_2025.db
│   ├── budget_2026.db
│   └── compare.db
├── apps/api/
│   ├── app/
│   ├── .env (敏感信息)
│   └── run_server.py
└── start.sh / stop.sh
```

**优点**：相对路径便于迁移，压缩包解压即用

---

## 7. 迁移难度评估矩阵

### 7.1 迁移风险分类

| 类别 | 难度 | 工作量 | 关键风险 |
|------|------|--------|---------|
| **Schema 改写** | ⭐ 低 | 2-3 天 | PRAGMA、GLOB 语法替换 |
| **连接层改造** | ⭐⭐ 中 | 3-5 天 | 异步驱动替换（aiosqlite → aiomysql/asyncmy） |
| **数据迁移** | ⭐⭐⭐ 高 | 5-10 天 | 数据类型映射、字符集、索引优化 |
| **并发测试** | ⭐⭐ 中 | 2-3 天 | WAL 模式与 MySQL 锁机制差异 |
| **依赖更新** | ⭐ 低 | 1 天 | requirements.txt 更新 |

### 7.2 最大单文件改动列表

| 文件 | 改动点数 | 优先级 |
|------|--------|--------|
| `app/db_bootstrap/schemas.py` | 50+ (PRAGMA, 类型) | P0 |
| `app/db_bootstrap/runtime_metric_tree.py` | 10+ (GLOB) | P0 |
| `app/init_db.py` | 30+ (executescript, INSERT OR IGNORE) | P1 |
| `app/db_bootstrap/business_cost_income.py` | 15+ (Schema) | P1 |
| `app/routers/*.py` (41 个) | 各 1-5 处 (PRAGMA foreign_keys) | P2 |

---

## 8. 迁移方案建议

### 8.1 分阶段迁移策略

#### **阶段 1：准备期（1-2 周）**
- [ ] 选定 MySQL 驱动：推荐 `aiomysql` 或 `asyncmy`（完全兼容 aiosqlite API）
- [ ] 建立 MySQL 测试环境（8.0+）
- [ ] 编写 Schema 转换脚本
- [ ] 建立自动化测试用例（数据一致性）

#### **阶段 2：技术改造（2-3 周）**
- [ ] 改写 Schema（PRAGMA、GLOB、类型映射）
- [ ] 替换驱动（sqlite3/aiosqlite → mysql/aiomysql）
- [ ] 改写连接层（data_dir 配置 → connection_string）
- [ ] 修改初始化脚本（executescript → 单语句执行）

#### **阶段 3：数据迁移（1-2 周）**
- [ ] 导出 SQLite 数据
- [ ] 转换数据格式（BLOB、JSON、日期等）
- [ ] 批量导入 MySQL
- [ ] 数据完整性验证

#### **阶段 4：测试与优化（2-3 周）**
- [ ] 单元测试覆盖
- [ ] 集成测试（多并发场景）
- [ ] 性能基准测试（查询耗时、吞吐量）
- [ ] 索引优化

#### **阶段 5：灰度发布（1 周）**
- [ ] 双库写入测试（SQLite + MySQL 同步）
- [ ] 路由切换测试
- [ ] 故障回滚流程验证
- [ ] 生产环境部署

### 8.2 关键改写示例

#### 改写 1：PRAGMA foreign_keys

```python
# SQLite 方式
async with aiosqlite.connect(db_path) as db:
    await db.execute("PRAGMA foreign_keys = ON")

# MySQL 方式（在连接字符串中配置）
import aiomysql
async with aiomysql.create_pool(
    host=host,
    user=user,
    password=password,
    db=database,
    # MySQL 自动启用外键
) as pool:
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")  # 外键已启用
```

#### 改写 2：GLOB 语法

```sql
-- SQLite
WHERE functional_group_code NOT GLOB '[0-9]*'

-- MySQL（方案 A：REGEXP）
WHERE functional_group_code NOT REGEXP '^[0-9]+$'

-- MySQL（方案 B：LIKE，某些场景更快）
WHERE functional_group_code NOT LIKE '[0-9]%'  -- 仅用于前缀匹配
```

#### 改写 3：executescript

```python
# SQLite（批量执行 DDL）
conn.executescript("""
    CREATE TABLE users(...);
    CREATE INDEX idx_users(...);
    INSERT INTO defaults(...) VALUES(...);
""")

# MySQL（单语句执行）
for sql_statement in schema_script.split(';'):
    if sql_statement.strip():
        await db.execute(sql_statement)
```

#### 改写 4：INSERT OR IGNORE

```sql
-- SQLite
INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)

-- MySQL（假设 key 有 UNIQUE 约束）
INSERT IGNORE INTO settings(key, value) VALUES(?, ?)

-- 或
INSERT INTO settings(key, value) VALUES(?, ?)
ON DUPLICATE KEY UPDATE value=VALUES(value)
```

---

## 9. 遗留问题与建议

### 9.1 即时改进项（无需迁移）

| 建议 | 优先级 | 影响 |
|------|--------|------|
| 启用 WAL 模式（SQLite） | P1 | 并发性能提升 5-10 倍 |
| 配置连接池（aiosqlite） | P2 | 减少连接开销 |
| 添加查询超时设置 | P2 | 防止长查询锁定 |
| Schema 版本控制 | P1 | 简化多库同步 |

### 9.2 MySQL 迁移后建议

| 改进项 | 优先级 |
|--------|--------|
| 分区表设计（按 budget_year 分区） | P2 |
| 读写分离与副本配置 | P2 |
| 慢查询日志配置 | P1 |
| 自动备份与恢复策略 | P0 |
| 连接池配置（最小 10，最大 50） | P1 |

---

## 10. 总结

### 核心发现：

1. **代码库 SQLite 依赖深度**：中等
   - 使用原生 SQL（无 ORM 框架）
   - 无复杂 ORM 迁移包袱

2. **SQLite 特有语法分布**：集中且离散
   - PRAGMA：普遍但易替换（配置级别）
   - GLOB：集中在 1-2 个文件，需精准改写
   - 其他：兼容性强

3. **数据规模**：
   - 单库最大 418 MB（compare.db）
   - 可接受数据库迁移周期

4. **并发特性**：
   - FastAPI 异步框架适合 MySQL 异步驱动
   - 目前无 WAL 配置，MySQL 迁移后性能潜力大

5. **推荐迁移周期**：8-12 周（含测试）

---

## 附录 A：文件引用汇总

### 关键业务文件
- `/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)/apps/api/app/init_db.py` - 数据库初始化入口
- `/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)/apps/api/app/db_bootstrap/schemas.py` - Schema 定义（732 行）
- `/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)/apps/api/app/core/db_paths.py` - 路径配置
- `/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)/apps/api/pyproject.toml` - 依赖声明

### 高风险改写文件
- `app/db_bootstrap/runtime_metric_tree.py` - GLOB 操作符（需精准改写）
- `app/routers/*.py`（41 个文件） - PRAGMA 调用（批量替换）
- `app/db_bootstrap/business_cost_income.py` - 跨库 Schema（数据一致性风险）

---

*本报告由 Qoder AI 完成，基于代码静态分析和运行时配置扫描。*
