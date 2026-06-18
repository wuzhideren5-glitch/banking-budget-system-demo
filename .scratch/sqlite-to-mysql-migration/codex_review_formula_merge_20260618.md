# Codex Review: v03 公式合并检视

日期：2026-06-18
检视对象：Cursor/Qoder 后续完成的 v03 公式导入、上下文节点恢复、nature 回填相关改动

## 结论

公式合并的主链路已经基本完成：当前 MySQL 中可匹配到 v03 的公式行与脚本映射结果一致，`--dry-run` 已无待更新 patch，相关 43 个单测通过。

但还不能判定为完全无风险：当前公式引用链仍有 327 个缺失引用，其中 319 个属于已声明不恢复的陈旧分支（`.90` / `.05` / `.99` 等），符合当前 authority note 的边界；另有 8 个不属于陈旧分支的缺失引用需要人工确认或修复。

## 检视板块

### 1. v03 公式导入脚本

代码：
- `apps/api/scripts/import_v03_formulas_to_mysql.py`

映射规则：
- `budget_formula` 优先级：`年预算公式 > 预测月公式 > 取数公式 > 年预测公式`
- `actual_formula`：`实际月公式`

关键代码位置：
- `resolve_v03_db_formulas()`：第 94-101 行
- `build_patches()` 只更新 DB 已存在的 `node_code`：第 254-277 行
- `verify_against_v03()` 只校验 v03 与 DB 都存在的节点：第 326-343 行

验证结果：

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/import_v03_formulas_to_mysql.py --verify-only

formula convert warnings: 7
loaded v03 formula rows: 1324
verified codes: 911
mismatches: 0
```

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/import_v03_formulas_to_mysql.py --dry-run

formula convert warnings: 7
loaded v03 formula rows: 1324
planned patches: 0 (budget=0, actual=0)
budget_formula non-empty: 911
actual_formula non-empty: 523
```

判断：
- 已匹配到 DB 的 v03 公式与当前 MySQL 内容一致。
- 当前 DB 已无脚本可识别的待合并公式差异。
- 注意：这个验证不覆盖 v03 有公式但 DB 不存在的节点，因为脚本按既有节点合并，不负责全量恢复所有 v03 节点。

### 2. v03 上下文节点恢复

代码：
- `apps/api/scripts/restore_v03_context_nodes_to_mysql.py`
- `apps/api/app/services/v03_metric_node_catalog.py`

业务边界：
- `.05` 旧费用树不恢复，但 `A01.14*` 例外保留。
- `.99` / `.90` / `.91` 视为旧分支或已重建分支，不按 v03 全量恢复。
- 相关判断在 `is_v03_stale_node_code()` 第 43-56 行。

验证结果：

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/restore_v03_context_nodes_to_mysql.py --verify-only

v03 parsed nodes: 1373
eligible restore candidates: 1373
mysql active nodes before: 2521
still missing eligible nodes: 0
stale branch nodes present (informational): 1121
```

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python apps/api/scripts/restore_v03_context_nodes_to_mysql.py --dry-run

v03 parsed nodes: 1373
eligible restore candidates: 1373
mysql active nodes before: 2521
group insert plans: 0
metric insert plans: 0
```

判断：
- 按当前 authority note 的口径，应该恢复的 v03 节点已经没有缺口。
- dry-run 已没有新增插入计划。

### 3. nature 回填

代码：
- `apps/api/scripts/restore_v03_context_nodes_to_mysql.py`
- `apps/api/app/db_bootstrap/runtime_metric_tree.py`
- `apps/api/app/services/org_product_metric_runtime_snapshot.py`
- `apps/api/app/services/org_product_metric_runtime_sync.py`

验证结果：

```text
nature_matched 1373
other_or_blank_active 1395
nature_mismatches 0
```

判断：
- v03 可匹配节点的 `nature` 回填与 v03 一致。
- `其他/空` 仍有 1395 个，主要来自非 v03 覆盖范围或陈旧/运行态节点，需要结合业务口径判断，不应简单视为错误。

### 4. 公式引用链完整性

验证结果：

```text
formula_nodes: 915
unique_refs: 1614
missing_ref_count: 327
missing_unique_refs: 324
```

缺失引用分布：

```text
by_second_segment:
90: 301
05: 14
99: 4
50: 4
46: 3
47: 1

stale_flag_counts:
stale: 319
non-stale: 8
```

非陈旧分支缺失引用：

```text
AA.46 -> AA.46.01
AA.46 -> AA.46.02
AA.46 -> AA.46.03
AA.47.01 -> AA.47.01.02
AA.50 -> AA.50.01
AA.50 -> AA.50.02
AA.50 -> AA.50.03
AA.50 -> AA.50.04
```

判断：
- 大部分缺失引用落在当前明确排除的旧分支，和 `v03_authority_notes_20260618.md` 一致。
- 8 个 `AA.46` / `AA.47.01` / `AA.50` 的引用不属于陈旧规则，需要继续确认。
- 如果这些公式参与实际重算，可能出现引用缺失、计算为空或公式结果不完整。

### 5. 公式转换 warning

当前 warning 明细：

```text
AA利息净收入表 row 50: =H33/H16，H16 第 16 行未找到科目代码
AA利息净收入表 row 50: =I33/I16，I16 第 16 行未找到科目代码
A02微账户 row 104: =H107+H110，H110 第 110 行未找到科目代码
A02微账户 row 104: =I107+I110，I110 第 110 行未找到科目代码
A02微账户 row 111: =H110/H42，H110 第 110 行未找到科目代码
A03汽车金融 row 95: =H96+H98，H98 第 98 行未找到科目代码
A03汽车金融 row 95: =I96+I98，I98 第 98 行未找到科目代码
```

判断：
- warning 数量不大，但脚本当前只打印数量，不打印明细。
- 这些 warning 都是 Excel 单元格公式引用到未能识别科目代码的行，应该确认对应行是否是汇总空行、说明行、隐藏行，还是应恢复的真实科目。

### 6. 当前工作区状态

当前工作区仍有未提交或未跟踪文件：

```text
 M apps/api/app/db_bootstrap/runtime_metric_tree.py
 M apps/api/app/services/org_product_metric_runtime_snapshot.py
 M apps/api/app/services/org_product_metric_runtime_sync.py
 M resources/business_inputs/机构及产品指标（公式配置） - v03.xlsx
?? .scratch/sqlite-to-mysql-migration/codex_handoff_20260618_v03_restore_nature.md
?? .scratch/sqlite-to-mysql-migration/plan_migrate_formulas_v03_20260618.md
?? .scratch/sqlite-to-mysql-migration/plan_restore_v03_context_nodes_20260618.md
?? .scratch/sqlite-to-mysql-migration/v03_authority_notes_20260618.md
?? apps/api/app/services/v03_metric_node_catalog.py
?? apps/api/scripts/import_v03_formulas_to_mysql.py
?? apps/api/scripts/maintain_v03_metric_workbook.py
?? apps/api/scripts/restore_v03_context_nodes_to_mysql.py
?? apps/api/tests/org_product/test_v03_metric_node_catalog.py
```

判断：
- 虽然用户口径是“git 都提交了”，但当前 checkout 仍然是 dirty 状态。
- 如果这些改动来自 Cursor，应补一次提交或明确保留为待评审工作区。

## 测试结果

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests/org_product/test_v03_metric_node_catalog.py -q

4 passed in 0.01s
```

```text
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest tests.org_product.test_v03_metric_node_catalog tests.org_product.test_org_product_metric_runtime_refs -v

Ran 43 tests in 1.957s
OK
```

## 问题清单

### P1：仍有 8 个非陈旧缺失引用

问题：
- `AA.46`、`AA.47.01`、`AA.50` 的公式引用了当前 MySQL 不存在、且不在陈旧排除规则内的节点。

建议：
- 查 v03 workbook 中这些节点是否应该恢复。
- 若应该恢复，补充 context node 恢复规则或数据。
- 若不应该恢复，修改对应公式，或在 authority note 中明确这些引用为业务废弃/外部引用。
- 将这 8 个引用加入自动化 verifier，避免后续再次被“mismatches: 0”掩盖。

### P2：公式转换 warning 没有结构化输出

问题：
- `import_v03_formulas_to_mysql.py` 只打印 warning 数量，不打印 sheet/row/formula/reason。

建议：
- 增加 `--report` 或 `--verbose-warnings` 参数，输出 warning 明细到 `.scratch/sqlite-to-mysql-migration/`。
- CI 或人工验收时要求 warning 明细被审阅，而不是只接受数量。

### P2：公式验证范围容易被误读

问题：
- `verify_against_v03()` 只检查 v03 和 DB 同时存在的 `node_code`。
- 它能证明“已存在节点的公式一致”，不能证明“v03 所有公式均已进入 DB”。

建议：
- 增加一类统计：`v03_has_formula_but_db_missing`，并按 stale / non-stale 分类。
- 报告中应明确区分：已合并公式数、跳过陈旧公式数、DB 缺失但非陈旧公式数。

### P3：`formula_calc_mode` / `need_calc` 与公式数量不一致

当前统计：

```text
formula_calc_mode = 1: 502
need_calc = 1: 5
budget_formula 非空: 911
actual_formula 非空: 523
```

问题：
- 如果某些重算链路依赖 `formula_calc_mode` 或 `need_calc`，新导入的公式可能不会被纳入计算。
- 当前 `budget_actual_batch.py` 的批量公式读取主要按公式字段非空筛选，但其他展示、导出、运行态引用链仍会读取这些标志位。

建议：
- 明确业务定义：导入 v03 公式是否应该同步设置 `formula_calc_mode=1` 或 `need_calc=1`。
- 如果不需要，应在迁移说明中写清楚“公式字段是元数据/展示/按需计算入口，非 need_calc 任务标记”。
- 如果需要，应补脚本和回归测试。

## 建议下一步

1. 先处理或确认 8 个非陈旧缺失引用。
2. 给公式导入脚本增加 warning 明细报告。
3. 增加公式引用完整性 verifier，输出 stale/non-stale 分类。
4. 明确 `formula_calc_mode` / `need_calc` 的迁移口径。
5. 在当前 dirty worktree 上补一次提交，或让后续 agent 明确从这些未提交文件继续。

