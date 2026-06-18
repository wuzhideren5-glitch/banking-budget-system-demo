# Codex Review - Hermes v03 Data Restore Plan

日期：2026-06-18  
被评审文件：`.scratch/sqlite-to-mysql-migration/plan_restore_v03_data_20260618.md`  
评审人：Codex

## 结论

Hermes 计划的方向是对的：连接层迁移通过后，确实还需要补“数据层/业务口径层”的验收，尤其是 v03 指标体系、展示配置、公式引用、年度聚合规则和登录态页面验证。

但当前计划不能直接执行为最终恢复方案。主要问题是：它把部分已经完成的状态误判为未完成，又把真正的大缺口写得太轻。最关键的是，v03 的缺口不是简单 `UPDATE annual_agg_rule`，而是有大量 v03 code 当前不在 MySQL `data_account_metric_node` 中；计划没有设计“恢复缺失指标节点”的步骤。

## 当前实测证据

### 1. 展示配置并非“未重建”

当前 MySQL：

```sql
SELECT display_view, COUNT(*)
FROM budget_output_display_item
WHERE is_active=1
GROUP BY display_view;
```

实测结果：

| display_view | rows |
|---|---:|
| TOTAL | 54 |
| OVERVIEW | 29 |
| PRODUCT.A01 | 134 |
| PRODUCT.A02 | 101 |
| PRODUCT.A03 | 74 |
| PRODUCT.A04 | 87 |
| PRODUCT.A05 | 55 |
| PRODUCT.B01 | 165 |
| PRODUCT.B02 | 199 |
| PRODUCT.C01 | 29 |
| PRODUCT.C02 | 19 |
| PRODUCT.D01 | 19 |
| PRODUCT.E01 | 19 |
| PRODUCT.F01 | 65 |

总数：

```text
budget_output_display_item active rows = 1049
```

因此计划中：

```text
展示报表配置 ❌ 未重建
当前 total_rows=54，远少于完整配置
```

这个判断不准确。`total_rows=54` 是预算输出报表里 TOTAL 视图的展示行数，不是 `budget_output_display_item` 的配置总数。配置总数当前已经是 1049。

### 2. 年度聚合规则不是“完全未导入”

当前 MySQL `data_account_metric_node` 已有 `annual_agg_rule` 列。

实测分布：

| annual_agg_rule | rows |
|---|---:|
| 空 | 1595 |
| AVG | 121 |
| LAST | 139 |
| SUM | 375 |
| WGT | 214 |

所以计划中：

```text
年度聚合规则 ❌ 未导入
```

不准确。更准确的说法是：规则已部分存在，需要和 v03 Excel 做 code 级对账。

### 3. v03 规则列不总是在 N 列

计划写的是：

```text
来源：resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx — N 列（规则）
```

实测 v03 workbook 中，很多产品 sheet 的「规则」列不是 N 列：

| sheet 示例 | 规则列 |
|---|---:|
| AA业务状况表 | 14 |
| A01泛微粒贷 | 14 |
| A02微账户 | 16 |
| B01企业金融 | 16 |
| B02金融市场 | 18 |

正确做法应该按表头文本 `规则` 定位列，而不是写死 N 列。

### 4. 真正缺口：v03 有 1306 个带规则 code 当前不在 MySQL 节点表

按 v03 Excel 的「科目代码」和「规则」表头对账：

```text
v03 unique codes with rule = 2155
rule_counts = SUM 1635, WGT 243, LAST 149, AVG 128
```

和 MySQL `data_account_metric_node` 对账：

```text
mysql_nodes = 2444
matched = 849
missing_code = 1306
empty_rule = 0
mismatch = 0
```

解释：

- 已存在于 MySQL 且有规则的 849 个 code，规则和 v03 匹配。
- 没发现“存在于 MySQL 但 annual_agg_rule 为空”的 v03 code。
- 真正问题是 v03 中 1306 个带规则的 code 在 MySQL 节点表里不存在。

缺失样例：

```text
AA.05.02
AA.05.02.01
AA.05.02.02
AA.49.05
AA.90.01.01.01.001
AA.90.01.01.01.002
AA.90.01.01.02.001
AA.90.01.01.02.002
...
```

这说明恢复方案必须包含“从 v03 恢复/合并缺失指标节点”的设计，不能只做 `annual_agg_rule` UPDATE。

## 主要问题

### P0-1 展示配置的验收口径错误

计划把 API 报表响应的 `total_rows=54` 当作展示配置未完整重建的证据，这是错的。

正确口径应分开：

- 配置完整性：看 `budget_output_display_item` 行数和 `display_view` 分布。
- 报表展示结果：看 `display-report` 的 `total_rows/product_overview_blocks/product_detail_blocks`。

当前配置层是 1049 条，已经接近计划预期。

### P0-2 `rebuild-from-org-product` 路由仍有 MySQL 路径判断风险

`apps/api/app/routers/budget_output.py` 当前逻辑：

```python
budget_path, _, _ = await editable_context_provider()
effective_budget = budget_path if budget_path.exists() else None
```

这在 MySQL 迁移后仍然用 `.db` 文件存在性决定是否传入 `budget_path`。如果后续真正不依赖 SQLite 文件，这里会把 `budget_path` 置空，导致 rebuild 走“无 budget 数据回退”。

这和 Codex 已在 `budget_output_display.py` 中修过的 `_path_available()` 是同类问题。Hermes 计划应先要求修这个判断，再考虑调用 rebuild。

### P0-3 年度规则更新 SQL 过于粗糙，且会覆盖错误对象

计划示例：

```sql
UPDATE data_account_metric_node 
SET annual_agg_rule = CASE 
  WHEN value_type IN ('收入','支出','利润') THEN 'SUM'
  WHEN value_type IN ('资产余额','负债余额') THEN 'LAST'
  WHEN value_type IN ('资产日均','负债日均') THEN 'AVG'
  WHEN value_type = '其他' THEN 'WGT'
  ELSE ''
END
WHERE node_type = 'METRIC' 
  AND (budget_formula IS NULL OR budget_formula = '');
```

问题：

- v03 已有明确「规则」列，应以 Excel 明细为准，不应从 `value_type` 猜。
- 当前 MySQL 与 v03 对账显示没有现有节点规则 mismatch；批量按 value_type 猜规则反而可能破坏已匹配数据。
- `node_type='METRIC'` 未必覆盖所有需要规则的节点；也可能覆盖不应设置规则的节点。
- 计划风险表写“只 UPDATE annual_agg_rule 为空”，但示例 SQL 没有 `annual_agg_rule IS NULL OR annual_agg_rule=''` 条件。

建议：规则导入必须按 `node_code -> rule` 精确 upsert/patch，并先输出 dry-run diff。

### P0-4 计划缺少“恢复缺失 v03 指标节点”的核心步骤

计划标题是：

```text
从 v03 权威源重建完整指标体系
```

但执行步骤没有：

- 解析 v03 workbook 所有 sheet。
- 生成 `data_account_metric_node` 节点树。
- 对比 MySQL 当前节点。
- 对缺失 code 做 insert/merge。
- 对存在但字段不同的节点做受控 update。
- 保护用户曾明确要求保留的 `AA.90` 系列。

现在实测最大的缺口就是 `missing_code=1306`。如果不补这个步骤，计划无法达成“完整指标体系”。

### P1-1 公式验证脚本路径不可执行

计划写：

```text
references/verify-formula-refs.py（在 skill 目录中）
python3 references/verify-formula-refs.py
```

当前工作区没有找到这个文件。仓库中有：

```text
apps/api/app/formula_refs.py
apps/api/services/formula_engine.py
apps/api/tests/org_product/test_formula_refs.py
```

但没有 `references/verify-formula-refs.py`。后续必须明确脚本来源，或新增仓库内可运行脚本，例如：

```text
apps/api/scripts/verify_formula_refs.py
```

### P1-2 `extract_display_codes.py` 不存在

计划写：

```bash
python3 scripts/extract_display_codes.py
```

当前工作区未找到这个脚本。若要保留 Step 2，需要补脚本路径和实现；否则应把它改成“待新增工具”。

### P1-3 API 预期 `total_rows >= 1000` 是错误验收

计划 Step 6 写：

```text
预期：total_rows ≥ 1000，product_blocks 覆盖 12+ 产品
```

这不符合当前 schema 语义。

当前服务层探针返回：

```text
total_rows = 54
product_overview_blocks = 21
product_detail_blocks = 13
```

`total_rows` 是 TOTAL 报表行数，不应等于展示配置总行数 1049。真正应验收：

- `budget_output_display_item` active rows 约 1049。
- `display-report.total_rows` 约 54。
- `display-report.product_overview_blocks` 约 21。
- `display-report.product_detail_blocks` 约 13。
- 如果传入具体 `product_codes`，再验收对应产品明细有数据。

### P1-4 未强调先备份 MySQL 目标表

计划风险里提到“先备份 `budget_output_display_item` 表”，但执行步骤没有把备份作为硬前置。

对任何 destructive rebuild，必须先做：

```sql
CREATE TABLE budget_output_display_item_backup_YYYYMMDDHHMMSS AS
SELECT * FROM budget_output_display_item;
```

同理，如果要恢复/合并 `data_account_metric_node`，也必须先备份：

```sql
CREATE TABLE data_account_metric_node_backup_YYYYMMDDHHMMSS AS
SELECT * FROM data_account_metric_node;
```

## 建议改成的执行顺序

### Step A：冻结当前状态并备份

必须先备份：

- `budget_output_display_item`
- `data_account_metric_node`
- 可能被公式/规则同步影响的绑定表，如 `org_product_data_entry_snapshot_v2`

并记录：

- 当前 MySQL row counts。
- 当前 `migrate_sqlite_to_mysql.py --verify-only` 三段结果。
- 当前预算输出服务层探针结果。

### Step B：做 v03 workbook -> MySQL 节点 diff，只输出报告

新增脚本建议：

```text
apps/api/scripts/diff_v03_metric_tree_to_mysql.py
```

要求：

- 按表头定位列，不写死 N/P/R。
- 输出：
  - v03 code 总数。
  - MySQL code 总数。
  - missing in MySQL。
  - extra in MySQL。
  - same code but different name/parent/product/rule/formula。
  - AA.90 系列单独列出，不能误删。

### Step C：先只补缺失节点，不覆盖已匹配节点

从 v03 补 `data_account_metric_node` 缺失 code。

原则：

- insert missing。
- 对 existing 只做字段级 diff 报告，先不覆盖。
- `annual_agg_rule` 用 v03 明确规则。
- 保护 `AA.90`，不得删除。

### Step D：公式引用验证

新增或定位真实可运行脚本。

建议脚本：

```text
apps/api/scripts/verify_formula_refs.py
```

检查：

- `budget_formula`
- `actual_formula`
- 引用 code 是否存在于 `data_account_metric_node` 或官方运行引用映射。
- 输出 missing refs 和来源节点。

### Step E：展示配置是否需要 rebuild，要先 dry-run

当前配置已经 1049 active rows，不应无脑 rebuild。

建议先做 dry-run：

- 从当前 `data_account_metric_node` 推导 expected display rows。
- 对比当前 `budget_output_display_item`。
- 只在 diff 明确需要时 rebuild。

如果执行 rebuild，先修正路由里的 `budget_path.exists()` 判断，避免 MySQL 模式下误走 fallback。

### Step F：登录态 UI/API 验证

无 cookie curl 会返回 401，不能作为数据为空证据。

建议：

- 用登录 cookie 验证 `/api/budget-output/display-config`。
- 用登录 cookie 验证 `/api/budget-output/display-report?year=2026`。
- 浏览器验证 `8443` 的机构及产品指标页和预算输出展示页。

## 是否建议立即执行 Hermes 计划

不建议按原文直接执行。

建议先修改计划，至少修正以下项后再执行：

1. 把“展示配置未重建”改成“展示配置当前 1049 active rows，需 dry-run 对账确认是否重建”。
2. 把“年度聚合规则未导入”改成“现有 849 个规则与 v03 匹配，但 v03 有 1306 个带规则 code 不在 MySQL，需恢复缺失节点”。
3. 删除“规则在 N 列”的假设，改为按表头 `规则` 定位列。
4. 删除 `total_rows >= 1000` 的验收标准。
5. 增加 v03 -> MySQL 指标节点 diff/merge 步骤。
6. 明确可运行的公式引用验证脚本路径。
7. 把 destructive rebuild 前备份写成强制步骤。
8. 修正 `budget_output.py` 中 `budget_path.exists()` 的 MySQL 运行态判断。

## 推荐下一步产出物

建议把 Hermes 计划升级为：

```text
.scratch/sqlite-to-mysql-migration/plan_restore_v03_data_20260618_v2.md
```

并新增两个脚本计划：

```text
apps/api/scripts/diff_v03_metric_tree_to_mysql.py
apps/api/scripts/verify_formula_refs.py
```

在脚本只读 diff 通过前，不要执行重建或批量 UPDATE。
