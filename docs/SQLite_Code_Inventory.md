# SQLite 特有语法代码清单

**目的**：快速定位需要改写的代码行，用于 MySQL 迁移

**最后更新**：2026年6月17日

---

## 1. PRAGMA 调用清单（15+ 处）

### 1.1 PRAGMA foreign_keys = ON

这些位置需要改为 MySQL 连接时的配置参数。

```
app/routers/auth.py                          → L: 多处
app/routers/intelligent_budget_simulation.py → L: 多处
app/routers/expense_budget_entry.py          → L: 多处
app/routers/chart_readonly.py                → L: 多处
app/routers/system_edit_show.py              → L: 多处
app/budget_data_writer.py                    → L: 多处
app/core/audit.py                            → L: 多处
app/integrations/feishu_store.py             → L: 多处
app/db_bootstrap/schemas.py                  → L: 6-7 (Schema 初始化)
app/db_bootstrap/budget_data.py              → L: 多处
```

**改写方案**：
- 移除所有 `await db.execute("PRAGMA foreign_keys = ON")`
- MySQL 在连接时自动启用外键约束

### 1.2 PRAGMA table_info

用于反射表结构。

```
app/db_bootstrap/runtime_metric_tree.py      → 字段元数据检查
app/db_bootstrap/current_contracts.py        → 表结构校验
app/db_bootstrap/budget_data.py              → 动态字段检查
app/db_bootstrap/budget_version.py           → 列名查询
app/db_bootstrap/smart_report.py             → 列名查询
app/routers/system_edit_show.py              → 表结构验证
```

**改写方案**：
```python
# SQLite
for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall():
    col_name = row[1]

# MySQL (改为)
for row in await db.execute(f"""
    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE()
""", (table_name,)):
    col_name = row[0]
```

---

## 2. GLOB 操作符清单

### 2.1 关键位置（需要精准改写）

```
app/db_bootstrap/runtime_metric_tree.py
  → WHERE functional_group_code NOT GLOB '[0-9]*'
```

**改写**：
```sql
-- 改为
WHERE functional_group_code NOT REGEXP '^[0-9]+$'
```

### 2.2 分散的 GLOB 调用（venv 中的依赖代码）

- 开发依赖包中使用 GLOB（无需改写，这些不会在生产运行）

---

## 3. INTEGER PRIMARY KEY 清单

### 3.1 Schema 定义（需要类型映射）

```
app/db_bootstrap/schemas.py
  → 35 处 "id INTEGER PRIMARY KEY AUTOINCREMENT"

app/db_bootstrap/business_cost_income.py
  → 4 处相同定义

app/db_bootstrap/expense.py
  → 13 处相同定义
```

**改写模板**：
```sql
-- SQLite
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT
)

-- MySQL
CREATE TABLE users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(255)
)
```

**字符类型映射表**：

| SQLite | MySQL | 字符限制 |
|--------|-------|---------|
| TEXT | VARCHAR(255) | 255 字节 |
| TEXT | TEXT | 65,535 字节 |
| TEXT | LONGTEXT | 4 GB |
| BLOB | BLOB | 二进制数据 |
| REAL | DOUBLE | 浮点数 |
| INTEGER | INT | 4 字节整数 |
| INTEGER | BIGINT | 8 字节整数 |

---

## 4. INSERT OR IGNORE / INSERT OR REPLACE

### 4.1 INSERT OR IGNORE（需要改写）

```
app/init_db.py (6 处)
  Line ~116-126: INSERT OR IGNORE INTO settings(...)

app/db_bootstrap/runner.py (1 处)
  └─ Budget registry update

app/db_bootstrap/seeds.py (1 处)
  └─ Seed data insertion

app/services/budget_output_display_config.py (1 处)
  └─ Display config update
```

**改写方案**：
```sql
-- SQLite
INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)

-- MySQL (方案 A)
INSERT IGNORE INTO settings(key, value) VALUES(?, ?)

-- MySQL (方案 B - 推荐用于更新)
INSERT INTO settings(key, value) VALUES(?, ?)
ON DUPLICATE KEY UPDATE value=VALUES(value)
```

### 4.2 INSERT OR REPLACE（需要改写）

```
app/routers/intelligent_budget_simulation.py
  → INSERT OR REPLACE INTO intelligent_budget_tasks(...)
```

**改写**：
```sql
-- SQLite
INSERT OR REPLACE INTO intelligent_budget_tasks(...) VALUES(...)

-- MySQL (方案 A)
REPLACE INTO intelligent_budget_tasks(...) VALUES(...)

-- MySQL (方案 B)
INSERT INTO intelligent_budget_tasks(...) VALUES(...)
ON DUPLICATE KEY UPDATE status=VALUES(status), ...
```

---

## 5. 其他 SQLite 特性

### 5.1 GROUP_CONCAT（3 处，无需改写）

```
业务代码: 3 处 GROUP_CONCAT() 调用
改写: MySQL 5.7+ 完全支持，无需改写
```

### 5.2 json_extract（17 处，无需改写）

```
app/services/org_product_runtime_catalog.py (6 处)
  → json_extract(json_col, '$.path')

改写: MySQL 5.7+ 完全支持，无需改写
```

### 5.3 executescript（需要改写）

```
app/init_db.py
  → conn.executescript(COMMON_SCHEMA)
  → conn.executescript(BUDGET_SCHEMA)
  → conn.executescript(COMPARE_SCHEMA)
```

**改写**：
```python
# SQLite
conn.executescript("""
    CREATE TABLE users(...);
    CREATE INDEX idx_users(...);
""")

# MySQL (改为)
for sql_stmt in schema_sql.split(';'):
    if sql_stmt.strip():
        cursor.execute(sql_stmt)
db.commit()
```

---

## 6. 异步驱动替换清单

### 6.1 需要替换的导入

```python
# 当前
import aiosqlite
async with aiosqlite.connect(db_path) as db:
    await db.execute(...)

# 改为
import aiomysql  # 或 asyncmy
pool = await aiomysql.create_pool(
    host=host, user=user, password=pwd, db=dbname
)
async with pool.acquire() as conn:
    async with conn.cursor() as cursor:
        await cursor.execute(...)
```

### 6.2 影响的文件列表

**主要异步调用**（41 个 router 文件）：
- `app/routers/auth.py`
- `app/routers/intelligent_budget_simulation.py`
- `app/routers/expense_budget_entry.py`
- `app/routers/chart_readonly.py`
- `app/routers/system_edit_show.py`
- ... (其他 36 个)

**同步调用**（需要改为异步或保留为同步）：
- `app/init_db.py` - 初始化时可保留同步 sqlite3 驱动，改用 mysql-connector-python
- `app/db_bootstrap/*.py` - 初始化时 OK

---

## 7. 连接配置迁移

### 7.1 当前配置源

```
app/core/config.py
  → data_dir: Path = REPO_ROOT / "var" / "data"

app/core/db_paths.py
  → 返回 Path 对象，用 aiosqlite.connect(str(path))
```

### 7.2 新配置目标

```python
# 新增到 app/core/config.py
class Settings:
    # SQLite 配置（兼容性）
    database_type: str = "mysql"  # "sqlite" | "mysql"
    
    # MySQL 连接
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "budget_app"
    mysql_password: str = ""
    mysql_database: str = "banking_budget"
    
    # SQLite 备用配置
    sqlite_data_dir: Path = REPO_ROOT / "var" / "data"
```

### 7.3 .env 中的新条目

```env
# 数据库选择
DATABASE_TYPE=mysql

# MySQL 配置
MYSQL_HOST=db.company.com
MYSQL_PORT=3306
MYSQL_USER=budget_app
MYSQL_PASSWORD=<secure_password>
MYSQL_DATABASE=banking_budget
```

---

## 8. 数据类型映射参考

### 8.1 完整映射表

| SQLite 类型 | MySQL 类型 | 说明 |
|------------|-----------|------|
| INTEGER PRIMARY KEY | INT PRIMARY KEY AUTO_INCREMENT | 自增主键 |
| INTEGER | INT | 整数（4 字节） |
| INTEGER | BIGINT | 整数（8 字节） |
| REAL | DOUBLE | 浮点数 |
| TEXT | VARCHAR(255) | 短文本 |
| TEXT | TEXT | 中等文本（64K） |
| TEXT | LONGTEXT | 长文本（4GB） |
| BLOB | BLOB | 二进制 |
| DATETIME | DATETIME(6) | 日期时间（微秒精度） |
| NULL | NULL | 空值 |

### 8.2 NULL 值处理

SQLite 和 MySQL 都支持 NULL，无需改写。

---

## 9. 关键文件修改清单

| 文件 | 改动数 | 优先级 | 技术风险 |
|------|--------|--------|---------|
| `app/db_bootstrap/schemas.py` | 50+ | P0 | 高：影响所有表结构 |
| `app/db_bootstrap/runtime_metric_tree.py` | 10+ | P0 | 中：GLOB 改写需精准 |
| `app/init_db.py` | 30+ | P1 | 中：Schema 执行逻辑改写 |
| `app/db_bootstrap/business_cost_income.py` | 15+ | P1 | 高：跨库 Schema 同步 |
| `app/routers/*.py` (41 个) | 各 1-5 | P2 | 低：PRAGMA 批量删除 |
| `app/core/config.py` | 5-10 | P1 | 低：新增配置项 |
| `app/core/db_paths.py` | 3-5 | P1 | 低：改为返回连接字符串 |

---

## 10. 测试检查清单

### 10.1 语法校验
- [ ] 所有 PRAGMA 替换完成
- [ ] 所有 GLOB 改写完成
- [ ] 所有 INSERT OR IGNORE/REPLACE 改写完成
- [ ] 所有 executescript 改为单语句执行

### 10.2 数据一致性
- [ ] SQLite → MySQL 数据导出/导入验证
- [ ] 主键碰撞检查
- [ ] 外键约束验证
- [ ] 字符集编码检查（UTF-8）

### 10.3 性能测试
- [ ] 单表查询耗时对比
- [ ] 批量写入（INSERT）性能对比
- [ ] JOIN 查询耗时对比
- [ ] 并发（10+ 连接）性能压力测试

### 10.4 功能测试
- [ ] 用户认证与会话管理
- [ ] 预算数据增删改查
- [ ] 报表生成
- [ ] 智能模拟计算
- [ ] 飞书集成（长连接）

---

## 附录：快速查找命令

```bash
# 查找所有 PRAGMA 调用
grep -rn "PRAGMA" apps/api/app --include="*.py"

# 查找所有 GLOB
grep -rn "GLOB" apps/api/app --include="*.py"

# 查找所有 INSERT OR
grep -rn "INSERT OR" apps/api/app --include="*.py"

# 查找所有 aiosqlite.connect
grep -rn "aiosqlite.connect" apps/api/app --include="*.py"

# 查找所有 executescript
grep -rn "executescript" apps/api/app --include="*.py"
```

---

*此清单由 Qoder AI 生成，用作 MySQL 迁移工作的代码定位工具。*
