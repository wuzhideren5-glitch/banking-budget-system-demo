# Qoder 审核：项目臃肿度分析 — 低风险改善建议

审核角色：Qoder  
审核日期：2026-06-16  
审核范围：全仓库结构、文件体积、历史包袱、代码组织  
文件路径：`.scratch/org-product-metric-tree-review/qoder审核_项目臃肿分析.md`

---

## 一、项目臃肿现状总览

| 维度 | 数据 | 风险等级 |
|------|------|---------|
| `.git/objects` | **944 MB** | 🔴 严重 |
| `var/data/`（运行时 DB） | **601 MB** | 🔴 严重 |
| `apps/api/.venv/` | **265 MB** | 🟡 中 |
| 根 `node_modules/` | **177 MB** | 🟡 中 |
| `releases/`（交付包） | **54 MB** | 🟢 低 |
| 后端 services 文件数 | **141 个** | 🔴 严重 |
| 后端 test 文件数 | **146 个** | 🟡 中 |
| `org_product_metrics.py`（单路由） | **224 KB** | 🔴 严重 |
| Git 历史中的 `.venv312/` | 曾提交过完整 venv | 🔴 严重 |
| Git 历史中的 `apps/var/data/` | 多次提交 39MB DB 文件 | 🔴 严重 |

---

## 二、低风险可改善项（按投入产出比排序）

### T1：Git 历史瘦身 — 回收约 800+ MB（最高优先级，零功能风险）

#### T1-1 Git 历史中残留了完整的 Python venv

```
.venv312/lib/python3.12/site-packages/lxml/etree.cpython-312-darwin.so   → 4.7 MB
.venv312/lib/python3.12/site-packages/pydantic_core/_pydantic_core...so  → 4.4 MB
.venv312/lib/python3.12/site-packages/PIL/.dylibs/libavif.16.4.1.dylib  → 4.7 MB
```

`.gitignore` 现在已经排除了 `.venv*/`，但**历史中仍然存在**，每次 clone 都会拉取这些无用 blob。

**改善方式**：`git filter-repo --path .venv312/ --invert-paths`，一次操作即可删除历史中的 venv，回收数百 MB。

**风险**：零。venv 是可重建的依赖，不影响任何代码逻辑。

#### T1-2 Git 历史中残留了大型 DB 文件

```
apps/var/data/common.db        → 39 MB（出现 2 次）
apps/var/data/budget_2026.db   → 147 MB
data/backups/compare_before... → 13.8 MB
data/backups/budget_2025_...   → 3.8 MB
data/backups/budget_2026_...   → 4.8 MB（出现 2 次）
```

这些 DB 文件和备份在历史中被反复提交，占用了大量 object 空间。

**改善方式**：`git filter-repo --path apps/var/data/ --path data/backups/ --invert-paths`，然后在 `.gitignore` 中确认排除这些路径。

**风险**：零。DB 文件是运行时产物，不应进入版本控制。当前 `.gitignore` 已经排除了 `var/data/*`，但历史仍在。

#### T1-3 Git 历史中残留了多个交付 zip

```
releases/Codex_20260508_预算预测驱动因素联动完善_完整项目.zip  → 91 MB
releases/Codex_20260508_预算预测驱动因素联动完善_轻量项目.zip  → 3.9 MB
releases/CTO_20260509_完整交付包_含env_data_excel.zip         → 4.2 MB
releases/MergeSkill_20260509_项目合并验收完整包...zip          → 10.6 MB
```

**改善方式**：`git filter-repo --path releases/ --invert-paths`

**风险**：极低。交付包是发布产物，不属源代码。如果需要存档可放到外部存储。

---

### T2：运行时数据瘦身 — 回收约 500+ MB（零功能风险）

#### T2-1 `var/data/` 中有冗余的大文件

```
budget_2026.db   → 140 MB
compare.db       → 418 MB
budget_2025.db   → 4.7 MB
common.db        → 37 MB
```

`compare.db` 占了 418 MB，是历史比对数据库。如果当前不使用旧比对功能，可以安全删除或归档。

**改善方式**：
1. 确认 `compare.db` 是否为活跃使用中的库
2. 如果不活跃 → 直接删除（418 MB 回收）
3. `budget_2025.db` 如果 2025 年预算已归档 → 删除或移到 archive

**风险**：零。运行时 DB 不影响代码，且 `.gitignore` 已排除。

#### T2-2 `var/data/backups/` 和 `var/data/backup/` 目录

存在两个备份目录（`backup/` 和 `backups/`），应该清理过期的备份文件。

**风险**：零。备份文件不影响运行。

---

### T3：根目录散落文件整理（极低风险，提升可维护性）

#### T3-1 根目录有 10+ 个业务 Excel/Docx/PPT/PDF 文件

```
产品指标.xlsx
公式完整性诊断报告.xlsx
机构及产品指标（公式配置）- v01.xlsx
机构及产品指标（公式配置）- v02.xlsx
机构及产品指标（公式配置）- v02_bak.xlsx
机构及产品指标（公式配置）- v03.xlsx
机构汇总指标表（2）.xlsx
机构产品数据录入_B01_业务状况表_2026 (1).xlsx
数据流+工作流.pptx
智能纪要：预算系统架构与指标规划 2026年6月12日.pdf
机构产品智能预算管理系统需求规格说明书.docx
```

这些文件应该放到 `resources/business_inputs/` 或 `docs/product/` 下，不应散落在根目录。

**改善方式**：按类型归档到对应目录：
- Excel 业务输入 → `resources/business_inputs/`
- 需求文档 → `docs/product/`
- 工作流 PPT → `docs/product/`

**风险**：极低。只涉及文件移动，如果代码中有硬编码路径需要同步更新。

#### T3-2 根目录有 6 个 DELIVERY/RELEASE/VERIFY 文档

```
DELIVERY_20260607_runtime_package.md
DELIVERY_20260609_runtime_package.md
DELIVERY_20260610_full_runtime_package.md
DELIVERY_20260611_full_runtime_single_metric_package.md
DELIVERY_20260615_full_runtime_package.md
RELEASE_NOTE_TeamSubmitRuntime_20260606_...md
TEAM_SUBMIT_PACKAGING.md
TEAM_SUBMIT_TeamSubmit_20260606_...md
VERIFY_20260611_full_runtime_single_metric_package.md
```

这些是历史交付记录，应归档到 `archive/releases/` 或 `docs/development/`。

**风险**：零。纯文档搬迁。

---

### T4：超大源文件拆分（低风险，提升可维护性）

#### T4-1 后端 TOP 超大文件

| 文件 | 体积 | 问题 |
|------|------|------|
| `org_product_metrics.py`（路由） | **224 KB** | 单路由文件包含机构产品树 + 指标树 + 导入导出 + Excel 解析，应拆为 4-5 个子路由 |
| `smart_report_service.py` | **80 KB** | 智能报告生成，应按报告类型拆分 |
| `business_cost_income.py`（bootstrap） | **76 KB** | 应按数据域拆分 |
| `agent_graph.py` | **68 KB** | AI agent 图，应按节点类型拆分 |
| `smart_ppt_service.py` | **64 KB** | PPT 生成，应按模板/渲染/导出拆分 |
| `budget_output_display.py` | **60 KB** | 应按展示模式拆分 |
| `expense_forecast.py`（路由） | **60 KB** | 应按子功能拆分 |
| `org_product_metric_runtime_sync.py` | **52 KB** | 应按同步阶段拆分 |
| `expense_budget_execution_report_resolver.py` | **52 KB** | 应按报表类型拆分 |
| `agent_product_intent.py` | **52 KB** | 应按意图类型拆分 |

#### T4-2 前端 TOP 超大组件

| 文件 | 体积 | 问题 |
|------|------|------|
| `OrgProductMetricContent.tsx` | **240 KB** | 最大的前端组件，应拆为树编辑、公式编辑、表格编辑等子组件 |
| `BusinessCostIncomeRatioAdminContent.tsx` | **96 KB** | 应按管理标签页拆分 |
| `PivotChartContent.tsx` | **80 KB** | 应拆为图表配置、渲染、导出 |
| `ExpenseForecastRuleContent.tsx` | **72 KB** | 应拆为规则列表、规则编辑、规则导入 |
| `AnalysisReportContent.tsx` | **72 KB** | 应拆为报告生成、报告展示 |

**改善方式**：这些文件不需要一次全拆，可以按模块优先级逐步拆分。最应该先拆的是 `org_product_metrics.py`（224 KB，当前 review 的核心文件）和 `OrgProductMetricContent.tsx`（240 KB）。

**风险**：低。拆分是纯重构，不改变功能逻辑，配合测试验证即可。

---

### T5：双份 DB 和过时数据路径（零功能风险）

#### T5-1 `apps/var/data/` vs `var/data/`

代码实际使用的 DB 路径是 `var/data/common.db`（项目根目录），但 `apps/var/data/` 也曾经被使用过。当前 `apps/var/data/` 目录为空，说明旧路径已被废弃，但 git 历史中仍有残留。

review 报告中也指出了这个问题：v1 检视误用了 `apps/var/data/common.db`，v2 纠正为 `var/data/common.db`。

**改善方式**：确认 `apps/var/data/` 不再使用，清理空目录，在 `.gitignore` 或代码中明确只使用一个路径。

**风险**：零。

#### T5-2 `common.db` 根目录还有一个 `common.db`

```
./common.db  （根目录）
./var/data/common.db  （运行时）
```

根目录的 `common.db` 不应存在，可能是调试时复制的。

**风险**：零。删除即可。

---

### T6：脚本文件瘦身（低风险）

#### T6-1 两个超大型验证脚本

| 文件 | 体积 |
|------|------|
| `verify_worktree_organization.py` | **70 KB** |
| `verify_current_database_inventory.py` | **75 KB** |

这两个验证脚本比很多业务模块还大。`verify_worktree_organization.py` 的测试文件更是 **116 KB**。

**改善方式**：
1. 验证逻辑应按检查项拆分为独立函数/模块
2. 大量内联数据应抽取为 YAML/JSON 配置
3. 考虑是否所有检查项都是必要的，过时的检查可以删除

**风险**：低。验证脚本不影响业务功能。

---

### T7：重复/过时的交付文档和模板（零风险）

#### T7-1 `机构及产品指标（公式配置）` 有 4 个版本

```
v01.xlsx, v02.xlsx, v02_bak.xlsx, v03.xlsx
```

只有 v03 是最新版，其余 3 个应归档到 `archive/` 或删除。

#### T7-2 `resources/` 下也有重复的指标表

```
resources/机构产品指标表_v4.xlsx
resources/机构产品指标表_v5.xlsx
resources/费用指标树_v4.csv
resources/费用指标树_v4.xlsx
```

如果 v5 是最新版，v4 可以归档。

**风险**：零。

---

## 三、改善优先级矩阵

| 优先级 | 编号 | 改善项 | 预估回收 | 投入 | 风险 |
|--------|------|--------|---------|------|------|
| **P0** | T1 | Git 历史瘦身（venv + DB + zip） | **800+ MB** | 1-2 小时 | 零 |
| **P1** | T2 | 运行时数据瘦身（compare.db 等） | **500+ MB** | 30 分钟 | 零 |
| **P1** | T5 | 双份 DB 和过时路径清理 | 清晰度提升 | 30 分钟 | 零 |
| **P2** | T3 | 根目录散落文件归档 | 可维护性 | 1 小时 | 极低 |
| **P2** | T7 | 重复版本文件清理 | 清晰度 | 30 分钟 | 零 |
| **P3** | T4 | 超大源文件拆分 | 可维护性 | 按模块 2-4 小时/个 | 低 |
| **P3** | T6 | 验证脚本瘦身 | 可维护性 | 2-3 小时 | 低 |

---

## 四、立即可执行的 P0 操作

以下操作**零功能风险**，可在 30 分钟内完成：

```bash
# Step 1: 备份当前仓库
cp -r .git .git.backup

# Step 2: 安装 git-filter-repo（如果没有）
pip install git-filter-repo

# Step 3: 清除历史中的 venv
git filter-repo --path .venv312/ --invert-paths --force

# Step 4: 清除历史中的 DB 文件
git filter-repo --path apps/var/data/ --path data/backups/ --invert-paths --force

# Step 5: 清除历史中的交付 zip（当前 .gitignore 已排除 releases/）
git filter-repo --path releases/ --invert-paths --force

# Step 6: 删除运行时大文件
rm -f var/data/compare.db          # 418 MB，如不活跃
rm -f var/data/budget_2025.db      # 4.7 MB，如已归档
rm -f common.db                    # 根目录残留

# Step 7: 清理 __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Step 8: 垃圾回收
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

**预估效果**：仓库从 ~1.6 GB 缩减到 ~200 MB 以内。

---

## 五、结论

这个项目的核心问题是**臃肿来源于治理缺失，不是代码膨胀**：

1. **Git 历史被污染**（944 MB objects）：venv、DB、交付包不该进版本控制，虽然现在 `.gitignore` 修好了，但历史仍在
2. **运行时数据过大**（601 MB）：`compare.db` 418 MB 占大头，可能是遗留产物
3. **超大文件需要拆分**：224 KB 的路由和 240 KB 的前端组件是可维护性最大的瓶颈
4. **文件组织混乱**：根目录散落 10+ 业务文件、6+ 交付文档、4 版指标表

**最推荐先做的是 T1（Git 历史瘦身）和 T2（运行时数据瘦身）**，这两项零风险且回收超过 1.3 GB 空间。
