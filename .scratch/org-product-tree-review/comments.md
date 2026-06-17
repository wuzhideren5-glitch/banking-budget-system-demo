# 机构及产品树模块代码评审 Comments

评审时间：2026-06-16  
评审对象：`机构及产品` 主数据树模块  
评审范围：机构/产品树前端维护、DB 快照、Excel 导入导出、运行产品清单、下游数据录入/预测输出联动  
主要文件：

- `apps/web/src/app/components/OrgProductContent.tsx`
- `apps/web/src/app/orgProductTree.ts`
- `apps/api/app/routers/org_product_metrics.py`
- `apps/api/app/services/org_product_runtime_catalog.py`
- `apps/api/app/agent_product_intent.py`
- `apps/var/data/common.db`

## 总体结论

当前 `机构及产品` 树的数据现状没有明显坏掉：DB 快照只有 1 行，能展开为 21 个节点；`product_type` 旧维护对象当前没有恢复；AAA/AA/AB/A-F/A01-F01 的层级在当前库里是正确的。

但从交付标准看，这个模块还不够稳。它现在更像“页面维护 + JSON 快照”，而不是一个具备强业务约束的主数据模块。最大风险是：前端限制比较多，后端合同比较软；产品树变更不会做影响分析；下游指标、录入、预算事实和 AI 查询都依赖它，但模块本身没有把这些依赖纳入保存门禁。

## 当前数据快照

当前 `apps/var/data/common.db` 中：

```text
org_product_tree_snapshot|table
snapshot rows: 1
payload length: 1735
updated_at: 2026-06-09T16:44:14Z
```

树节点展开结果：

```text
AAA 微众集团
  AA 微众银行
    A 个金群
      A01 泛微粒贷
      A02 微账户
      A03 汽车金融
      A04 财富
      A05 小鹅
    B 企金群
      B01 企业金融
      B02 金融市场
    C 数字金融
      C01 国内业务
      C02 国内研发
    D 国际业务
      D01 国际业务
    E 小鹅导流
      E01 小鹅导流
    F 司库及其他
      F01 司库及其他
  AB 微众科技
```

节点统计：

```text
tree_node_count|21
level1|2
level2|6
level3|12
```

当前未发现 `data_account_metric_node.product_code`、`org_product_data_entry_snapshot_v2.entity_code`、`org_product_output_snapshot_v1.entity_code` 中存在“不在机构及产品树”的产品码。

## 检视板块 1：业务主数据边界

### 问题 1：模块还没有把“机构及产品树是主数据”这件事落实到保存门禁

前端在 `OrgProductContent.tsx` 中会做基础校验：代码不能为空、名称不能为空、代码不能重复。新增节点也会按父节点类型推导下一层类型。

相关位置：

- `validateNodeDraft()`：只校验空值和重复代码。
- `handleCreateChild()`：依赖 `childTypeForParent()` 控制新增层级。
- `handleSaveRefresh()`：直接调用 `/api/org-product-tree/save-refresh`。

后端保存接口在 `org_product_metrics.py` 中直接写入 `org_product_tree_snapshot`，然后调用 `sync_org_product_runtime_catalog_from_tree()`。这个同步服务只校验空编码、空名称、重复编码，并删除旧 `product_type`，没有验证：

- 根节点必须是 `AAA / 微众集团 / level0`。
- `AA`、`AB` 是否只能位于 level1。
- level2 是否只能挂在 level1 下。
- level3 是否只能挂在 level2 下。
- 产品代码是否必须符合 `父机构代码 + 两位数字`。
- 核心节点是否允许改码或删除。

### 影响

只要绕过前端，或者导入 Excel 产生异常层级，后端仍可能保存业务上不合法的树。后续下游会通过 `org_product_runtime_products_cte()` 动态展开这份 JSON，错误会传播到数据录入、预测输出、模拟测算、AI 查询等模块。

### 建议

1. 在后端建立强校验函数，例如 `validate_org_product_tree_contract(tree)`，保存前必须通过。
2. 校验至少包含：唯一根、合法层级、父子层级合法、代码格式、核心节点保护、同级排序和重复代码。
3. 前端校验可以保留，但只能作为体验优化；主合同必须在后端。
4. 给 `/api/org-product-tree/save-refresh` 增加失败用例测试：非法根、level3 直接挂 level1、重复代码、空名称、非法产品码都应 400。

## 检视板块 2：删除/改码影响分析

### 问题 2：删除或改码产品树节点不会做下游引用检查

页面允许删除除集团根节点以外的任意节点：

- 删除 level1 会删除其全部机构和产品。
- 删除 level2 会删除其全部产品。
- 删除 level3 会删除单个产品。

保存时只是覆盖 `org_product_tree_snapshot`。同步服务 `sync_org_product_runtime_catalog_from_tree()` 并不会检查该产品下是否仍存在：

- `data_account_metric_node` 指标节点。
- `org_product_data_entry_snapshot_v2` 数据录入快照。
- `org_product_output_snapshot_v1` 预测输出快照。
- 年度库 `budget_data` 预算事实。
- 报表展示配置或模拟测算引用。

### 影响

业务上删除产品不是单表动作，它会影响指标体系、录入事实、输出报表和预算展示。当前实现可能出现“产品树上看不到某产品，但指标和事实还在”的悬挂状态。当前库暂未查到这种悬挂，但代码没有防止未来发生。

### 建议

1. 保存前增加影响分析接口，例如 `/api/org-product-tree/save-preview`。
2. 如果删除/改码节点命中已有指标、录入快照、输出快照或预算事实，默认阻断保存。
3. UI 上在删除确认前展示影响清单：产品数、指标数、录入版本数、预算事实行数。
4. 对“只改名称不改代码”放行；对“改代码/删除”走严格审批或二次确认。

## 检视板块 3：运行产品清单实现

### 问题 3：`sync_org_product_runtime_catalog_from_tree()` 名称像同步，实际没有物化运行表

`org_product_runtime_catalog.py` 中的 `sync_org_product_runtime_catalog_from_tree()` 做了两件事：

1. `_flatten_org_product_tree(tree)` 校验空值和重复。
2. `ensure_retired_product_type_absent(conn)` 删除旧 `product_type`。

它返回 `row_count`，但没有写入新的运行产品清单表。下游读取产品清单时主要依赖 `org_product_runtime_products_cte()` 从 `org_product_tree_snapshot.payload_json` 递归展开。

### 影响

这条路线本身可以成立，但命名和返回值容易让人误以为已经物化了 runtime catalog。实际运行时没有独立表，也没有 runtime catalog 的版本号、更新时间、校验摘要。一旦 JSON 快照坏掉，下游所有读取都跟着坏。

### 建议

1. 如果坚持 CTE 动态展开，建议把函数命名改成 `validate_org_product_tree_and_drop_retired_product_type()`，避免“同步表”的误导。
2. 如果业务上需要稳定运行清单，建议物化 `org_product_runtime_product` 表，保存树时事务内重建。
3. 无论是否物化，都应增加 `/api/org-product-tree/db-snapshot` 的合同校验和健康检查，不能只返回 JSON。

## 检视板块 4：Excel 导入

### 问题 4：导入解析兼容多格式，但缺少导入结果审计

`_parse_org_product_tree_excel()` 支持两类表：

- 标准列：层级、编码、名称、上级编码。
- 旧格式列：一级主体、二级机构、三级产品。

它能把 Excel 转成树，但当前导入接口只返回 `tree`，不会返回：

- 导入了多少个主体/机构/产品。
- 是否存在跳过行。
- 是否存在重复编码。
- 是否存在父级缺失。
- 是否从旧格式自动迁移为 AAA 根。

### 影响

业务人员导入 Excel 后只能靠页面肉眼看树是否正确。对于机构产品主数据，这个反馈太弱，尤其容易漏掉“某些行被跳过但没有提示”的情况。

### 建议

1. 导入接口返回 `summary`：节点数、各层级数量、跳过行、错误行、根节点信息。
2. 如果旧格式导入返回 AA 根，后端也应统一迁移成 AAA 根，而不是只依赖前端 `prepareOrgProductTreeFromStorage()`。
3. 导入预览阶段就做后端强合同校验，不要等保存时才失败。

## 检视板块 5：下游联动

### 问题 5：数据录入和预测输出会监听树保存事件，但依赖的是前端事件，不是服务端版本

`OrgProductDataEntryContent.tsx` 会监听：

- `org-product-tree-saved`
- `org-product-metrics-saved`
- `visibilitychange`

预测输出页面也监听 `org-product-tree-saved` 后重新加载。

这说明前端页面之间有联动意识。但这个联动只在同一浏览器窗口内可靠；如果其他用户或脚本更新了树，当前页面只能依赖可见性变化或手动同步。

### 影响

在多人协作或包交付场景中，树和指标表可能已经被后端更新，但前端页面仍保留旧选择状态。更严重的是，树变更后选中的产品可能已经不存在，数据录入/预测输出如果没有明确提示，会造成误操作。

### 建议

1. 在 `org_product_tree_snapshot` 中维护 `updated_at`，前端每次保存数据录入/输出前校验树版本是否变化。
2. 如果当前选择的 `entity_code` 已不在树中，页面必须显式提示并阻止保存。
3. 数据录入和预测输出页面不要只依赖 window event，应在关键提交前重新拉取树快照。

## 检视板块 6：AI/查询意图与产品树

### 问题 6：产品树范围扩展依赖指标运行引用，当前相关测试失败

执行：

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_runtime_catalog_router.py \
  apps/api/test_db_bootstrap_current_contracts.py \
  apps/api/test_agent_product_intent_catalog.py
```

结果：

```text
4 failed, 23 passed
```

失败集中在 `test_agent_product_intent_catalog.py`：

- `test_metric_lookup_ignores_orphan_runtime_nodes`
- `test_metric_binding_lookup_ignores_orphan_runtime_bindings`
- `test_metric_binding_lookup_expands_parent_product_scope_from_org_product_tree`
- `test_catalog_digest_sources_metrics_from_org_product_metric_code`

相关代码在 `agent_product_intent.py`：

- `_expanded_product_scope_codes()` 通过机构及产品树展开父级范围。
- `_lookup_metric_nodes()` 和 `_bindings_for_metric_nodes()` 又依赖已确认的指标运行引用。

### 影响

这说明“机构及产品树”虽然能展开范围，但它和“机构及产品指标运行引用”之间的合同没有完全对齐。AI 查询、自然语言预算分析、产品范围筛选可能无法正确从 A 扩到 A03，或无法把产品树范围映射到可用指标编码。

### 建议

1. 先修指标运行引用确认逻辑，再恢复这些测试。
2. 给产品树范围扩展单独加测试：选择 A 时必须包含 A01-A05，选择 AA 时必须包含 AA 下全部机构/产品。
3. AI 查询不要读取旧 `org_product_metric_table` 作为确认来源，应统一读取 runtime tree 中已启用的 org-product metric refs。

## 正向发现

当前模块有几处方向是对的，应保留：

1. 旧 `product_type` 维护对象没有恢复，运行产品清单从 `org_product_tree_snapshot` 展开。
2. 前端优先读取 DB 快照，DB 无数据时才回退 localStorage。
3. 数据录入和预测输出页面已经监听树保存事件，具备基础联动机制。
4. 当前 DB 树层级、空值、重复码检查未发现明显数据污染。

## 建议修复顺序

1. 先补后端树合同校验，确保非法树不能保存。
2. 增加删除/改码影响分析，防止产品树和指标/事实脱节。
3. 明确运行产品清单是否物化；若不物化，重命名同步函数并加强 CTE 读取健康检查。
4. 强化 Excel 导入预览，返回行级审计结果。
5. 修复 `agent_product_intent` 相关失败测试，确保产品树范围扩展能和指标运行引用对上。
6. 最后做浏览器验证：机构及产品页面保存后，机构及产品指标、数据录入、预测输出页面都能自动同步并处理失效选择。

## 本次验证命令

```bash
sqlite3 apps/var/data/common.db "SELECT name, type FROM sqlite_master WHERE name IN ('org_product_tree_snapshot','product_type') ORDER BY name;"

sqlite3 apps/var/data/common.db "WITH RECURSIVE t(code,name,type,parent,level,children) AS (
  SELECT json_extract(payload_json,'$.code'),json_extract(payload_json,'$.name'),json_extract(payload_json,'$.type'),NULL,1,json_extract(payload_json,'$.children')
  FROM org_product_tree_snapshot WHERE id=1
  UNION ALL
  SELECT json_extract(child.value,'$.code'),json_extract(child.value,'$.name'),json_extract(child.value,'$.type'),t.code,t.level+1,json_extract(child.value,'$.children')
  FROM t,json_each(COALESCE(t.children,'[]')) child
) SELECT level,type,code,name,parent FROM t ORDER BY level,code;"

PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest -q \
  apps/api/test_org_product_runtime_catalog_router.py \
  apps/api/test_db_bootstrap_current_contracts.py \
  apps/api/test_agent_product_intent_catalog.py
```

## 评审结论

机构及产品树当前数据是干净的，但模块治理还不够严格。它已经替代旧 `product_type` 成为产品主数据入口，但还没有形成完整的主数据保存合同、影响分析和下游一致性门禁。建议不要只把它当成“树页面”验收，而要按“预算系统产品主数据”来验收。
