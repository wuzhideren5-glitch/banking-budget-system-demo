# Codex Handoff — v03 公式 / 上下文节点 / 科目性质

日期：2026-06-18  
工作区：`/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)`  
文档目录：`.scratch/sqlite-to-mysql-migration/`  
前置文档：

- `.scratch/sqlite-to-mysql-migration/codex_handoff_20260618_mysql_migration.md`（连接层迁移）
- `.scratch/sqlite-to-mysql-migration/cursor_handoff_20260618_org_product_mysql_data.md`（机构指标 MySQL 数据修复）
- `.scratch/sqlite-to-mysql-migration/v03_authority_notes_20260618.md`（v03 权威边界，**必读**）

---

## 0. 协作流程

| 步骤 | 角色 | 动作 |
|------|------|------|
| 1 | Cursor | 写 plan + 改代码 + 本地验证 |
| 2 | **Codex** | 按 **§7 检视清单** 验收，结论写入 `codex_review_v03_restore_nature_20260618.md` |
| 3 | 用户 | 根据 Codex 结论 commit / push / 继续下一阶段 |

---

## 1. 本轮目标（Cursor 已完成）

在 MySQL `banking_budget`（端口 **3307**）上，补齐机构及产品指标运行时树的三块缺口：

| 子任务 | 状态 | 说明 |
|--------|------|------|
| v03 公式导入 | ✅ 已执行 | `budget_formula` / `actual_formula` 从 Excel 写入 MySQL |
| v03 上下文节点恢复 | ✅ 已执行 | 缺失叶子/隐式 GROUP 插入 MySQL（遵守 v03 权威边界） |
| **科目性质（nature）** | ✅ 已修复 | 新增 DB 列 + API 读真实值 + v03 批量回填 |

**不在本轮：**

- 恢复第二段 `.05` / `.99` / `.90` / `.91` 老分支（见 `v03_authority_notes`）
- 修改前端 UI 逻辑（仅后端/API/DB）

---

## 2. 业务背景：科目性质为何「没了」

| 环节 | 现象 |
|------|------|
| v03 Excel | 「科目性质」列正常（收入、支出、资产余额…） |
| 旧 SQLite | 存在 `org_product_metric_table.payload_json`，nature 在 JSON 里 |
| MySQL 迁移后 | `data_account_metric_node` **原先无 `nature` 列**；API `_node_payload()` **写死 `"其他"`** |
| 恢复脚本 | 解析了 nature，INSERT 时只写了 `value_type` |

**修复策略：** 给 `data_account_metric_node` 增加 `nature VARCHAR(32) DEFAULT '其他'`，读树/同步路径读写该列，并用 v03 批量回填 METRIC 叶子。

---

## 3. 关键代码改动

### 3.1 Schema（bootstrap 自动 ADD COLUMN）

**文件：** `apps/api/app/db_bootstrap/runtime_metric_tree.py`

- `METRIC_NODE_REQUIRED_COLUMNS` 增加 `nature`
- `RUNTIME_ACCOUNT_NODE_COLUMNS` 增加 `"nature": "VARCHAR(32) NOT NULL DEFAULT '其他'"`

### 3.2 API 读树

**文件：** `apps/api/app/services/org_product_metric_runtime_snapshot.py`

- `_RUNTIME_TREE_COLUMNS` / SELECT 增加 `nature`
- `_node_payload()`：`"nature": _clean(row.get("nature")) or "其他"`（不再写死）

### 3.3 同步写库

**文件：** `apps/api/app/services/org_product_metric_runtime_sync.py`

- `_RuntimeMetricRef` 增加 `nature`
- `_normalize_nature()` 新增
- `sync_org_product_metric_runtime_refs` UPDATE 语句写入 `nature`
- 费用树 payload 同步处不再写死 `"其他"`

### 3.4 v03 运维脚本（新增，未 commit）

| 脚本 | 用途 |
|------|------|
| `apps/api/scripts/import_v03_formulas_to_mysql.py` | 公式导入 / `--verify-only` |
| `apps/api/scripts/restore_v03_context_nodes_to_mysql.py` | 缺失节点恢复；**`--backfill-nature`** 科目性质回填 |
| `apps/api/scripts/maintain_v03_metric_workbook.py` | v03 隐式 GROUP 插入 + 镜像行删除 |
| `apps/api/app/services/v03_metric_node_catalog.py` | 跨 sheet 重名、镜像、隐式 GROUP、stale 分支规则 |
| `apps/api/tests/org_product/test_v03_metric_node_catalog.py` | 规则单测 |

**计划文档：**

- `plan_migrate_formulas_v03_20260618.md`
- `plan_restore_v03_context_nodes_20260618.md`

### 3.5 v03 Excel 变更

**文件：** `resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx`

- 插入 6 个隐式 GROUP 行
- 删除 2 条镜像重复行（`AA.25.05` / `AA.27.05` 在利息净收入表）
- 备份：`var/data/backups/v03_metric_workbook_before_maintain_20260618_153959.xlsx`

---

## 4. MySQL 实测结果（Cursor 本地已跑）

环境：`MYSQL_HOST=127.0.0.1` `MYSQL_PORT=3307` `MYSQL_DATABASE=banking_budget`

### 4.1 节点规模

| 指标 | 数值 |
|------|------|
| 修复前 active 节点 | 2444 |
| 上下文恢复后 | **2521** |
| v03 解析 eligible 节点 | 1373 |

### 4.2 公式 verify

```bash
cd apps/api && . .venv/bin/activate
python scripts/import_v03_formulas_to_mysql.py --verify-only
```

- 结果：**0 mismatch**（`budget_formula` / `actual_formula`）

### 4.3 节点 restore verify

```bash
python scripts/restore_v03_context_nodes_to_mysql.py --verify-only
```

- 结果：**0 缺失** eligible 节点

### 4.4 科目性质回填

```bash
python scripts/restore_v03_context_nodes_to_mysql.py --backfill-nature
```

- 更新行数：**1373**
- v03 mismatch：**0**
- DB 分布（active）：收入 379、支出 292、资产余额 155、资产日均 117、负债余额 76、负债日均 69、利润 38、**其他 1395**

**「其他 1395」预期行为：** GROUP/CATEGORY 节点、产品根、不在 v03 的运行时节点（含已 purge 的老分支残留若仍 active）— v03 无单独科目性质。

**抽样：**

| node_code | nature |
|-----------|--------|
| AA.01.01 | 收入 |
| AA.14.02.05 | 收入 |
| AA.24.05 | 资产余额 |

### 4.5 单测

```bash
python -m unittest tests.org_product.test_v03_metric_node_catalog \
                   tests.org_product.test_org_product_metric_runtime_refs -v
```

- 结果：**43 passed**

---

## 5. Git 状态（交给 Codex 时）

**已修改（未 commit）：**

```
M apps/api/app/db_bootstrap/runtime_metric_tree.py
M apps/api/app/services/org_product_metric_runtime_snapshot.py
M apps/api/app/services/org_product_metric_runtime_sync.py
M resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx
```

**未跟踪（未 commit）：**

```
.scratch/sqlite-to-mysql-migration/plan_migrate_formulas_v03_20260618.md
.scratch/sqlite-to-mysql-migration/plan_restore_v03_context_nodes_20260618.md
.scratch/sqlite-to-mysql-migration/v03_authority_notes_20260618.md
apps/api/app/services/v03_metric_node_catalog.py
apps/api/scripts/import_v03_formulas_to_mysql.py
apps/api/scripts/maintain_v03_metric_workbook.py
apps/api/scripts/restore_v03_context_nodes_to_mysql.py
apps/api/tests/org_product/test_v03_metric_node_catalog.py
```

**注意：** 更早的 MySQL 迁移大 diff（100+ 文件）可能已在其他分支/commit；Codex 应聚焦 **§3 列出的 v03 相关文件 + nature 三文件**。

---

## 6. v03 权威边界（Codex 必核对）

详见 `v03_authority_notes_20260618.md`。核心：

1. **不** 全量 INSERT v03 所有 code（早期「1306 缺失」未扣 stale 规则）
2. **不** 恢复 `.05`（费用老树）/ `.99` / `.90` / `.91`
3. 跨 sheet 重名 → `METRIC_TABLE_CANONICAL_PRIORITY`
4. 利息净收入表 `AA.25.05`/`AA.27.05` 为日均镜像，已从 v03 删除
5. 隐式 GROUP（`AA.24` 等）通过 `IMPLICIT_GROUP_PARENTS` + `repair_implicit_group_nodes` 修复

---

## 7. Codex 检视清单

### 7.1 代码审查

- [ ] `nature` 列 bootstrap 在 SQLite 测试库 / MySQL 均安全（`_ensure_metric_node_v02_columns`）
- [ ] `_node_payload` 在 `nature` 列不存在时是否有 graceful fallback（旧库兼容）
- [ ] `sync_org_product_metric_runtime_refs` 非 overwrite 模式下 nature 更新策略是否合理（仅当 DB 为「其他」/空时覆盖）
- [ ] restore 脚本 INSERT 已含 `nature`；GROUP 插入默认「其他」是否可接受
- [ ] `v03_metric_node_catalog.py` stale / mirror / implicit 规则与 `init_db` purge 不冲突
- [ ] v03 xlsx 二进制 diff 是否与 `maintain_v03_metric_workbook.py` 变更一致

### 7.2 数据验收（MySQL 3307）

```bash
cd apps/api && . .venv/bin/activate

# 公式
python scripts/import_v03_formulas_to_mysql.py --verify-only

# 节点
python scripts/restore_v03_context_nodes_to_mysql.py --verify-only

# 科目性质（幂等，可重复跑）
python scripts/restore_v03_context_nodes_to_mysql.py --backfill-nature

# 分布
python - <<'PY'
import pymysql
from app.core.config import settings
conn = pymysql.connect(host=settings.MYSQL_HOST, port=int(settings.MYSQL_PORT),
    user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD or "",
    database=settings.MYSQL_DATABASE, charset="utf8mb4")
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM data_account_metric_node WHERE is_active=1")
    print("active nodes:", cur.fetchone()[0])
    cur.execute("SELECT nature, COUNT(*) FROM data_account_metric_node WHERE is_active=1 GROUP BY nature ORDER BY 2 DESC")
    for row in cur.fetchall(): print(row)
conn.close()
PY
```

- [ ] active 节点 ≈ **2521**
- [ ] 公式 verify **0 mismatch**
- [ ] nature backfill **0 mismatch**
- [ ] 页面「机构及产品指标」叶子科目性质非全部「其他」

### 7.3 测试

```bash
python -m unittest tests.org_product.test_v03_metric_node_catalog \
                   tests.org_product.test_org_product_metric_runtime_refs -v
# 可选全量：pytest apps/api/tests -q
```

- [ ] 相关单测通过
- [ ] 无新增 `git diff --check` 问题

### 7.4 风险点（请 Codex 显式给出结论）

| 风险 | 问题 |
|------|------|
| GROUP 节点 nature 恒为「其他」 | 前端分组行是否依赖 nature？若依赖，是否需从子节点推断？ |
| 1395 条「其他」 | 是否含应回填但未在 v03 的 METRIC？ |
| schema 变更 | 生产 deploy 是否需先跑 bootstrap 再 `--backfill-nature`？ |
| v03 xlsx 变更 | 是否与业务方确认可入库？ |

---

## 8. 建议 commit 分组（供用户参考，Codex 可调整）

1. **feat(api): v03 metric node catalog + restore/formula scripts**
2. **feat(api): persist metric nature on data_account_metric_node**
3. **chore(data): maintain v03 workbook implicit groups**

---

## 9. Codex 输出格式

请写入：`.scratch/sqlite-to-mysql-migration/codex_review_v03_restore_nature_20260618.md`

结构建议：

1. 验收结论（通过 / 有条件通过 / 不通过）
2. 逐项清单结果（§7）
3. 发现的问题与严重级别
4. 建议用户下一步（commit 范围、是否需 UI 验证、是否补文档）

---

## 10. 快速命令汇总

```bash
cd apps/api && . .venv/bin/activate

python scripts/import_v03_formulas_to_mysql.py --verify-only
python scripts/restore_v03_context_nodes_to_mysql.py --verify-only
python scripts/restore_v03_context_nodes_to_mysql.py --backfill-nature
python -m unittest tests.org_product.test_v03_metric_node_catalog \
                   tests.org_product.test_org_product_metric_runtime_refs -v
```
