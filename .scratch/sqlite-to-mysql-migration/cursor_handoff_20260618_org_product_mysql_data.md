# Cursor Handoff — 机构及产品指标 MySQL 数据修复

日期：2026-06-18  
工作区：`/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)`  
文档目录：`.scratch/sqlite-to-mysql-migration/`（本文件）  
前置文档：`.scratch/sqlite-to-mysql-migration/codex_handoff_20260618_mysql_migration.md`

---

## 0. 协作流程（团队约定）

| 步骤 | 角色 | 动作 |
|------|------|------|
| 1 | **Cursor** | 在 `.scratch/<feature-slug>/` 下**先写**项目文档（目标、范围、验收标准、验证命令），再改代码 |
| 2 | **Cursor** | 按文档实施，并在文档中回填「已完成 / 实测结果」 |
| 3 | **Codex** | 按本文 **§6 Codex 检视清单** 逐项验收，结论写入 `codex_review_<同名>.md` |
| 4 | **用户** | 根据 Codex 结论决定 merge、继续下一阶段或回滚 |

本 feature slug：`sqlite-to-mysql-migration`  
相关 PRD：`.scratch/sqlite-to-mysql-migration/prd.md`

---

## 1. 本轮目标

在 Codex 已完成「连接层迁移 + 测试通过」的前提下，修复 **MySQL 数据层** 导致「机构及产品指标」页面异常的问题：

1. 老 `.05` / `.99` 退休分支被启动逻辑写回 MySQL  
2. `metric_table_name` 未从 SQLite 语义迁移，导致指标树读不全、页面退回到 Excel 种子  
3. `logic_code` 等派生字段未在 MySQL 启动时自动补齐  

**不在本轮范围（下一阶段）：**

- 从 v03 Excel 补齐缺失指标节点（约 1306 个 code）  
- 批量导入 `budget_formula` / `actual_formula`  
- 修改 migrate 脚本对 `metric_table_name` 的一次性 backfill（当前由启动自愈）

---

## 2. 问题根因（摘要）

| 现象 | 根因 |
|------|------|
| 指标树多老 `.05` 分支 | `init_db` 启动时 `merge_canonical_expense_metric_trees` 写入退休费用树；purge 曾未稳定生效 |
| 逻辑码不对 / 显示 `-` | MySQL 新增列 `metric_table_name` 为空 → `load_org_product_metric_table_rows_from_runtime_tree` 过滤掉绝大部分节点 → 前端用 Excel 旧格式种子（无逻辑码） |
| 迁移 verify 仍报 hash 警告 | `data_account_metric_node` 在 `TARGET_SUPERSET_TABLES` 中允许多行；且 MySQL 多 `metric_table_name` 列导致 hash 与 SQLite 文件不完全一致 |

---

## 3. 已完成改动

### 3.1 `apps/api/app/init_db.py`

- **移除** 启动时 `merge_canonical_expense_metric_trees_into_org_product_metrics`（不再写回老 `.05` 树）  
- **新增** `_purge_legacy_second_segment_99_nodes`（清理 `A02.99` 等 `*.99.*` 退休分支）  
- **新增** `_purge_legacy_org_product_metric_branches`（统一 purge + 日志）  
- **启动末尾** 调用 `_sync_derived_metric_node_identity`（见 3.2）

### 3.2 `apps/api/app/db_bootstrap/runtime_metric_tree.py`

- **新增** `_sync_derived_metric_node_identity(conn)`：每次启动从 `node_code` 派生  
  - `product_code`  
  - `local_metric_code`  
  - `logic_code`  
  - `level`  
  - `metric_table_name`（当为空时，从非数字的 `functional_group_code` 回填）  
- SQLite 测试路径与 MySQL 路径分别使用兼容 SQL（避免 `SUBSTRING_INDEX` 在 sqlite 测试库失败）

### 3.3 `apps/api/app/services/org_product_metric_runtime_snapshot.py`

- `_node_payload`：当库中 `logic_code` 为空时，按 `node_code` 去产品前缀自动补算

---

## 4. 实测结果（2026-06-18，本机 MySQL 3307）

### 4.1 指标主表行数

| 指标 | SQLite `common.db` | MySQL | 结论 |
|------|-------------------|-------|------|
| `data_account_metric_node` 总行数 | 2444 | 2444 | ✅ 一致 |
| 老 `.05` 费用分支 | 0 | 0 | ✅ |
| `A02.99` 遗留 | 0 | 0 | ✅ |
| 共有 code 字段内容 | — | — | ✅ 0 差异 |

### 4.2 派生字段（修复后）

| 字段 | 说明 |
|------|------|
| `logic_code` | 2425/2425 个非根节点已填充（根节点如 `A01` 为空属正常） |
| `metric_table_name` | 由 2423 空 → **36 空**（与 `functional_group_code` 同为空的源数据节点，如 `A02.17.*`） |
| 连续 3 次 `ensure_databases()` | 行数保持 2444，无 `.05`/`.99` 回流 |

### 4.3 迁移校验

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only common
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only budget --year 2025
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only budget --year 2026
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only compare
```

| 范围 | 结果 |
|------|------|
| budget 2025 / 2026 / compare | ✅ 无错误 |
| common | ⚠️ `data_account_metric_node` row hash mismatch（MySQL 多 `metric_table_name` 列；行数与共有 code 内容已一致） |

### 4.4 单元测试（本轮相关）

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest \
  apps/api/tests/org_product/test_org_product_output_router_contract.py \
  apps/api/tests/org_product/test_runtime_metric_refs.py -q
```

结果：**12 passed**

### 4.5 用户确认

- 用户反馈：机构及产品指标页面 **逻辑码已显示正确**（「现在对了」）

---

## 5. 字段迁移审计（全库对照摘要）

详见对话审计；结论：

| 类别 | 结论 |
|------|------|
| `common.db` 迁移清单内所有表 | ✅ 均在 MySQL；行数与 SQLite 一致（除允许 superset 的表） |
| MySQL 独有列 | 仅 `data_account_metric_node.metric_table_name`（启动自愈，非 migrate 脚本列） |
| 源数据本身为空（非迁移丢失） | `actual_formula` 100% 空；`budget_formula` ~79% 空；`annual_agg_rule` ~65% 空 |
| 预期 MySQL 多出行 | `user_sessions` +4；`intelligent_budget_tasks` +166 |
| 退休表 `SKIP_TABLES` | 当前 `common.db` 无残留数据 |

---

## 6. Codex 检视清单（请逐项打勾）

> Codex 检视完成后，请将结论写入：  
> `.scratch/sqlite-to-mysql-migration/codex_review_cursor_handoff_20260618_org_product_mysql_data.md`

### P0 — 必须通过

- [ ] **P0-1** MySQL `data_account_metric_node` 行数 = SQLite 2444，且无仅 MySQL 存在的 `node_code`（除已文档化的 superset 表策略外）  
- [ ] **P0-2** MySQL 中老 `.05` 费用树节点数 = 0（查询：`node_code LIKE '%.05%' AND ... NOT LIKE '%.90%'` 等，与 `init_db._purge_legacy_aa05_nodes` 一致）  
- [ ] **P0-3** MySQL 中 `*.99.*` 退休分支 = 0（与 `_purge_legacy_second_segment_99_nodes` 一致）  
- [ ] **P0-4** 重启后端 3 次后，上述计数不变（无 merge 回写）  
- [ ] **P0-5** 机构及产品指标 API：`/api/org-product-metrics/db-snapshot` 返回的 `entities` 数量显著大于修复前（修复前约 2 个实体；修复后应接近全量产品）  
- [ ] **P0-6** 抽样 10 个叶子节点：`logic_code` = `node_code` 去掉首段产品前缀（如 `A01.10.01.02` → `10.01.02`）  
- [ ] **P0-7** `init_db.py` 启动路径**不再**调用 `merge_canonical_expense_metric_trees_into_org_product_metrics`  

### P1 — 建议验证

- [ ] **P1-1** `migrate_sqlite_to_mysql.py --verify-only` 四套范围均无 **新增** 失败（common 的 hash 警告可记录为已知限制）  
- [ ] **P1-2** 相关 pytest（§4.4）通过  
- [ ] **P1-3** 页面人工抽检：AA / A01 业务状况表逻辑码列非大面积 `-`  

### P2 — 已知未闭合（不阻塞本轮）

- [ ] **P2-1** v03 缺失指标节点（~1306 code）— 见 `codex_review_plan_restore_v03_data_20260618.md`  
- [ ] **P2-2** `annual_agg_rule` / 公式字段大面积为空 — 源数据缺口，需 v03 导入专项  
- [ ] **P2-3** 36 个 `metric_table_name` 与 `functional_group_code` 双空节点（如 `A02.17.*`）— 需业务确认是否保留  

---

## 7. Codex 建议执行的验证命令

```bash
cd "/Users/penghui/Downloads/kevinchen_20260507_新增预算预测驱动因素模块(2)"

# 行数与 .05/.99
mysql -h127.0.0.1 -P3307 -uroot banking_budget -e "
SELECT COUNT(*) AS total FROM data_account_metric_node;
SELECT COUNT(*) AS fee05 FROM data_account_metric_node
  WHERE node_code LIKE '%.05%' AND node_code NOT LIKE '%.90%' AND node_code NOT LIKE '%.91%' AND node_code NOT LIKE 'A01.14%';
SELECT COUNT(*) AS seg99 FROM data_account_metric_node
  WHERE node_code REGEXP '^[^.]+\\\\.99(\\\\.|$)';
"

# 启动稳定性（3 次）
for i in 1 2 3; do
  PYTHONPATH=apps/api apps/api/.venv/bin/python -c "from app.init_db import ensure_databases; ensure_databases()"
done

# 迁移 verify
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only common
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only budget --year 2026
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/migrate_sqlite_to_mysql.py --verify-only --only compare

# 测试
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest \
  apps/api/tests/org_product/test_org_product_output_router_contract.py \
  apps/api/tests/org_product/test_runtime_metric_refs.py -q

# API（需先登录）
curl -s -X POST http://127.0.0.1:8009/api/login \
  -H 'Content-Type: application/json' \
  -d '{"user_name":"Kevin","password":"WB12345678"}' -c /tmp/cookies.txt
curl -s -b /tmp/cookies.txt http://127.0.0.1:8009/api/org-product-metrics/db-snapshot | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('entities', len(d.get('entities',[])))"
```

---

## 8. 下一阶段建议（给 Codex / 用户）

1. **v03 指标恢复专项**：按 `codex_review_plan_restore_v03_data_20260618.md` 补缺失 `node_code`，不要仅用 `UPDATE annual_agg_rule`  
2. **migrate 脚本增强（可选）**：对 `metric_table_name` 做一次性 backfill，减少依赖启动自愈  
3. **verify 规则收紧（可选）**：`data_account_metric_node` 改为行数相等 + 共有列 hash 一致  

---

## Comments

- 2026-06-18 Cursor：初稿。本轮代码已实施；用户已确认逻辑码页面正确。待 Codex 按 §6 检视。
- 2026-06-18 Cursor（提交前复检）：
  - `migrate --verify-only --only budget --year 2025/2026` → ✅ 无错误
  - `migrate --verify-only --only compare` → ✅ 无错误
  - `migrate --verify-only --only common` → ⚠️ 仅 `data_account_metric_node` hash mismatch（已知：MySQL 多 `metric_table_name` 列；行数 2444=2444，共有 code 内容一致）
  - MySQL 指标节点：total=2444，fee05=0，empty metric_table_name=36
  - 用户要求：迁移 OK 后提交并 push 到 git
