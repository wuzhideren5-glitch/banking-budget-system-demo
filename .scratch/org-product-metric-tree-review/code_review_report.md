# 机构及产品列表模块 — 代码检视报告（v2 修正版）

检视人：QoderWork（代码检视角色）
检视日期：2026-06-16
更新日期：2026-06-16（修正 DB 路径错误）

检视依据：
- `.scratch/org-product-tree-review/comments.md`（Codex 评审，6 项）
- `.scratch/org-product-metric-tree-review/comments.md`（Codex 评审，5 项）

检视范围：机构及产品树前端维护、DB 快照、Excel 导入导出、运行产品清单、机构及产品指标树、运行指标同步链路、下游数据录入/预测输出联动

---

## 一、检视方法

本次检视采用三种手段交叉验证：

1. **代码比对**：逐行阅读 comments 涉及的全部源文件，检查是否已有对应修改。
2. **测试运行**：执行 comments 中给出的两套 pytest 命令，记录当前通过/失败数。
3. **DB 状态查询**：直接查询后端实际使用的 DB 文件，验证表结构、行数、字段是否存在。

### v2 修正说明：DB 路径纠错

v1 报告中检视使用了 `apps/var/data/common.db`（一份 2026-06-15 16:34 的旧快照），但后端实际使用的 DB 路径是 `var/data/common.db`（项目根目录下）。路径解析链如下：

```
apps/api/app/config.py
  → REPO_ROOT = Path(__file__).resolve().parents[3]  →  项目根目录
  → data_dir = REPO_ROOT / "var" / "data"            →  项目根/var/data/
  → common_db_path() = settings.data_dir / "common.db"
  → 最终路径: var/data/common.db
```

两份 DB 文件差异巨大：

| 属性 | `var/data/common.db`（后端实际） | `apps/var/data/common.db`（v1 误用） |
|------|------|------|
| 修改时间 | 2026-06-16 19:29（今天） | 2026-06-15 16:34（昨天） |
| 文件大小 | 39 MB | 39 MB |
| MD5 | `83b65b0c944ecaeb2d15ccdf988859a8` | `d39ab4d81f27b26659b86776c14f6dbb` |
| 表数量 | **45** | 47 |
| `org_product_metric_table` | **不存在**（已清理） | 存在，46 行 |
| `data_account_metric_node` 列数 | **26 列**（含全部运行字段） | 16 列（缺运行字段） |
| `data_account_metric_binding` | **view** | table |

v1 报告中关于"代码改了但库没落地"的结论是错的。Bootstrap 已经在正确的 DB 上成功执行过了。以下 v2 报告基于正确 DB 重新验证。

---

## 二、检视涉及文件

| 文件 | 角色 |
|------|------|
| `apps/api/app/routers/org_product_metrics.py` | 后端路由：树保存/导入/指标接口 |
| `apps/api/app/services/org_product_runtime_catalog.py` | 后端服务：运行产品清单同步 |
| `apps/api/app/services/org_product_metric_runtime_sync.py` | 后端服务：指标运行树同步 |
| `apps/api/app/services/org_product_metric_runtime_snapshot.py` | 后端服务：指标 DB 快照还原 |
| `apps/api/app/agent_product_intent.py` | 后端：AI 查询产品意图识别 |
| `apps/api/app/db_bootstrap/schemas.py` | DB 启动：规范 schema 定义 |
| `apps/api/app/db_bootstrap/runtime_metric_tree.py` | DB 启动：运行指标树 bootstrap |
| `apps/api/app/db_bootstrap/retired_deletion.py` | DB 启动：退休表治理 |
| `apps/api/app/init_db.py` | DB 启动：初始化入口 |
| `apps/api/scripts/verify_current_database_inventory.py` | 脚本：DB inventory 验证 |
| `apps/web/src/app/components/OrgProductContent.tsx` | 前端：机构及产品树维护页面 |
| `apps/web/src/app/components/OrgProductMetricContent.tsx` | 前端：机构及产品指标树页面 |
| `apps/web/src/app/components/OrgProductDataEntryContent.tsx` | 前端：数据录入页面 |
| `apps/web/src/app/components/OrgProductForecastOutputContent.tsx` | 前端：预测输出页面 |

---

## 三、机构及产品树检视结果（6 项）

### 3.1 后端树合同强校验

| 项目 | 内容 |
|------|------|
| Comments 问题 | 模块没有把"机构及产品树是主数据"落实到保存门禁。缺少根节点、层级、代码格式、核心节点保护等强校验。 |
| 整改状态 | **未改** |
| 代码现状 | `validate_org_product_tree_contract()` 不存在。保存接口 `/api/org-product-tree/save-refresh`（`org_product_metrics.py`）直接写入 `org_product_tree_snapshot`，只调用 `sync_org_product_runtime_catalog_from_tree()`，该校验仅覆盖空值和重复码。前端 `validateNodeDraft()` 也只校验空值和重复代码。 |
| 风险 | 绕过前端或通过 Excel 导入可产生业务上不合法的树（非法根、层级错乱、非法产品码），错误会通过 CTE 动态展开传播到全部下游模块。 |

### 3.2 删除/改码影响分析

| 项目 | 内容 |
|------|------|
| Comments 问题 | 删除或改码产品树节点不会检查下游引用（指标节点、录入快照、输出快照、预算事实）。 |
| 整改状态 | **未改** |
| 代码现状 | 前端 `handleDeleteCurrent()`（`OrgProductContent.tsx`）仍为简单 confirm dialog。后端保存接口覆盖 `org_product_tree_snapshot` 时不做下游引用检查。不存在 `/api/org-product-tree/save-preview` 影响分析接口。 |
| 风险 | 可能出现"产品树上已删除某产品，但指标和事实还在"的悬挂状态，且无任何提示。 |

### 3.3 sync 函数命名与运行产品清单

| 项目 | 内容 |
|------|------|
| Comments 问题 | `sync_org_product_runtime_catalog_from_tree()` 名称像同步实际没有物化运行表，命名误导。 |
| 整改状态 | **未改** |
| 代码现状 | `org_product_runtime_catalog.py` 函数名不变，仍只做空值/重复校验 + 删除旧 product_type。下游仍依赖 `org_product_runtime_products_cte()` 从 JSON 递归展开。无物化表、无版本号、无健康检查。 |
| 风险 | 命名误导可能让开发者误以为已有独立运行表；JSON 快照一旦损坏，下游全部读取跟着坏。 |

### 3.4 Excel 导入审计

| 项目 | 内容 |
|------|------|
| Comments 问题 | 导入解析兼容多格式，但缺少导入结果审计（节点统计、跳过行、错误行、重复码等）。 |
| 整改状态 | **未改** |
| 代码现状 | 两个导入接口（`/api/org-product-tree/import-excel` 和 `/api/org-product-tree/import-from-base-data`）仍只返回 `{"tree": tree}`，无 summary 或审计信息。前端也不展示任何导入审计信息。 |
| 风险 | 业务人员导入 Excel 后只能靠肉眼看树是否正确，容易漏掉被跳过的行。 |

### 3.5 下游联动依赖前端事件

| 项目 | 内容 |
|------|------|
| Comments 问题 | 数据录入和预测输出监听树保存事件，但依赖的是前端 window event，不是服务端版本。 |
| 整改状态 | **未改** |
| 代码现状 | `OrgProductDataEntryContent.tsx` 和 `OrgProductForecastOutputContent.tsx` 仍监听 `org-product-tree-saved` 事件。`updated_at` 在类型定义中存在但未被用于版本校验。无 `entity_code` 存在性校验，关键提交前不重新拉取树快照。 |
| 风险 | 多人协作或包交付场景中，树可能已被其他用户更新，但当前页面仍保留旧状态，选中产品可能已不存在。 |

### 3.6 agent_product_intent 测试失败

| 项目 | 内容 |
|------|------|
| Comments 问题 | 产品树范围扩展与指标运行引用合同未对齐，4 个测试失败。 |
| 整改状态 | **未改** |
| 测试结果 | 仍 4 failed。 |
| 根因分析 | `_confirmed_org_product_runtime_refs()` 查询 `data_account_metric_node` 时要求 `runtime_account_enabled` 列，但 4 个测试的 fixture 只创建了 6 列的简化表（`node_code, node_name, parent_code, level, node_type, is_active`），缺少 `runtime_account_enabled` 和 `product_code`。查询触发 `sqlite3.Error` 被 `except` 捕获后静默返回空集合，导致 `_lookup_metric_nodes()` 和 `_bindings_for_metric_nodes()` 全部返回空列表。 |
| 修复方向 | 测试 fixture 需要补齐 `runtime_account_enabled` 和 `product_code` 列，使测试数据对齐当前生产 schema。 |
| 风险 | AI 查询、自然语言预算分析、产品范围筛选无法正确从 A 扩展到 A01-A05。 |

---

## 四、机构及产品指标树检视结果（5 项）

### 4.1 退休表 `org_product_metric_table` 治理

| 项目 | 内容 |
|------|------|
| Comments 问题 | 退休表仍存在且有 46 行数据，存在"双主数据"风险。 |
| 整改状态 | **已改（有遗留）** |
| 已做 | 1) `_ensure_metrics_table()` 已改为 no-op（不再创建该表）。2) `sync_existing_org_product_metric_tables()` 迁移函数已写好（读旧行 → 同步运行树 → DROP TABLE）。3) 该函数在 `init_db.py` 第 82 行和第 165 行被调用，每次启动 bootstrap 时都会执行。4) **正确 DB 中该表已不存在** — 迁移已成功完成。 |
| 遗留 | 1) `org_product_metric_table` **未加入** `RETIRED_TABLES`（`retired_deletion.py`），如果未来某处代码意外重建该表，退休表清理机制不会自动删除它。2) `verify_current_database_inventory.py` 能处理该表存在/不存在两种情况，但未将存在本身作为违规条件。 |
| DB 验证 | `var/data/common.db` 中 `org_product_metric_table` → **不存在** |

### 4.2 `functional_group_code` 语义复用

| 项目 | 内容 |
|------|------|
| Comments 问题 | `functional_group_code` 同时表示"指标功能族"和"指标表名"，导致大量伪表。 |
| 整改状态 | **实质改善（代码 + 数据双改善，但代码逻辑仍有风险）** |
| 代码现状 | `org_product_metric_runtime_snapshot.py` 新增了 `_resolve_table_name()` 函数（第 36-44 行），会把 `functional_group_code` 的原始值与 `org_product_metric_table_catalog` 中的白名单比对做校验。SQL 查询也增加了 `COALESCE(functional_group_code, '') <> ''` 过滤（第 144 行），排除空值行。 |
| 数据现状 | 正确 DB 中 `functional_group_code` 分布已大幅改善：`业务状况表`(1775行)、`业务支出评估`(494行)、`资产质量表`(49行)、`利息净收入表`(26行)、`资产负债表（日均）`(24行)、`资产负债表（余额）`(23行)、`损益表`(9行)、空值(36行)。**不再出现** v1 中看到的 "05"(414行)、"14"(138行)、"01"(112行) 等数字码。 |
| 残余风险 | 代码仍用 `functional_group_code` 作为表名分组键。如果未来导入数据再次出现非表名的功能族码，白名单校验依赖 `org_product_metric_table_catalog` 表的存在——如果该 catalog 表不存在，`_valid_table_names()` 返回空集后走 fallback 逻辑，可能放行非法值。 |

### 4.3 `_node_name()` 父节点命名

| 项目 | 内容 |
|------|------|
| Comments 问题 | 同步函数要求隐式父节点必须已有名称，导致 15 个测试失败。 |
| 整改状态 | **已改** |
| 代码现状 | `org_product_metric_runtime_sync.py` 第 398-407 行，`_node_name()` 对中间 GROUP 节点允许以 code 兜底命名（兼容模式）。注释明确策略选择："严格校验放在导入预览层，不在同步层阻断。" |
| 备注 | 评审建议严格模式，代码选择了兼容模式。决策已在注释中记录，能解决测试失败。 |

### 4.4 `allow_manual_entry` 等列 schema 迁移

| 项目 | 内容 |
|------|------|
| Comments 问题 | runtime snapshot 查询假设存在 `allow_manual_entry` 列，但当前库 schema 缺少该列。 |
| 整改状态 | **已改** |
| 代码现状 | `schemas.py` 规范 schema 和 `runtime_metric_tree.py` 的 `_ensure_metric_node_v02_columns()` 迁移逻辑已覆盖所有运行字段。 |
| DB 验证 | 正确 DB (`var/data/common.db`) 中 `data_account_metric_node` 已有 **26 列**，包含：`runtime_account_enabled`(16)、`budget_formula`(17)、`actual_formula`(18)、`budget_rule_code`(19)、`budget_rule_config_json`(20)、`need_calc`(21)、`formula_calc_mode`(22)、`allow_manual_entry`(23)、`value_type`(24)、`annual_agg_rule`(25)。Bootstrap 已成功落地。 |

### 4.5 `data_account_metric_binding` table vs view

| 项目 | 内容 |
|------|------|
| Comments 问题 | `data_account_metric_binding` 应为 VIEW 但部分测试和当前库中仍为物理 TABLE。 |
| 整改状态 | **已改（有测试遗留）** |
| 已做 | `schemas.py` 已定义为 VIEW。`_ensure_metric_binding_view()` 在 bootstrap 中强制 DROP TABLE 再 CREATE VIEW。**正确 DB 中已为 view**。 |
| 遗留 | 6 个测试文件仍用 `CREATE TABLE data_account_metric_binding`：`test_budget_output_display_config.py`、`test_budget_actual_batch_service.py`、`test_expense_forecast_metric_sources.py`、`test_budget_summary_export_service.py`、`test_budget_summary_rebuild.py`。这些测试使用内存 SQLite 创建与规范合同不一致的物理表。 |
| DB 验证 | `var/data/common.db` 中 `data_account_metric_binding` → **view** |

---

## 五、测试运行结果

### 5.1 套件 1：机构及产品树

```
命令：PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_runtime_catalog_router.py \
  apps/api/test_db_bootstrap_current_contracts.py \
  apps/api/test_agent_product_intent_catalog.py

结果：4 failed, 23 passed in 0.66s
```

4 个失败集中在 `test_agent_product_intent_catalog.py`：

| 测试 | 失败原因 |
|------|---------|
| `test_metric_lookup_ignores_orphan_runtime_nodes` | `_lookup_metric_nodes()` 返回空列表，期望 `["A03.01.01.001"]` |
| `test_metric_binding_lookup_ignores_orphan_runtime_bindings` | `_bindings_for_metric_nodes()` 返回空列表，期望 `["A03.01.01.001"]` |
| `test_metric_binding_lookup_expands_parent_product_scope_from_org_product_tree` | `_bindings_for_metric_nodes()` 返回空列表，期望 `["A03"]` |
| `test_catalog_digest_sources_metrics_from_org_product_metric_code` | digest 的 metrics 部分为空 |

**根因**：测试 fixture 的 `data_account_metric_node` 表只有 6 列，缺少 `runtime_account_enabled` 和 `product_code`。`_confirmed_org_product_runtime_refs()` 查询时触发 `sqlite3.Error` 被静默捕获，返回空集合。

### 5.2 套件 2：机构及产品指标树

```
命令：PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_metric_runtime_refs.py \
  apps/api/test_verify_current_database_inventory_script.py

结果：7 failed, 72 passed, 36 warnings in 17.88s
```

与 v1 对比：v1 是 9 failed，v2 是 7 failed。**2 个 canonical_expense_merge 测试已通过**（说明 `_node_name()` 修复生效了），剩余 7 个失败全在 `test_verify_current_database_inventory_script.py`。

7 个失败分布：

| 测试 | 失败原因 |
|------|---------|
| `test_business_data_account_refs_must_point_to_confirmed_org_product_metrics` | 测试创建 `org_product_metric_table` 作为 TABLE 并期望违规，但校验函数已不再从该表读取 |
| `test_canonical_expense_metric_tree_requires_aa_expense_nodes` | 测试创建两种表，期望 `canonical_expense_missing` 违规但未检测到 |
| `test_derived_read_model_data_code_names_must_point_to_confirmed_org_product_metrics` | 同第 1 个，校验行为已变化 |
| `test_metric_identity_contract_fails_for_legacy_corp_prefixed_accounts` | 脚本报 `binding_physical_table_retired` 而测试期望 `data_account_legacy_corp:CORP.00` |
| `test_metric_identity_contract_fails_for_retired_binding_shape` | 脚本报 `binding_physical_table_retired` 而测试期望 `binding_schema_missing` |
| `test_metric_identity_contract_succeeds_for_product_prefixed_accounts` | 期望 returncode=0 但因 `binding_physical_table_retired` 导致 returncode=1 |
| `test_org_product_metric_runtime_refs_fail_when_not_materialized` | 脚本报 `runtime_binding_must_be_view` 而测试期望 `org_product_ref_missing_metric_node` |

**根因**：7 个 inventory 测试都在内存 SQLite 中把 `data_account_metric_binding` 创建为物理 TABLE，但 inventory 脚本已新增了 `binding_physical_table_retired` 检查（binding 必须是 view），该检查优先于测试原本期望的其他违规类型触发，导致测试断言不匹配。

另有 36 个 deprecation warning（openpyxl `cell.font.copy(bold=True)` 用法）。

### 5.3 测试汇总

| 套件 | 通过 | 失败 | v1 对比 |
|------|------|------|---------|
| 套件 1 | 23 | **4** | 不变 |
| 套件 2 | 72 | **7** | v1 是 9 failed，少了 2 个 |
| **合计** | **95** | **11** | v1 是 93 passed / 13 failed |

---

## 六、当前 DB 状态快照（正确路径 `var/data/common.db`）

```sql
SELECT type, name FROM sqlite_master
WHERE name IN ('org_product_tree_snapshot','product_type','org_product_metric_table',
               'data_account_metric_node','data_account','data_account_metric_binding')
ORDER BY name;
```

| name | type | 预期 | 状态 |
|------|------|------|------|
| `org_product_tree_snapshot` | table | table | 正确 |
| `org_product_metric_table` | — | 不存在 | **正确**（已迁移清理） |
| `data_account_metric_node` | table | table | 正确（26 列） |
| `data_account` | view | table 或 view | 已为 view |
| `data_account_metric_binding` | view | view | **正确**（已转为 view） |
| `product_type` | — | 不存在 | 正确（已退休） |

```
org_product_metric_table：不存在（已清理）
data_account_metric_node：26 列（含全部运行字段）
org_product_tree_snapshot：22 节点，4 层（level0-level3），数据干净
```

树结构：
```
AAA 微众集团 (level0)
├── AA 微众银行 (level1)
│   ├── A 个金群 (level2) → A01-A05 (level3)
│   ├── B 企金群 (level2) → B01-B02 (level3)
│   ├── C 数字金融 (level2) → C01-C02 (level3)
│   ├── D 国际业务 (level2) → D01 (level3)
│   ├── E 小鹅导流 (level2) → E01 (level3)
│   └── F 司库及其他 (level2) → F01 (level3)
└── AB 微众科技 (level1)
```

---

## 七、整改状态总览

| 序号 | 模块 | 问题 | 状态 | v1 对比 |
|------|------|------|------|---------|
| 树-1 | 机构及产品树 | 后端树合同强校验 | **未改** | 不变 |
| 树-2 | 机构及产品树 | 删除/改码影响分析 | **未改** | 不变 |
| 树-3 | 机构及产品树 | sync 函数命名/物化 | **未改** | 不变 |
| 树-4 | 机构及产品树 | Excel 导入审计 | **未改** | 不变 |
| 树-5 | 机构及产品树 | 前端服务端版本联动 | **未改** | 不变 |
| 树-6 | 机构及产品树 | agent_product_intent 测试 | **未改** | 不变 |
| 指标-1 | 指标树 | 退休表治理 | **已改（有遗留）** | v1 误判"部分改了" |
| 指标-2 | 指标树 | functional_group_code 语义 | **实质改善（有残余风险）** | v1 误判"未改" |
| 指标-3 | 指标树 | _node_name() 兼容 | **已改** | 不变 |
| 指标-4 | 指标树 | schema 迁移 | **已改** | v1 误判"库未落地" |
| 指标-5 | 指标树 | binding table vs view | **已改（测试遗留）** | v1 误判"测试未统一" |

**修正后完成率：6/11 已改好或有实质改善，5/11 未改。测试 11 failed（v1 是 13 failed）。**

---

## 八、建议修复优先级

| 优先级 | 事项 | 原因 |
|--------|------|------|
| P1 | 后端树合同强校验 | 主数据模块的核心防线，缺失会让非法树污染全部下游 |
| P1 | agent_product_intent 测试修复 | 测试 fixture 补齐 `runtime_account_enabled` + `product_code` 列即可，修复简单 |
| P1 | 统一 inventory 测试的 VIEW 合同 | 7 个测试 fixture 需把 `CREATE TABLE data_account_metric_binding` 改为 `CREATE VIEW` |
| P2 | 删除/改码影响分析 | 防止产品树与指标/事实脱节产生悬挂数据 |
| P2 | Excel 导入审计 summary | 业务人员导入体验的关键缺失 |
| P2 | `org_product_metric_table` 加入 `RETIRED_TABLES` | 防御性措施，防止未来意外重建 |
| P3 | sync 函数命名 | 代码可维护性问题，不影响功能 |
| P3 | 前端服务端版本联动 | 多人协作场景才触发，当前单用户可接受 |
| P3 | functional_group_code 增加独立字段 | 当前数据已改善，但长期应拆分语义 |

---

## 九、检视结论

机构及产品列表模块的 Comments **部分已改完，但仍有重要缺口**。

**指标树模块（5 项）已基本完成**：退休表已清理、schema 已迁移（26 列）、binding 已转为 view、`_node_name()` 兼容模式生效、`functional_group_code` 数据已改善。遗留主要是代码层面的防御性措施（加入 RETIRED_TABLES）和测试 fixture 更新。

**机构及产品树模块（6 项）全部未动**，这是当前最大的缺口。特别是后端树合同强校验和 agent_product_intent 测试修复应作为下一轮优先处理。

当前测试共 **11 个失败**（比 v1 的 13 个少了 2 个），其中 4 个是测试 fixture 缺少列（简单修复），7 个是测试 fixture 的 binding 仍用物理 table（需要统一改为 view）。

建议让虾按 P1 → P2 → P3 顺序处理：先修后端强校验 + 修测试 fixture（共 11 个测试），再补删除影响分析和 Excel 审计，最后处理命名和联动优化。
