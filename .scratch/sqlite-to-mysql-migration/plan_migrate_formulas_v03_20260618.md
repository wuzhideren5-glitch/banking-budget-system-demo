# 计划：从 v03 Excel 导入公式到 MySQL

日期：2026-06-18  
依赖：`.scratch/sqlite-to-mysql-migration/cursor_handoff_20260618_org_product_mysql_data.md`  
权威源：`resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx`

---

## 0. 协作流程

| 步骤 | 角色 | 动作 |
|------|------|------|
| 1 | Cursor | 写本文档 + 实现导入脚本 |
| 2 | Cursor | dry-run → apply → 回填 §5 实测 |
| 3 | Codex | 按 §6 检视清单验收 |
| 4 | 用户 | 确认页面 / 公式重算后 commit |

---

## 1. 现状（2026-06-18 实测）

| 项目 | SQLite `common.db` | MySQL `banking_budget` | v03 Excel（已存在节点） |
|------|-------------------|------------------------|-------------------------|
| 活跃节点 | 2444 | 2444 | — |
| `budget_formula` 非空 | 502 | 502（与 SQLite 逐 code 一致） | 624 有「年预算公式」 |
| `actual_formula` 非空 | 0 | 0 | 503 有「实际月公式」 |
| 仅有「预测月公式」 | — | 0 | 105 |

说明：

- SQLite→MySQL 表迁移已把 **502 条年预算公式** 带入 MySQL，但与 v03 完整口径仍有缺口。
- `sync_org_product_metric_runtime_refs` **不写** `budget_formula` / `actual_formula`（只同步树结构）。
- 前端快照 `_node_payload` 只从 DB 两列映射：`budget_formula`→`formula_budget_annual`，`actual_formula`→`formula_actual`；「预测月公式」无独立 DB 列，需按优先级折叠进 `budget_formula`。

---

## 2. 目标

对 MySQL 中 **已存在的** `data_account_metric_node.node_code`：

1. 从 v03 解析公式（复用 `_parse_metric_worksheet_basic`，按表头定位列，不写死 N 列）
2. 写入 `budget_formula`、`actual_formula`
3. dry-run 输出 diff；apply 后可与 v03 对账

**不在本轮：**

- 新建 v03 有而 MySQL 无的 ~1306 个节点（见 `codex_review_plan_restore_v03_data_20260618.md`）
- 修改 `annual_agg_rule`（另开专项）
- 改 `sync_org_product_metric_runtime_refs` 持久化逻辑（可选后续）

---

## 3. 字段映射规则

| v03 列（表头） | DB 列 | 优先级 / 说明 |
|----------------|-------|----------------|
| 年预算公式 | `budget_formula` | **最高**；与现有 SQLite 502 条一致 |
| 预测月公式 | `budget_formula` | 年预算为空时使用 |
| 取数公式（legacy） | `budget_formula` | 再 fallback |
| 年预测公式 | `budget_formula` | 最后 fallback |
| 实际月公式 | `actual_formula` | 独立写入 |

规范化：trim；空串视为 NULL。

更新策略：

- 仅 `UPDATE` 已存在且 `is_active=1` 的节点
- 若 v03 某 code 无任何公式列 → **跳过**（保留 DB 原值）
- `--overwrite`：即使 DB 已有公式也按 v03 覆盖（默认开启）

---

## 4. 实施步骤

### Step 1：新增脚本

**文件**：`apps/api/scripts/import_v03_formulas_to_mysql.py`

```bash
cd apps/api
. .venv/bin/activate

# dry-run（默认）
python scripts/import_v03_formulas_to_mysql.py --dry-run

# 写入 MySQL
python scripts/import_v03_formulas_to_mysql.py --apply

# 可选：指定 Excel
python scripts/import_v03_formulas_to_mysql.py --apply \
  --workbook ../../resources/business_inputs/机构及产品指标（公式配置）\ -\ v03.xlsx
```

### Step 2：导入后验证

```bash
# 行数统计
python3 - <<'PY'
import pymysql
conn = pymysql.connect(host='127.0.0.1', port=3307, user='root', password='', database='banking_budget')
cur = conn.cursor()
for col in ('budget_formula','actual_formula'):
    cur.execute(f"SELECT COUNT(*) FROM data_account_metric_node WHERE is_active=1 AND TRIM(COALESCE({col},''))!=''")
    print(col, cur.fetchone()[0])
conn.close()
PY

# 与 v03 对账（脚本内置 --verify）
python scripts/import_v03_formulas_to_mysql.py --verify-only
```

预期（约数，以 dry-run 为准）：

| 指标 | 导入前 | 导入后（预期） |
|------|--------|----------------|
| `budget_formula` 非空 | 502 | ~730（502 + 126 年预算缺口 + 105 仅预测） |
| `actual_formula` 非空 | 0 | ~503 |
| v03 已存在节点公式匹配率 | 部分 | ≥99%（按映射规则） |

### Step 3：页面抽测

- 登录 → 机构及产品指标 → 选 A01 / AA 业务状况表
- 抽查有公式的汇总行（如 `A01.01`）是否显示年预算公式
- 若有预算公式重算入口，对单产品试跑无 orphan ref 报错

---

## 5. 实测结果

| 检查项 | 结果 |
|--------|------|
| dry-run diff 条数 | **638**（首轮） |
| apply 更新条数 | **638 + 508**（第二轮修正 Excel 公式转换上下文） |
| `budget_formula` 非空 | **502 → 872** |
| `actual_formula` 非空 | **0 → 503** |
| `--verify-only` | checked=**869**，mismatches=**0** |
| 活跃节点行数 | **2444**（未变） |
| Excel 公式转换告警 | **5**（ArrayFormula 等，已跳过无效 budget，保留 actual） |

抽样（第二轮后，actual 已从 Excel 单元格引用转为系统 code）：

| node_code | budget_formula | actual_formula |
|-----------|----------------|----------------|
| `A01.01` | `A01.01.01+A01.01.02+A01.01.03` | `A01.01.01 + A01.01.02 + A01.01.03` |
| `A01.03` | `A01.01-A01.02` | `A01.01 - A01.02` |
| `A02.16.01.01.04.03` | （空） | `A02.16.01.01.04.02/A02.13.01.01` |

脚本路径：`apps/api/scripts/import_v03_formulas_to_mysql.py`

---

## 6. Codex 检视清单

- [ ] 脚本存在：`apps/api/scripts/import_v03_formulas_to_mysql.py`
- [ ] 使用 `_parse_metric_worksheet_basic`，列按表头解析（非写死 N 列）
- [ ] 映射规则与 §3 一致（年预算 > 预测月 > legacy > 年预测）
- [ ] 只 UPDATE 已存在节点，不 INSERT 新节点
- [ ] dry-run 与 apply 行为一致（apply 才写库）
- [ ] 导入后 `budget_formula` 非空行数 ≥ 850
- [ ] 导入后 `actual_formula` 非空行数 ≥ 500
- [ ] 抽样 10 个 code：`A01.01`、`A01.03`、`AA.29.01` 等与 v03 一致
- [ ] 未破坏既有 2444 节点行数
- [ ] §5 实测已回填

---

## Comments

- 2026-06-18 Cursor：初稿。范围限定为「已存在节点的公式列补齐」，不恢复缺失 node_code。
