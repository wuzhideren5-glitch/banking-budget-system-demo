# Qoder 审核：项目可删除/清理项清单

审核角色：Qoder  
审核日期：2026-06-16  
文件路径：`.scratch/org-product-metric-tree-review/qoder审核_可删除清理项.md`

---

## 一、代码引用验证结果（逐一 grep 全仓库确认）

| 候选项 | grep 结果 | 结论 |
|--------|----------|------|
| `var/data/compare.db` | `db_paths.py`、`agent_compare_version.py`、`agent_graph.py`、`org_product_metric_runtime_sync.py` 均引用 | ⛔ 不能删 |
| `var/data/budget_2025.db` | `budget_simulation_results.py`、`verify_delivery_package.py`、`test_system_versions_service.py` 等 5+ 文件引用 | ⛔ 不能删 |
| `releases/CTO_20260616_...zip` | 全仓库零引用 | ✅ 可删 |
| 根目录 `机构及产品指标（公式配置）- v01/v02/v02_bak.xlsx` | 代码引用 `resources/business_inputs/` 下的文件，**不是根目录** | ✅ 可删（散落副本） |
| 根目录 `产品指标.xlsx` | 代码引用 `settings.business_inputs_dir / "产品指标.xlsx"` = `resources/business_inputs/产品指标.xlsx`，**不是根目录** | ✅ 可删（散落副本） |
| 根目录 `机构汇总指标表（2）.xlsx` | 代码引用 `resources/business_inputs/机构汇总指标.xlsx`，**不是根目录** | ✅ 可删（散落副本） |
| 根目录 `公式完整性诊断报告.xlsx` | 全仓库零引用 | ✅ 可删 |
| `resources/费用指标树_v4.csv` | 全仓库零引用 | ✅ 可删 |
| `resources/机构产品指标表_v4.xlsx` | 全仓库零引用 | ✅ 可删 |
| `scripts/debug_*.py` | 全仓库零引用（非模块，非 import） | ✅ 可删 |
| `scripts/run_horizontal_rollup.py` | 全仓库零引用 | ✅ 可删 |
| 根目录 DELIVERY_*.md / VERIFY_*.md | 全仓库零引用（仅 DELIVERY_*.md 内部互相提及文件名） | ✅ 可移至 archive |
| `research_papers/` | 全仓库零代码引用 | ✅ 可移至 archive |
| `archive/handover/legacy_import_workbooks/` | 全仓库零代码引用 | ✅ 可删 |
| `archive/handover/data.zip` | 全仓库零代码引用 | ✅ 可删 |
| `archive/handover/legacy_data_account_migrations/` | 全仓库零代码引用 | ✅ 可删 |
| `.superpowers/brainstorm/` | `verify_delivery_package.py` 仅检查 `.superpowers` 目录是否存在，不引用 brainstorm 子目录 | ✅ 可删内容保留目录 |
| `archive/frontend_retired/` | `verify_worktree_organization.py` 检查目录存在和 README，**不能删目录** | ⚠️ 不能删目录，但内容可清理 |
| `var/data/chart_cache/` | `smart_report_service.py` 动态引用 `data_dir / "chart_cache"` | ⛔ 不能删 |

---

## 二、确认可删（零引用，零风险）

### 1. ~~`var/data/compare.db` — 418 MB~~ ⛔ 不能删

**验证后结论：不能删。**
- `db_paths.py` 第 16 行：`return settings.data_dir / "compare.db"` — 代码动态引用
- `agent_compare_version.py`、`agent_graph.py` 都依赖它做多年度对比查询
- 库内有 33 万行数据（compare_budget_summary 133K + compare_pivot_aggregate 198K）
- 删除会导致 AI 对比查询和跨年度分析直接报错

### 2. ~~`var/data/budget_2025.db` — 4.7 MB~~ ⛔ 不能删

**验证后结论：不能删。**
- `budget_simulation_results.py` 第 105 行：`year_2025_path = common_path.parent / "budget_2025.db"` — 动态按年份查找
- `verify_delivery_package.py`、`verify_current_database_inventory.py` 都期望它存在
- `system_versions_service` 和 `global_refresh_status` 都会读写它
- 代码按 `{year}.db` 模式动态查找，删了会报错

### 3. `releases/CTO_20260616_full_runtime_env_data_dist.zip` — 54 MB ✅

全仓库零引用。交付 zip 包，磁盘占 54 MB。

```bash
rm releases/CTO_20260616_full_runtime_env_data_dist.zip
```

### 4. 根目录旧版本 Excel 文件 — 共 ~370 KB ✅

代码引用路径是 `resources/business_inputs/产品指标.xlsx` 和 `resources/business_inputs/机构汇总指标.xlsx`，**不是根目录**。根目录的是散落副本，零引用。

```bash
mkdir -p archive/root_excel_cleanup
mv "机构及产品指标（公式配置） - v01.xlsx" archive/root_excel_cleanup/
mv "机构及产品指标（公式配置） - v02.xlsx" archive/root_excel_cleanup/
mv "机构及产品指标（公式配置） - v02_bak.xlsx" archive/root_excel_cleanup/
mv "机构汇总指标表（2）.xlsx" archive/root_excel_cleanup/
mv "产品指标.xlsx" archive/root_excel_cleanup/
mv "公式完整性诊断报告.xlsx" archive/root_excel_cleanup/
```

### 5. 根目录历史交付/发布文档 — 共 ~30 KB ✅

全仓库零代码引用，仅内部互相提及文件名。

| 文件 | 大小 |
|------|------|
| `DELIVERY_20260607_runtime_package.md` | 1.9K |
| `DELIVERY_20260609_runtime_package.md` | 2.1K |
| `DELIVERY_20260610_full_runtime_package.md` | 2.2K |
| `DELIVERY_20260611_full_runtime_single_metric_package.md` | 2.1K |
| `DELIVERY_20260615_full_runtime_package.md` | 2.0K |
| `RELEASE_NOTE_TeamSubmitRuntime_20260606_...md` | 2.0K |
| `VERIFY_20260611_full_runtime_single_metric_package.md` | 2.0K |

```bash
mv DELIVERY_*.md archive/releases/
mv RELEASE_NOTE_*.md archive/releases/
mv VERIFY_*.md archive/releases/
```

### 6. `research_papers/` — 6.6 MB ✅

全仓库零代码引用。学术论文 PDF，对运行无影响。

```bash
# 移到 archive 或外部存储
mv research_papers archive/
```

### 7. `resources/费用指标树_v4.csv` — 115 KB ✅

全仓库零引用。已有 `.xlsx` 版本。

```bash
rm resources/费用指标树_v4.csv
```

### 8. `resources/机构产品指标表_v4.xlsx` — 213 KB ✅

全仓库零引用。已有 v5。

```bash
rm resources/机构产品指标表_v4.xlsx
```

### 9. `scripts/debug_*.py` + `scripts/run_horizontal_rollup.py` ✅

全仓库零 import、零调用。一次性调试脚本。

```bash
rm scripts/debug_rebuild.py scripts/debug_rollup_plan.py scripts/debug_write.py
```

---

## 三、可归档整理（零引用，极低风险）

### 10. `archive/handover/legacy_import_workbooks/` ✅

全仓库零代码引用。遗留导入工作簿和照片。

```bash
# 如果确认不再需要，可直接删除
rm -rf archive/handover/legacy_import_workbooks/
```

### 11. `archive/handover/data.zip` — 1.3 MB ✅

全仓库零代码引用。

```bash
rm archive/handover/data.zip
```

### 12. `archive/handover/legacy_data_account_migrations/` ✅

全仓库零代码引用。迁移已完成。

```bash
rm -rf archive/handover/legacy_data_account_migrations/
```

### 13. `.superpowers/brainstorm/` ✅（删内容，保留 .superpowers 目录）

`verify_delivery_package.py` 第 54 行检查 `.superpowers` 目录存在，但不管子目录内容。

```bash
rm -rf .superpowers/brainstorm/
```

---

## 四、不能删的项（有代码引用）

| 文件 | 引用它的代码 |
|------|-------------|
| `var/data/compare.db` | `db_paths.py`、`agent_compare_version.py`、`agent_graph.py`、`org_product_metric_runtime_sync.py` |
| `var/data/budget_2025.db` | `budget_simulation_results.py`、`verify_delivery_package.py`、`test_system_versions_service.py` 等 |
| `var/data/chart_cache/` | `smart_report_service.py` 动态创建和读取 |
| `archive/frontend_retired/` 目录 | `verify_worktree_organization.py` 检查目录结构 |

---

## 五、代码层面的可清理项（低风险，需验证）

### 14. `_ensure_metrics_table()` — no-op 死代码 ✅

`org_product_metrics.py` 第 321 行定义了一个空函数：

```python
def _ensure_metrics_table(conn: sqlite3.Connection) -> None:
    """org_product_metric_table has been retired; this is a no-op to preserve call sites."""
```

第 1062 行仍然调用它。可以删除函数和调用点。

### 15. `archive/frontend_retired/` 内容 — 97 KB ⚠️

`verify_worktree_organization.py` 检查目录存在和 README.md，**不能删目录**，但 `ProductBudgetWorkbenchContent.tsx` 等具体组件文件可删（零代码引用）。

---

## 六、清理收益汇总

| 类别 | 数量 | 回收空间 | 风险 | 验证方式 |
|------|------|---------|------|----------|
| 交付 zip | 1 个 | **54 MB** | 零 | grep 零引用 |
| 旧 Excel/Doc/PDF（根目录散落副本） | 10 个 | ~1.5 MB | 零 | grep 确认代码引用 resources/ 下，非根目录 |
| 历史文档 MD | 7 个 | ~30 KB | 零 | grep 零引用 |
| 学术论文 PDF | 9 个 | **6.6 MB** | 零 | grep 零代码引用 |
| 重复/调试文件 | ~10 个 | ~130 KB | 零 | grep 零 import |
| 归档遗留文件 | ~50 个 | ~3 MB | 极低 | grep 零引用 |
| 代码死代码 | 1 处 | ~0.5 KB | 低 | 函数体为空，仅 1 个调用点 |
| **合计** | | **~65 MB** | | |

加上 Git 历史瘦身（.git/objects 944 MB），总回收约 **1 GB**。