Status: ready-for-agent
Category: enhancement

# PRD: 产品维度数据科目维护

## Problem Statement

当前 **数据科目维护表** 更像一张全局维护大表。用户进入页面后，需要同时面对完整层级编码、指标口径编码、指标族、产品范围码、公式等大量技术字段，再自己脑补“这个数据科目到底和哪个产品有关”。这种工作方式和预算团队真实的 **产品优先工作流** 不一致。

对预算人员来说，日常任务不是维护一套抽象的全局数据科目，而是先进入某个 **系统产品科目** 或产品线，再看当前产品可用的数据科目、补充缺失科目、检查公式和范围是否合理。如果页面继续以全局平铺表格为主，用户会在海量无关行里反复搜索、过滤、切换产品范围，维护成本高，也很难一眼分辨 `全行` 公共科目、当前产品线共享科目和产品专属科目。

用户真正需要的是一个 **产品维度数据科目视图**：先选产品，再在精简后的指标树和当前产品可用的数据科目表中完成维护；同时又不能破坏现有 **数据科目维护表** 作为统一主数据来源的角色，不能引入第二套数据科目模型。

## Solution

在现有 **数据科目维护表** 上建设 **产品维度数据科目视图**，让页面以产品为当前工作上下文，但继续复用同一套数据科目主数据、指标口径绑定、公式编辑和产品范围字段。

用户进入页面后，先选择一个 **系统产品科目**。该选择既支持末级产品，也支持父级产品线。选中某个产品后，页面只展示该产品当前可用的数据科目，包括：

- `全行` 公共数据科目
- 适用范围覆盖当前产品的专属数据科目
- 当用户选择父级产品线时，适用于任一子产品的数据科目

页面主结构保持“左侧精简指标树 + 右侧数据科目表”。左侧保留现有指标树的组织能力，但弱化技术噪音；右侧围绕当前树节点展示当前产品上下文下的数据科目核心信息。默认只展示业务维护所需的核心列，例如数据科目名称、适用范围、数值类型、公式状态和操作，技术字段改为详情或更多字段。

公式列默认只显示紧凑状态，支持 hover 预览完整公式，点击进入公式编辑器。适用范围列采用简洁摘要，例如 `全行`、`本产品`、`本产品线`、`适用 3 个产品` 或具体产品名，并在 hover 中展示完整范围。

新增数据科目时，用户不进入独立弹窗，而是在当前指标节点下直接新增一行。新行默认继承当前产品或产品线范围，并只要求填写少量必填项：**数据科目名称**、**适用范围**、**数值类型**。公式及其他可选配置由用户后续按需补充。所有维护仍然写回统一 **数据科目维护表**，不引入新的平行表。

## User Stories

1. As a 预算人员, I want to start 数据科目维护 from a selected **系统产品科目**, so that the page matches my product-based maintenance workflow.
2. As a 预算人员, I want to select either a leaf product or a parent product line, so that I can work at the level that matches my responsibility.
3. As a 预算人员, I want the page to show only data accounts relevant to the selected product context, so that I do not scan unrelated global rows.
4. As a 预算人员, I want `全行` data accounts to remain visible in the selected product context, so that shared public indicators are not accidentally hidden.
5. As a 预算人员, I want parent-product selection to include descendant-product data accounts, so that a product-line view is still useful.
6. As a 预算人员, I want the page to preserve the existing indicator-tree structure, so that I can still navigate by business indicator hierarchy.
7. As a 预算人员, I want the indicator tree to be visually simplified in the product view, so that it feels lighter than the current full maintenance table.
8. As a 预算人员, I want the main layout to be left indicator tree and right data-account table, so that navigation and editing happen in one workspace.
9. As a 预算人员, I want the right table to default to business-facing columns only, so that I am not overwhelmed by technical metadata.
10. As a 预算人员, I want technical fields such as full hierarchy code and metric node code hidden behind details, so that they are available when needed but not always in my way.
11. As a 预算人员, I want the formula columns to show status first, so that long formulas do not make the table hard to scan.
12. As a 预算人员, I want hover on a formula status to preview the full formula, so that I can quickly inspect logic without opening an editor every time.
13. As a 预算人员, I want clicking a formula status to open the formula editor, so that detailed changes still use the existing configuration capability.
14. As a 预算人员, I want the适用范围 column to use short business summaries, so that I can quickly tell whether a row is public, current-product, current-line, or multi-product.
15. As a 预算人员, I want hover on the适用范围 summary to show the full product list, so that compact display does not hide important detail.
16. As a 预算人员, I want `全行` to be labeled directly as `全行`, so that shared public scope is immediately obvious.
17. As a 预算人员, I want a data account that applies to the current selected product only to read as `本产品`, so that I can distinguish it from shared rows.
18. As a 预算人员, I want a data account scoped to the selected parent product line to read as `本产品线`, so that line-shared rows are recognizable.
19. As a 预算人员, I want multi-product scopes to show a concise count such as `适用 3 个产品`, so that the table stays compact.
20. As a 预算人员, I want a single other-product scope to show the product name directly, so that I can understand exceptions at a glance.
21. As a 预算人员, I want to add a new data account inline under the currently selected indicator-tree node, so that creation feels lightweight and in-context.
22. As a 预算人员, I want a new inline row to inherit the current product or product-line scope by default, so that most additions require minimal setup.
23. As a 预算人员, I want to be able to override the default scope on that new row, so that I can still create public or multi-product data accounts when needed.
24. As a 预算人员, I want new inline rows to require only 数据科目名称, 适用范围, and 数值类型 at first, so that I can create missing rows quickly.
25. As a 预算人员, I want formulas and optional settings to be configured later, so that new-row creation stays focused on the essentials.
26. As a 预算人员, I want new rows created from a parent-product context to default to that parent product line rather than all descendants individually, so that line-level shared scope remains first-class.
27. As a 预算人员, I want all-product data accounts to be created only through an explicit scope change, so that I do not accidentally create public rows from a product view.
28. As a 预算人员, I want edits to an all-product data account in the product view to clearly imply shared impact, so that I do not mistake it for a product-local change.
29. As a 预算人员, I want the product view to reuse the same underlying data-account records as the global maintenance page, so that I am not maintaining duplicate master data.
30. As a 预算人员, I want product filtering to be based on existing product-scope rules, so that the view matches downstream budget and formula behavior.
31. As a 预算主管, I want this feature to preserve **数据科目维护表** as a single source of truth, so that reporting, formula configuration, and budget calculation continue using the same master data.
32. As a 预算主管, I want the product view to reduce training cost for business users, so that they can maintain product-relevant rows without learning technical coding fields first.
33. As a 预算主管, I want the page to stay compact even when many data accounts exist under one product line, so that product reviews remain practical.
34. As a 预算主管, I want parent product lines to be explorable without maintaining a separate report-account or data-account copy for each parent, so that the hierarchy remains manageable.
35. As a 开发人员, I want the product-dimension filtering and scope-summary logic separated from raw row rendering, so that the behavior can be tested without coupling to the whole page.
36. As a 开发人员, I want the product view to reuse existing formula editing, product selection, and data-account persistence contracts, so that implementation risk stays low.
37. As a 开发人员, I want a stable read model for product-scoped data-account rows, so that frontend layout changes do not force repeated backend SQL rewrites.
38. As an AFK implementation agent, I want the PRD to define the primary layout, required fields, and scope-display rules clearly, so that implementation does not need another design round before starting.

## Implementation Decisions

- The feature is a **产品维度数据科目视图** built on top of the existing **数据科目维护表**, not a new master-data model.
- **数据科目维护表** remains the single source of truth for data-account master data, product scope, formulas, metric bindings, and value type.
- The product view begins with selecting a **系统产品科目** and uses that selection as the working context for filtering and defaults.
- Product selection must support both leaf products and parent product nodes.
- When the selected node is a leaf product, the view includes all-product data accounts and data accounts whose product scope covers that leaf product.
- When the selected node is a parent product node, the view includes all-product data accounts, parent-line-scoped data accounts, and any data accounts whose scope covers descendant products.
- The main visual structure is a left indicator-tree panel and a right data-account table for the selected tree node.
- The product view keeps the existing indicator-tree organization as the primary navigation structure rather than regrouping the page by product scope.
- The indicator tree should be rendered in a simplified, compact form for product-focused maintenance.
- The right data-account table should default to business-facing columns only.
- Technical fields such as full hierarchy code, metric node code, metric group code, and metric group name should be hidden behind details or a more-fields control by default.
- Formula columns should default to compact status display rather than inline full-formula text.
- Formula status must support hover preview of the full formula and click-through into the existing formula editor.
- Product scope must be displayed as a compact business summary in the table.
- Scope summary rules are:
  - all-product scope displays as `全行`
  - a scope equal to the selected leaf product displays as `本产品`
  - a scope equal to the selected parent product node displays as `本产品线`
  - a multi-product scope displays as a concise item count
  - a single other-product scope displays its product name
- Hover on the scope summary should reveal the full product scope detail.
- New data accounts in the product view are created inline under the currently selected indicator-tree node rather than through a separate creation dialog.
- A new inline row inherits the current product or product-line scope by default.
- Users may explicitly change the inherited scope before save.
- A new inline row should require only **数据科目名称**, **适用范围**, and **数值类型** at creation time.
- Data-account code generation remains system-owned and should not become a required manual input in the product view.
- The selected indicator-tree node defines the binding context for a new inline row.
- Formula configuration and other optional settings are deferred until after the row is created.
- Creating an all-product data account from the product view must require an explicit scope change by the user.
- Editing an all-product data account from the product view is a shared-scope change and should be treated with clear shared-impact affordances.
- Existing product-scope persistence based on `product_codes` remains the underlying scope model unless implementation uncovers a stronger compatibility-preserving abstraction.
- Existing data-account formula editing, product selection, export/import, and persistence APIs should be reused where possible rather than reimplemented in parallel.
- The implementation should prefer introducing a focused product-scoped read model and scope-summary helper module instead of embedding all filtering and label logic directly in the page component.
- Secondary inline-editing details should follow streamlined best practices and existing maintenance-page safety patterns unless they conflict with the product-focused workflow.
- The issue tracker entry for this PRD uses local markdown and is marked `ready-for-agent`.

## Testing Decisions

- Tests should focus on externally visible behavior and domain rules, not implementation details of the React component tree.
- Product-scope filtering should be tested as a read-model contract, including leaf-product selection, parent-product selection, descendant inclusion, and all-product inclusion.
- Scope-summary formatting should be tested as behavior, including `全行`, `本产品`, `本产品线`, single-other-product naming, and multi-product count summaries.
- New-row defaults should be tested as behavior, including inherited tree-node binding context, inherited product scope, and required-field validation.
- Formula-display behavior should be tested at the interaction level: compact status by default, hover preview availability, and editor entry action.
- Table-column behavior should be tested to ensure default business-facing columns are shown and technical fields are hidden behind an explicit reveal path.
- Shared-scope behavior should be regression-checked so that all-product rows remain visible in product context and do not silently become product-local rows when edited.
- Backend or service-level tests should cover any new product-scoped data-account read model and helper logic used to derive scope summaries.
- Frontend interaction tests or repeatable browser verification should cover:
  - selecting a leaf product
  - selecting a parent product line
  - indicator-tree navigation
  - inline row creation under a selected node
  - scope summary rendering
  - hover preview for formulas
- Good tests should verify business outcomes rather than DOM structure, for example “rows visible for selected product” rather than “specific hook state changed”.
- Prior art in this codebase includes the current **数据科目维护表** interactions, product selector flows, formula editor behavior, and other budget-maintenance API tests. New tests should follow those established patterns before introducing heavier end-to-end suites.

## Out of Scope

- Replacing **数据科目维护表** with a new standalone product-specific master table.
- Redesigning the entire budget maintenance navigation outside the data-account maintenance area.
- Changing the physical storage grain of data accounts or replacing the existing `product_codes` scope mechanism as part of this feature alone.
- Rebuilding formula authoring into a new editor separate from the existing data-account formula editor.
- Reworking Excel import/export semantics beyond what is needed to keep the product view compatible.
- Introducing a new permissions model for “我的负责产品” or turning that concept into formal access control.
- Reworking **报告科目维护表**, **产品预算工作台**, or **预算展示报表** as part of this PRD.
- Defining every minor inline-editing microinteraction up front when existing best-practice patterns can be reused safely.

## Further Notes

- The strongest product signal from the discussion is simplicity: the user wants product-focused maintenance, not a second global table wrapped in extra filters.
- The feature should preserve current data-account semantics while changing the primary user-facing navigation model from “global master table first” to “product context first”.
- A clean implementation will likely separate two concerns that are currently entangled in the page: raw data-account persistence and product-scoped presentation logic.
- The product view should make shared rows feel visible but clearly shared, so that business users can move faster without accidentally widening scope.
- If implementation discovers that existing product-scope data is inconsistent across parent and descendant nodes, that should be surfaced as a data-quality issue rather than hidden behind ambiguous UI behavior.
