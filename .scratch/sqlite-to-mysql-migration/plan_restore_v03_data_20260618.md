# 计划：MySQL 数据层恢复 — 从 v03 权威源重建完整指标体系

日期：2026-06-18
依赖：`.scratch/sqlite-to-mysql-migration/codex_handoff_20260618_mysql_migration.md`
前提：MySQL 连接层迁移已完成（handoff 已确认），但数据层初始化不完整

## 1. 当前状态

| 项目 | 状态 | 说明 |
|---|---|---|
| MySQL 服务 | ✅ 运行中（端口 3307） | banking_budget 库 |
| 后端 | ✅ :8009 | 健康检查通过 |
| 前端 | ✅ :8443 | |
| 连接层迁移 | ✅ | handoff 确认 967 tests passed |
| `data_account_metric_node` | ⚠️ 部分修复 | 已清理 1180 个老 .05 节点，2444 节点与 SQLite 一致 |
| 展示报表配置 | ❌ 未重建 | 当前 `total_rows=54`，远少于完整配置 |
| 公式 | ❌ 未验证 | 未跑 verify-formula-refs.py |
| 年度聚合规则 | ❌ 未导入 | v03 N 列 SUM/AVG/LAST/WGT 未写入 MySQL |
| `init_db.py` 防复发 | ⚠️ 已加 purge | 但未端到端验证 |

## 2. 目标

让 MySQL 的 `banking_budget` 库在**数据层面**达到与 SQLite `common.db` 等价的状态，包括：
- 展示报表配置完整（`budget_output_display_item`）
- 公式引用完整性
- 年度聚合规则
- `init_db.py` 冷启动可自愈

## 3. 执行步骤

### Step 1：展示配置重建

**文件**：`apps/api/app/routers/budget_output.py` — `rebuild_budget_output_display_config_from_org_product_metrics()`

**操作**：
- 调 API `POST /api/budget-output/display-config/rebuild-from-org-product`
- 或直接调 Python 函数（避免 HTTP 鉴权）

**验证**：
```sql
SELECT display_view, COUNT(*) 
FROM budget_output_display_item 
WHERE is_active=1 
GROUP BY display_view;
```
预期：TOTAL ~56, OVERVIEW ~29, PRODUCT.* 各产品 ~50-100

### Step 2：编码 JSON 更新（可选）

**文件**：`var/data/budget_display_codes.json`

**操作**：
```bash
python3 scripts/extract_display_codes.py
```
从 v03 Excel 的 C 列提取编码清单，供 rebuild 使用。

**注意**：如果 JSON 缺失，rebuild 已有 DB 回退逻辑，此步可选。

### Step 3：公式引用完整性验证

**文件**：`references/verify-formula-refs.py`（在 skill 目录中）

**操作**：
```bash
python3 references/verify-formula-refs.py
```

**预期**：零缺失引用。如有缺失，逐条分析并补。

### Step 4：年度聚合规则导入

**来源**：`resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx` — N 列（规则）

**目标表**：`data_account_metric_node.annual_agg_rule`

**规则映射**：
| 科目性质 | 规则 |
|---|---|
| 收入/支出/利润 | SUM |
| 资产余额/负债余额 | LAST |
| 资产日均/负债日均 | AVG |
| 其他（比率等） | WGT |
| 有公式的节点 | 空（不设规则） |

**操作**：
```sql
-- 示例：按科目性质批量设置
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

### Step 5：全量验证

**脚本**：`apps/api/scripts/verify_current_database_inventory.py`

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
```

**预期**：全部通过。

### Step 6：展示报表 API 探针

```bash
# 登录
curl -s -X POST http://127.0.0.1:8009/api/login \
  -H 'Content-Type: application/json' \
  -d '{"user_name":"Kevin","password":"WB12345678"}' -c /tmp/cookies.txt

# 展示报表
curl -s -b /tmp/cookies.txt http://127.0.0.1:8009/api/budget-output/display-report?year=2026 | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'total_rows={len(d[\"total_rows\"])}, product_blocks={len(d[\"product_blocks\"])}, versions={len(d[\"versions\"])}')"
```

**预期**：`total_rows` ≥ 1000，`product_blocks` 覆盖 12+ 产品。

### Step 7：端到端浏览器验证

1. 打开 `http://127.0.0.1:8443`
2. 登录 Kevin / WB12345678
3. 进入「机构及产品指标」页面
4. 确认各产品指标树完整、名称正确
5. 进入「预算输出展示」页面
6. 确认 TOTAL/产品明细报表数据正常

## 4. 风险

| 风险 | 缓解 |
|---|---|
| 展示配置重建覆盖已定制的内容 | 先备份 `budget_output_display_item` 表 |
| 公式引用缺失 | verify-formula-refs.py 逐条检查 |
| 年度聚合规则覆盖 | 只 UPDATE `annual_agg_rule` 为空的 METRIC 行 |
| 服务启动失败 | 每步修改后重启验证 |

## 5. 产出物

- MySQL `budget_output_display_item` 完整配置
- MySQL `data_account_metric_node` 公式 + 聚合规则完整
- `verify_current_database_inventory.py` 通过
- 展示报表 API 返回完整数据
