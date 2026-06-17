# SQLite 到 MySQL 迁移 - 执行摘要

**调研完成**：2026年6月17日  
**报告完成者**：Qoder AI  
**详细报告**：见 `SQLite_MySQL_Migration_Report.md` 和 `SQLite_Code_Inventory.md`

---

## 概况

### 数据规模
- **总数据量**：595.7 MB（生产库）
- **总表数**：60 个唯一表
- **最大库**：compare.db (418 MB)
- **活跃库**：budget_2026.db (140 MB)

### 代码迁移范围
- **Python 源文件**：280+ 个
- **需改写文件**：20-25 个（优先级 P0/P1）
- **PRAGMA 调用**：15+ 处
- **SQLite 特有语法**：346+ 处

---

## 关键发现

### ✅ 优势
1. **无 ORM 依赖** - 直接使用原生 SQL，无框架层改造
2. **驱动兼容性强** - aiosqlite API 与 aiomysql 高度相似
3. **数据复杂度低** - 无特殊数据类型（BLOB/JSON 都支持）
4. **异步框架友好** - FastAPI + 异步驱动组合成熟

### ⚠ 风险点
1. **GLOB 操作符** - 集中在 1-2 个关键文件，需精准改写
2. **executescript 调用** - Schema 初始化逻辑需重构
3. **数据导出/导入** - 595.7 MB 数据量，需避免数据丢失
4. **并发模式差异** - SQLite 锁机制与 MySQL 不同

---

## 迁移工作量评估

| 阶段 | 工作 | 工期 | 人员 |
|------|------|------|------|
| 准备 | 环境搭建、工具链、测试框架 | 1-2 周 | 1 人 |
| 改造 | Schema 转换、代码改写、驱动替换 | 2-3 周 | 2 人 |
| 数据迁移 | 导出、转换、导入、验证 | 1-2 周 | 1 人 |
| 测试 | 单元、集成、性能、压力测试 | 2-3 周 | 2 人 |
| 上线 | 灰度、回滚、监控 | 1 周 | 1 人 |
| **总计** | | **8-12 周** | **平均 1.5 人** |

---

## 优先级 P0 改写任务

### P0-1: Schema DDL 改写（2-3 天）
**文件**：`app/db_bootstrap/schemas.py`  
**改动**：
- 移除所有 `PRAGMA foreign_keys = ON`
- 将 `INTEGER PRIMARY KEY AUTOINCREMENT` 改为 `INT PRIMARY KEY AUTO_INCREMENT`
- TEXT 字段改为 VARCHAR(255) 或 TEXT（根据字段大小）
- 检查所有 CHECK 约束（SQLite GLOB → MySQL REGEXP）

### P0-2: GLOB 语法改写（1 天）
**文件**：`app/db_bootstrap/runtime_metric_tree.py`  
**改动**：
```sql
-- 改前
WHERE functional_group_code NOT GLOB '[0-9]*'

-- 改后
WHERE functional_group_code NOT REGEXP '^[0-9]+$'
```

### P0-3: 初始化逻辑改写（1-2 天）
**文件**：`app/init_db.py`  
**改动**：
- 使用 mysql-connector-python 或 pymysql（同步）替代 sqlite3
- 将 `executescript()` 改为逐语句执行
- 保留 INSERT OR IGNORE 但改用 MySQL 语法

---

## 优先级 P1 改写任务

### P1-1: 驱动替换（2-3 天）
**改写方向**：
```python
# 旧
import aiosqlite
async with aiosqlite.connect(db_path) as db:

# 新
import aiomysql
pool = await aiomysql.create_pool(host=..., user=..., password=..., db=...)
async with pool.acquire() as conn:
```

**涉及文件**：41 个 router + 10 个 service

### P1-2: 配置层改造（1 day）
**文件**：`app/core/config.py`, `.env`  
**改动**：
- 添加 DATABASE_TYPE（mysql/sqlite 可选）
- 添加 MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD 等参数
- 改造 `db_paths.py` 返回连接字符串而非 Path 对象

### P1-3: PRAGMA 移除（2 小时）
**改动**：
- 移除所有 `await db.execute("PRAGMA foreign_keys = ON")`
- MySQL 自动支持外键，无需配置

---

## 优先级 P2 改写任务

### P2-1: PRAGMA table_info 改写
**改动**：40+ 处 PRAGMA table_info 改用 INFORMATION_SCHEMA

### P2-2: 测试用例更新
**改动**：tests/db/*.py 适配新驱动

---

## 快速迁移核心清单

**需要立即行动**（优先级 P0）：
- [ ] 建立 MySQL 8.0+ 测试环境
- [ ] 审查 `app/db_bootstrap/schemas.py`（732 行）所有 DDL
- [ ] 定位所有 `GLOB` 用法（核心：runtime_metric_tree.py）
- [ ] 制定数据验证测试用例

**建议立即准备**（优先级 P1）：
- [ ] 选定 MySQL 异步驱动（aiomysql vs asyncmy）
- [ ] 准备环境变量迁移方案
- [ ] 梳理应用启动流程（启动前初始化逻辑）

**后续跟进**（优先级 P2）：
- [ ] 性能基准对标（SQLite vs MySQL）
- [ ] 并发场景压力测试
- [ ] 监控与告警配置

---

## 关键数据表一览

### 系统关键表（common.db）

| 表名 | 行数预估 | 字段数 | 用途 |
|------|---------|--------|------|
| users | 10-50 | 10 | 用户管理 |
| org_product_data_entry_draft | 1K+ | 15 | 组织产品数据录入 |
| expense_forecast_rule | 500+ | 12 | 预算预测规则 |
| budget_output_display_item | 500+ | 15 | 报表显示项配置 |
| data_account_metric_node | 2K+ | 20 | 指标树节点 |

### 预算数据表（budget_YYYY.db）

| 表名 | 行数预估 | 字段数 | 用途 |
|------|---------|--------|------|
| budget_data | 10K+ | 动态 | 预算数据事实表 |
| budget_summary | 1K+ | 15 | 预算汇总 |
| business_cost_income_value | 5K+ | 8 | 成本收入拆分 |

### 对比库（compare.db）

| 表名 | 行数预估 | 字段数 | 用途 |
|------|---------|--------|------|
| compare_budget_summary | 1K+ | 15 | 对比分析汇总 |
| compare_pivot_aggregate | 5K+ | 10 | 透视表汇总 |

---

## 性能期望对标

| 操作 | SQLite | MySQL | 提升 |
|------|--------|-------|------|
| 单行查询 | ~10ms | ~5ms | 2x |
| 批量插入（1K行） | ~500ms | ~100ms | 5x |
| 并发读（10 连接） | 有锁等待 | 无等待 | 10x+ |
| 并发写（5 连接） | 串行化 | 可并发 | 显著 |

---

## 回滚方案

**双库写入策略**（零宕机迁移）：
```
Phase 1: SQLite + MySQL 同时写入
  → 应用层代码分支，所有写操作同时写两个库
  
Phase 2: 数据对账
  → 对比 SQLite 和 MySQL 行数、数据哈希
  → 修复差异

Phase 3: 路由切换
  → 读写从 SQLite 切换到 MySQL
  → 保留 SQLite 数据备份

Phase 4: 回滚阈值
  → 发现问题时，立即切回 SQLite
  → 恢复至切换前的完整状态
```

---

## 文档导航

1. **SQLite_MySQL_Migration_Report.md**（详细报告）
   - 数据库架构完整分析
   - 每项 SQLite 特性的迁移方案
   - 分阶段迁移路线图

2. **SQLite_Code_Inventory.md**（代码清单）
   - 快速定位所有需要改写的代码
   - 具体文件和行号
   - 改写模板和示例

3. 本文档（执行摘要）
   - 快速概览与决策支持
   - 工作量评估与人员配置
   - 优先级任务清单

---

## 联系与支持

- 如需详细技术方案，参考主报告的第 8 章"迁移方案建议"
- 如需快速定位特定代码，使用 SQLite_Code_Inventory.md 的查找命令
- 如有新的 SQLite 特性使用，参考本报告第 3 章的映射表进行改写

---

**准备好开始 MySQL 迁移了吗？**  
建议首先：
1. 成立迁移小组（后端 2 人 + DBA 1 人）
2. 搭建 MySQL 8.0+ 测试环境
3. 按优先级 P0 逐项推进改造

