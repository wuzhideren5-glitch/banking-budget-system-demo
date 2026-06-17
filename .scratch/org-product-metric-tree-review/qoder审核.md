# Qoder 审核：机构与产品指标体系表 Review 整改评估

审核角色：Qoder（第三方审核）  
审核日期：2026-06-16  
审核对象：龙虾对 Codex Review Comments 的整改情况  
审核依据：
- `.scratch/org-product-tree-review/comments.md`（Codex 评审，6 项）
- `.scratch/org-product-metric-tree-review/comments.md`（Codex 评审，5 项）
- `.scratch/org-product-metric-tree-review/code_review_report.md`（v2 检视报告）
- `.scratch/org-product-metric-tree-review/review_status_report.md`（整改状态报告）

审核方法：阅读全部 Review 文档 + 实际运行两套测试 + 查询正确 DB（`var/data/common.db`）

---

## 一、总体结论

**龙虾尚未改完，还有重要缺口。**

Codex 共提出 **11 项问题**（机构及产品树 6 项 + 指标树 5 项），当前整改完成率约 **55%**（6/11 已改好或有实质改善），仍有 **5 项完全未动**。测试共 **11 个失败**。

---

## 二、机构及产品树模块（6 项）— 全部未改 ⛔

| # | 问题 | 状态 | 当前代码现状 |
|---|------|------|-------------|
| 树-1 | 后端树合同强校验 | **未改** | `validate_org_product_tree_contract()` 不存在。保存接口 `/api/org-product-tree/save-refresh` 只校验空值和重复码，无根节点、层级、代码格式、核心节点保护等强校验 |
| 树-2 | 删除/改码影响分析 | **未改** | 无 `/api/org-product-tree/save-preview` 接口。前端 `handleDeleteCurrent()` 仍为简单 confirm，后端不做下游引用检查 |
| 树-3 | sync 函数命名误导 | **未改** | `sync_org_product_runtime_catalog_from_tree()` 函数名不变，仍无物化运行表、无版本号、无健康检查 |
| 树-4 | Excel 导入审计 | **未改** | 两个导入接口仍只返回 `{"tree": tree}`，无 summary 或审计信息 |
| 树-5 | 前端服务端版本联动 | **未改** | 仍依赖 `org-product-tree-saved` window event，无 `updated_at` 版本校验、无 `entity_code` 失效拦截 |
| 树-6 | agent_product_intent 测试 | **未改** | **4 个测试仍然失败**，根因：fixture 的 `data_account_metric_node` 表只有 6 列，缺少 `runtime_account_enabled` 和 `product_code` |

**模块小结**：机构及产品树是当前最大缺口，6 项评审问题全部未动。该模块作为预算系统产品主数据入口，缺少后端合同校验意味着非法树可通过 Excel 导入或 API 直接写入，错误会通过 CTE 传播到全部下游。

---

## 三、机构及产品指标树模块（5 项）— 基本完成 ✅

| # | 问题 | 状态 | 详细说明 |
|---|------|------|---------|
| 指标-1 | 退休表 `org_product_metric_table` 治理 | **已改（有遗留）** | 正确 DB 中该表已不存在，`_ensure_metrics_table()` 改为 no-op，迁移函数已写好并在 init_db.py 中调用。遗留：未加入 `RETIRED_TABLES`，`verify_current_database_inventory.py` 未将表存在本身作为违规条件 |
| 指标-2 | `functional_group_code` 语义复用 | **实质改善（有残余风险）** | 新增 `_resolve_table_name()` 白名单校验 + `COALESCE(functional_group_code, '') <> ''` 过滤。正确 DB 中数字码伪表已消除。残余：代码仍用 `functional_group_code` 作为表名分组键，catalog 表不存在时白名单 fallback 可能放行非法值 |
| 指标-3 | `_node_name()` 父节点命名 | **已改** | 允许 code 兜底命名（兼容模式），注释记录策略选择"严格校验放在导入预览层，不在同步层阻断" |
| 指标-4 | `allow_manual_entry` schema 迁移 | **已改** | 正确 DB `data_account_metric_node` 已有 26 列（含 `runtime_account_enabled`、`allow_manual_entry`、`value_type` 等），bootstrap 已成功落地 |
| 指标-5 | binding table vs view | **已改（测试遗留）** | 正确 DB 中 `data_account_metric_binding` 已为 view。遗留：6 个测试文件仍用 `CREATE TABLE` 而非 `CREATE VIEW` |

**模块小结**：指标树模块核心问题已修复，退休表清理、schema 迁移、binding 转 view、白名单校验均已完成。遗留项主要是防御性措施和测试 fixture 统一。

---

## 四、测试验证结果（2026-06-16 实际运行）

### 套件 1：机构及产品树

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_runtime_catalog_router.py \
  apps/api/test_db_bootstrap_current_contracts.py \
  apps/api/test_agent_product_intent_catalog.py

结果：4 failed, 23 passed in 0.64s
```

4 个失败全在 `test_agent_product_intent_catalog.py`：

| 测试 | 失败原因 |
|------|---------|
| `test_metric_lookup_ignores_orphan_runtime_nodes` | `_lookup_metric_nodes()` 返回空列表，期望 `["A03.01.01.001"]` |
| `test_metric_binding_lookup_ignores_orphan_runtime_bindings` | `_bindings_for_metric_nodes()` 返回空列表，期望 `["A03.01.01.001"]` |
| `test_metric_binding_lookup_expands_parent_product_scope_from_org_product_tree` | `_bindings_for_metric_nodes()` 返回空列表，期望 `["A03"]` |
| `test_catalog_digest_sources_metrics_from_org_product_metric_code` | digest 的 metrics 部分为空 |

**根因**：测试 fixture 的 `data_account_metric_node` 表只有 6 列，缺少 `runtime_account_enabled` 和 `product_code`。`_confirmed_org_product_runtime_refs()` 查询触发 `sqlite3.Error` 被静默捕获，返回空集合。

### 套件 2：机构及产品指标树

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_metric_runtime_refs.py \
  apps/api/test_verify_current_database_inventory_script.py

结果：7 failed, 72 passed, 36 warnings in 14.59s
```

7 个失败全在 `test_verify_current_database_inventory_script.py`：

| 测试 | 失败原因 |
|------|---------|
| `test_business_data_account_refs_must_point_to_confirmed_org_product_metrics` | 测试创建 `org_product_metric_table` 为 TABLE，但校验函数已不再从该表读取 |
| `test_canonical_expense_metric_tree_requires_aa_expense_nodes` | 测试创建两种表，期望 `canonical_expense_missing` 违规但未检测到 |
| `test_derived_read_model_data_code_names_must_point_to_confirmed_org_product_metrics` | 同第 1 个 |
| `test_metric_identity_contract_fails_for_legacy_corp_prefixed_accounts` | 脚本报 `binding_physical_table_retired` 而测试期望 `data_account_legacy_corp:CORP.00` |
| `test_metric_identity_contract_fails_for_retired_binding_shape` | 脚本报 `binding_physical_table_retired` 而测试期望 `binding_schema_missing` |
| `test_metric_identity_contract_succeeds_for_product_prefixed_accounts` | 期望 returncode=0 但因 `binding_physical_table_retired` 导致 returncode=1 |
| `test_org_product_metric_runtime_refs_fail_when_not_materialized` | 脚报导出 `runtime_binding_must_be_view` 而测试期望 `org_product_ref_missing_metric_node` |

**根因**：7 个测试在内存 SQLite 中把 `data_account_metric_binding` 创建为物理 TABLE，但 inventory 脚本已新增 `binding_physical_table_retired` 检查（binding 必须是 view），该检查优先触发，导致断言不匹配。

### 测试汇总

| 套件 | 通过 | 失败 | 与 v2 报告对比 |
|------|------|------|---------------|
| 套件 1 | 23 | **4** | 不变 |
| 套件 2 | 72 | **7** | 不变 |
| **合计** | **95** | **11** | 不变 |

---

## 五、当前 DB 状态验证（`var/data/common.db`）

| 对象 | 类型 | 预期 | 状态 |
|------|------|------|------|
| `org_product_tree_snapshot` | table | table | ✅ 正确（22 节点，4 层） |
| `org_product_metric_table` | — | 不存在 | ✅ 正确（已清理） |
| `data_account_metric_node` | table | table | ✅ 正确（26 列，含全部运行字段） |
| `data_account_metric_binding` | view | view | ✅ 正确（已转为 view） |
| `data_account` | view | table 或 view | ✅ 已为 view |
| `product_type` | — | 不存在 | ✅ 正确（已退休） |

---

## 六、整改完成度评分

| 模块 | 总项数 | 已改 | 部分改 | 未改 | 完成度 |
|------|--------|------|--------|------|--------|
| 机构及产品树 | 6 | 0 | 0 | 6 | **0%** |
| 机构及产品指标树 | 5 | 2 | 3 | 0 | **70%** |
| **合计** | **11** | **2** | **3** | **6** | **36%**（严格）/ **55%**（含部分改） |

---

## 七、建议修复优先级

### P1 — 阻断级（必须先修）

| 优先级 | 事项 | 原因 | 预估工作量 |
|--------|------|------|-----------|
| P1-1 | 后端树合同强校验 | 主数据模块核心防线，缺失让非法树污染全部下游 | 中（新增校验函数 + 测试用例） |
| P1-2 | agent_product_intent 测试修复 | fixture 补齐 `runtime_account_enabled` + `product_code` 列即可 | 小（改 1 个 fixture） |
| P1-3 | 统一 inventory 测试 VIEW 合同 | 7 个测试 fixture 需把 `CREATE TABLE data_account_metric_binding` 改为 `CREATE VIEW` | 小（改 6 个测试文件） |

### P2 — 重要级

| 优先级 | 事项 | 原因 | 预估工作量 |
|--------|------|------|-----------|
| P2-1 | 删除/改码影响分析 | 防止产品树与指标/事实脱节产生悬挂数据 | 中（新增 save-preview 接口） |
| P2-2 | Excel 导入审计 summary | 业务人员导入体验的关键缺失 | 小（改返回值格式） |
| P2-3 | `org_product_metric_table` 加入 `RETIRED_TABLES` | 防御性措施，防止未来意外重建 | 极小（加 1 行） |

### P3 — 优化级

| 优先级 | 事项 | 原因 | 预估工作量 |
|--------|------|------|-----------|
| P3-1 | sync 函数命名 | 代码可维护性问题，不影响功能 | 极小（改函数名） |
| P3-2 | 前端服务端版本联动 | 多人协作场景才触发，当前单用户可接受 | 中（前后端联动改造） |
| P3-3 | `functional_group_code` 增加独立字段 | 当前数据已改善，但长期应拆分语义 | 大（schema 变更 + 全链路适配） |

---

## 八、审核最终结论

### 整体判定：**不合格 — 需继续整改**

1. **指标树模块**（5 项）已基本完成核心整改，遗留为防御性措施和测试统一，可作为"有条件通过"。

2. **机构及产品树模块**（6 项）全部未动，这是当前最大缺口。特别是：
   - **后端树合同强校验**：主数据模块没有后端防线，Excel 导入和 API 可绕过前端直接写入非法树
   - **4 个 agent_product_intent 测试**：根因明确（fixture 缺 2 列），修复简单但一直未修
   - **7 个 inventory 测试**：测试 fixture 与生产 schema 未对齐（CREATE TABLE vs CREATE VIEW）

3. **11 个失败测试**中，全部是测试数据与生产 schema 未对齐导致的，修复工作量不大但一直未做。

### 建议下一步

龙虾应按 **P1 → P2 → P3** 顺序处理，先修后端强校验 + 修测试 fixture（共 11 个测试），再补删除影响分析和 Excel 审计，最后处理命名和联动优化。P1 级别修复完成后可重新提交审核。
