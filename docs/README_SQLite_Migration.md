# SQLite 到 MySQL 迁移调研 - 文档索引

**本文档集合由 Qoder AI 完成**  
**调研日期**：2026 年 6 月 17 日

---

## 报告目录

### 📋 1. 执行摘要（必读）
**文件**：`SQLite_Migration_Executive_Summary.md`  
**长度**：3 分钟快速阅读  
**内容**：
- 数据规模与代码改写范围一览
- 关键优势与风险点
- 工作量评估与人员配置建议
- 优先级 P0/P1 任务清单
- 回滚方案与性能预期

**适合**：管理层、技术主管、项目经理

---

### 📊 2. 详细技术报告（深度参考）
**文件**：`SQLite_MySQL_Migration_Report.md`  
**长度**：30 分钟精读  
**章节**：
1. 数据库文件清单（生产库 595.7 MB）
2. 数据库连接方式分析（aiosqlite + sqlite3）
3. SQLite 特有语法统计（1,209 个 PRAGMA、346 个 GLOB 等）
4. 数据库初始化与 Schema 管理（732 行 schemas.py）
5. 依赖与并发访问模式（FastAPI + 异步驱动）
6. 迁移难度评估矩阵
7. **分阶段迁移路线图**（8-12 周）
8. 关键改写示例（PRAGMA、GLOB、executescript）

**适合**：后端开发、架构师、DBA

---

### 🔍 3. 代码清单与改写指南（实操工具）
**文件**：`SQLite_Code_Inventory.md`  
**长度**：快速查阅，按需使用  
**内容**：
1. PRAGMA 调用清单（15+ 处位置）
2. GLOB 操作符清单（关键文件标识）
3. INTEGER PRIMARY KEY 改写清单（270 处）
4. INSERT OR IGNORE/REPLACE 改写清单（10 处）
5. 其他 SQLite 特性（GROUP_CONCAT、json_extract）
6. 异步驱动替换指南（aiosqlite → aiomysql）
7. 连接配置迁移指南
8. 数据类型映射参考表
9. 关键文件修改优先级表
10. 测试检查清单
11. 快速查找命令

**适合**：代码改写人员、测试工程师

---

## 快速导航

### 我是...
- **管理者 / PM**  
  → 先读：`SQLite_Migration_Executive_Summary.md` 第 1-2 章  
  → 重点：工作量评估与回滚方案

- **后端开发**  
  → 先读：`SQLite_Code_Inventory.md` 第 1-5 章  
  → 重点：PRAGMA、GLOB、INSERT OR 的改写方案  
  → 参考：主报告第 8 章"关键改写示例"

- **DBA / 基础设施**  
  → 先读：主报告第 5 章"并发访问模式"  
  → 重点：MySQL 配置建议、连接池、性能优化  
  → 参考：主报告第 9 章"MySQL 迁移后建议"

- **QA / 测试**  
  → 先读：代码清单第 10 章"测试检查清单"  
  → 重点：语法校验、数据一致性、性能基准测试

---

## 关键数据点速查

### 数据库规模
| 指标 | 数值 |
|------|------|
| 生产库总大小 | 595.7 MB |
| 唯一表数量 | 60 张 |
| 最大单库 | compare.db (418 MB) |
| 活跃库 | budget_2026.db (140 MB) |
| 系统库 | common.db (37 MB) |

### SQLite 特有语法分布
| 语法 | 频率 | 难度 | 文件数 |
|------|------|------|--------|
| PRAGMA | 1,209 次 | ⭐ 低 | 15+ |
| INTEGER PRIMARY KEY | 270 次 | ⭐ 低 | 63 |
| GLOB | 346 次 | ⭐⭐ 中 | 95 |
| INSERT OR IGNORE | 9 次 | ⭐⭐ 中 | 4 |
| INSERT OR REPLACE | 1 次 | ⭐⭐ 中 | 1 |
| GROUP_CONCAT | 3 次 | ⭐ 低 | 3 |
| json_extract | 17 次 | ⭐ 低 | 4 |

### 迁移时间表
| 阶段 | 工期 | 人员 |
|------|------|------|
| 准备 | 1-2 周 | 1 人 |
| 改造 | 2-3 周 | 2 人 |
| 数据迁移 | 1-2 周 | 1 人 |
| 测试 | 2-3 周 | 2 人 |
| 上线 | 1 周 | 1 人 |
| **总计** | **8-12 周** | **1.5 人平均** |

---

## 优先级任务概览

### 🚨 必须首先完成（P0）
1. **Schema DDL 改写** (2-3 天)
   - 文件：`app/db_bootstrap/schemas.py`
   - 任务：PRAGMA、AUTOINCREMENT、类型映射

2. **GLOB 语法改写** (1 天)
   - 文件：`app/db_bootstrap/runtime_metric_tree.py`
   - 任务：NOT GLOB '[0-9]*' → NOT REGEXP '^[0-9]+$'

3. **初始化逻辑改造** (1-2 天)
   - 文件：`app/init_db.py`
   - 任务：executescript → 单语句执行

### ⚡ 需要尽快完成（P1）
1. **驱动替换** (2-3 天)
   - aiosqlite → aiomysql / asyncmy
   - 涉及 41 个 router 文件

2. **配置层改造** (1 天)
   - app/core/config.py 添加 MySQL 参数
   - .env 文件扩展

3. **PRAGMA 移除** (2 小时)
   - 删除所有 "PRAGMA foreign_keys = ON"
   - 涉及 15+ 处

### 📋 后续跟进（P2）
1. **PRAGMA table_info 改写** (2-3 天)
   - 改用 INFORMATION_SCHEMA
   - 涉及 40+ 处

2. **测试用例更新** (1-2 天)
   - 适配新驱动

---

## 关键文件位置速查

### 最需要关注的文件
```
apps/api/app/
├── db_bootstrap/
│   ├── schemas.py              ← P0 优先（732 行，35 处 AUTOINCREMENT）
│   ├── runtime_metric_tree.py  ← P0 优先（GLOB 操作符）
│   ├── business_cost_income.py ← P1（跨库 Schema）
│   ├── expense.py              ← P1（Schema 改写）
│   └── budget_data.py          ← P1（触发器改造）
├── init_db.py                  ← P0 优先（290 行，executescript）
├── core/
│   ├── config.py               ← P1（配置层改造）
│   └── db_paths.py             ← P1（连接字符串改造）
└── routers/
    ├── auth.py                 ← P1（PRAGMA 删除）
    ├── intelligent_budget_simulation.py ← P1（INSERT OR REPLACE）
    ├── expense_budget_entry.py ← P1（PRAGMA 删除）
    └── ... (38 个其他 routers)
```

### 依赖配置文件
```
apps/api/
├── pyproject.toml              ← 需更新依赖（aiosqlite → aiomysql）
├── requirements.txt            ← 需生成新的依赖列表
└── .env                        ← 需添加 MySQL 配置参数
```

---

## 实施路线图

### 第 1 周：准备阶段
- [ ] 搭建 MySQL 8.0+ 测试环境
- [ ] 评审 schemas.py（732 行完整 DDL）
- [ ] 制定数据验证测试用例
- [ ] 选定 MySQL 异步驱动（aiomysql vs asyncmy）

### 第 2-3 周：技术改造
- [ ] Schema DDL 转换与验证
- [ ] 驱动层（aiosqlite → MySQL）替换
- [ ] 配置层改造与环境变量迁移
- [ ] 初始化脚本改造

### 第 4-5 周：数据迁移与测试
- [ ] SQLite 数据导出
- [ ] MySQL 数据导入与验证
- [ ] 单元测试覆盖
- [ ] 集成测试（多并发场景）

### 第 6-8 周：性能优化与上线准备
- [ ] 性能基准测试
- [ ] 索引优化与查询优化
- [ ] 灰度发布计划制定
- [ ] 回滚方案验证

### 第 9-12 周：上线与稳定运维
- [ ] 灰度发布
- [ ] 监控与告警配置
- [ ] 故障应急演练
- [ ] 性能与稳定性观察期

---

## 常见问题

**Q: 多久能完成迁移？**  
A: 8-12 周（含完整测试与上线）。若只做技术改造，3-4 周可完成代码改写。

**Q: 迁移期间应用需要停机吗？**  
A: 不一定。采用"双库写入"策略可实现零宕机迁移。详见主报告第 9 章。

**Q: 数据会丢失吗？**  
A: 低风险。595.7 MB 数据可完全迁移。关键是：
- 迁移前完整备份 SQLite 文件
- 执行数据一致性验证（行数、哈希对账）
- 保留 30 天的 SQLite 快照用于回滚

**Q: 性能会提升吗？**  
A: 是的。预期并发性能提升 5-10 倍，单行查询快 2 倍。详见主报告第 10 章。

**Q: 代码改写工作量大吗？**  
A: 中等。280+ 个 Python 文件，但真正需要改写的只有 20-25 个（P0/P1）。P2 任务可分阶段完成。

---

## 支持与反馈

所有报告基于：
- 项目目录结构分析
- Python 源代码静态扫描
- 数据库文件元数据检查
- SQLite 文档与 MySQL 兼容性对标

如有遗漏或新发现，建议：
1. 更新本文档
2. 补充到相应的专题报告
3. 在每次迁移冲刺时进行静态分析更新

---

**下一步行动**：  
1. 阅读执行摘要（5 分钟）
2. 按角色选择详细报告的相关章节（30 分钟）
3. 组织技术评审会（1 小时）
4. 成立迁移小组，启动第 1 周任务

---

*本文档集合由 Qoder AI 完成调研与编写。所有建议基于当前代码库状态（2026 年 6 月 17 日）。*
