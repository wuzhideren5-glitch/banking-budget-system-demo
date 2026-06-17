Status: implemented-in-current-architecture
Category: enhancement

# PRD: 预算展示报表展示结构表解耦与 row_key 层级主键

## Problem Statement

**预算展示报表** 本质上是 **预算输出** 中的取数展示报表，但当前展示配置长期混入了多种业务身份：旧报告科目编码、数据科目编码、产品代码、`GROUP` 兼容标识和用户新增行流水号。用户在配置展示科目时看到的 `row_key` 既像展示行标识，又像数据科目编码，还可能包含产品范围。这样会让维护人员误以为报表展示结构表同时负责指标定义、产品范围、取数逻辑和展示层级。

这种混杂会带来三个风险。第一，纯展示节点可能被误当成数据行，页面上显示 `0.00` 或被参与取数。第二，数据行和展示行的身份来源不清，后续新增、拖拽、删除、迁移时容易破坏父子层级。第三，**预算展示报表** 会重新变成一套隐形“报告科目主数据”，与 **数据科目维护表** 和 **标准数据科目指标树** 的唯一来源原则冲突。

用户需要的是一个清晰、简单、可维护的展示结构表：它只负责 **全行总表**、**分产品概览**、**单产品明细** 三类展示视图的行位置、父子层级、展示名称和是否取数。真正的数据来源必须只通过 **数据科目维护表** 中的唯一指标号码绑定，不能再把数据科目或产品语义塞进展示结构主键里。

## Solution

将 **预算展示报表** 的展示配置收敛为一张纯展示结构表 `budget_output_display_item`。表中的 `display_view` 表达展示视图，`row_key` 表达该视图内的层级位置；它们不再表达数据科目身份，也不再把旧报告科目编码作为身份来源。

当前 `row_key` 规则按三类展示视图生成：

- **全行总表**：`TOTAL.01.02`
- **分产品概览**：`OVERVIEW.01.02`
- **单产品明细**：`PRODUCT.A01.01.02`

每一层使用两位层级位置码，从 `01` 开始。有几层展示层级就保留几段，不补无业务意义的尾部 `00`。例如四层结构可以是 `PRODUCT.A01.01.01.02.01`，一级根节点可以是 `TOTAL.01`。

展示结构表继续使用 `parent_row_key` 维护树关系，使用 `sort_order` 维护同父级排序，使用 `display_name` 维护用户可见名称。`row_type = GROUP` 表示纯展示分类节点，必须不取数；`row_type = METRIC` 表示数据展示行，必须通过 `data_acct_code` 挂到 **数据科目维护表**。数据取数、公式计算、产品范围、预算版本和期间选择均不写入 `row_key`。

用户在 **预算展示报表** 里新增展示分类或从 **数据科目维护表** 拖入数据科目时，系统按当前位置自动分配新的层级主键。新增纯展示分类不需要 `data_acct_code`；新增数据行必须挂 `data_acct_code`。报表运行时按传入的产品范围、版本和期间读取预算数据，再通过展示结构树呈现，不让展示结构表承担业务计算判断。

## User Stories

1. As a 预算报表维护用户, I want **预算展示报表** 的展示配置只维护展示结构, so that I can clearly distinguish layout maintenance from data-account maintenance.
2. As a 预算报表维护用户, I want `row_key` to use a stable hierarchy-position rule, so that I can understand where a row sits in the report tree without reading old business codes.
3. As a 预算报表维护用户, I want **全行总表** rows to use `TOTAL.xx` keys, so that all-bank report structure is clearly separated from product views.
4. As a 预算报表维护用户, I want **分产品概览** rows to use `OVERVIEW.xx` keys, so that cross-product comparison structure is not confused with a specific product.
5. As a 预算报表维护用户, I want **单产品明细** rows to use `PRODUCT.<产品代码>.xx` keys, so that each product-detail display tree has its own visible report heading.
6. As a 预算报表维护用户, I want each hierarchy segment to be two digits from `01`, so that row order and parent-child position are readable and deterministic.
7. As a 预算报表维护用户, I want the key to include only existing hierarchy depth, so that the system does not create misleading `00.00` padding.
8. As a 预算报表维护用户, I want `parent_row_key` to point to the new hierarchy key, so that expand/collapse and drag placement follow the display tree.
9. As a 预算报表维护用户, I want pure display categories such as `资产业务` to be `GROUP` rows, so that they act as headers rather than data rows.
10. As a 预算报表维护用户, I want `GROUP` rows to show blank values, so that users do not mistake a display header for a zero-valued business metric.
11. As a 预算报表维护用户, I want data-bearing rows to be `METRIC` rows, so that the table clearly marks which rows take data.
12. As a 预算报表维护用户, I want every `METRIC` row to have a `data_acct_code`, so that every displayed number has a formal data-account source.
13. As a 预算报表维护用户, I want `data_acct_code` to remain separate from `row_key`, so that changing display position does not change the metric identity.
14. As a 预算报表维护用户, I want a displayed row name to be editable separately from the data-account name, so that the report can use business-friendly wording while still taking data from the formal source.
15. As a 预算报表维护用户, I want to add a display category without selecting a data account, so that I can maintain report grouping nodes.
16. As a 预算报表维护用户, I want to drag a data account under an existing display row, so that the new row inherits the intended display hierarchy.
17. As a 预算报表维护用户, I want insertion under a parent to allocate the next available two-digit child segment, so that the structure remains stable after edits.
18. As a 预算报表维护用户, I want insertion after a sibling to preserve parent context, so that drag placement behaves like editing a report outline.
19. As a 预算报表维护用户, I want deleting a display row to affect only display configuration, so that deleting a report layout row does not delete data-account master data.
20. As a 预算报表维护用户, I want deleting or unbinding a data account to clear or validate display references explicitly, so that display rows cannot silently take stale data.
21. As a 预算主管, I want **预算展示报表** to read from **数据科目维护表**, so that all report numbers come from the unified metric-account system.
22. As a 预算主管, I want **预算展示报表** not to recreate report-account master data, so that the system avoids a second maintenance source.
23. As a 预算主管, I want **标准数据科目指标树** to remain the metric definition source, so that report display does not redefine metric meaning.
24. As a 预算主管, I want product, version and period selections to be runtime filters, so that the display structure table does not hard-code reporting context into row identity.
25. As a 预算主管, I want the same report structure to survive data-account formula changes, so that presentation and calculation can evolve independently.
26. As a 预算主管, I want the system to expose missing data-account bindings as configuration issues, so that display rows do not silently show incorrect zeros.
27. As a 预算主管, I want the old `PRODUCT.A01.GROUP...` style keys to disappear, so that users no longer see mixed product/group/metric semantics in one identifier.
28. As a 预算主管, I want the old `TOTAL.<data_acct_code>` style keys to disappear, so that users do not confuse report row identity with formal metric identity.
29. As a 预算主管, I want **全行总表**, **分产品概览**, and **单产品明细** to be visually and structurally distinct, so that each report view can be maintained without affecting the others.
30. As a 开发人员, I want a single key-allocation rule for display rows, so that frontend actions and initialization do not invent different row identities.
31. As a 开发人员, I want migration to preserve all existing display rows, so that the refactor changes identity shape without losing business configuration.
32. As a 开发人员, I want migration to preserve old parent-child relationships through explicit old-to-new mapping, so that no child row becomes orphaned.
33. As a 开发人员, I want migration to fail if any non-root parent cannot be mapped, so that the database never enters a partial broken tree state.
34. As a 开发人员, I want migration to validate `GROUP` and `METRIC` invariants, so that structure/data boundaries are enforced at the data layer.
35. As a 开发人员, I want API DTOs to expose row type clearly, so that the frontend can decide whether to render values without guessing from key text.
36. As a 开发人员, I want report export to label row identifiers as display row keys, so that exported workbooks do not imply that row keys are metric codes.
37. As a 开发人员, I want the read model to aggregate values by `data_acct_code` and then project onto display rows, so that display tree traversal stays separate from budget-data lookup.
38. As an AFK implementation agent, I want the PRD to define row-key grammar, row-type invariants, and migration validation, so that future changes do not reintroduce mixed identities.

## Implementation Decisions

- **预算展示报表** display configuration is a display-structure model, not a data-account definition model.
- `row_key` is the primary key of a display row and must express report view plus hierarchy position only.
- `row_key` must not embed `data_acct_code`, old report-account code, formula identity, version, period, or runtime product filter beyond the **单产品明细** report-view heading itself.
- The three report-view key prefixes are `TOTAL`, `OVERVIEW`, and `PRODUCT.<系统产品科目代码>`.
- **全行总表** row keys follow `TOTAL.<两位层级段>...`.
- **分产品概览** row keys follow `OVERVIEW.<两位层级段>...`.
- **单产品明细** row keys follow `PRODUCT.<系统产品科目代码>.<两位层级段>...`.
- Every hierarchy segment is two digits from `01` to `99`.
- Row keys include only actual display depth; the system does not append unused `00` segments.
- `parent_row_key` stores the parent display row's `row_key`.
- `sort_order` stores sibling ordering and remains independent from `row_key`, although generated hierarchy segments follow current sibling order during migration or allocation.
- `display_name` stores the user-facing report row name and may differ from the formal data-account name.
- `row_type = GROUP` means a display category row. It must not have `data_acct_code`.
- `row_type = METRIC` means a data-bearing display row. It must have `data_acct_code`.
- `data_acct_code` remains the only pointer from a report display row to **数据科目维护表**.
- `GROUP` rows must render blank or a non-numeric placeholder in the report grid and export, not `0.00`.
- `METRIC` rows take values by resolving `data_acct_code` against budget data for the selected product, version and period.
- Parent rows with children may roll up from child rows for display, but row identity remains display-position identity.
- Runtime product selection, selected versions, year and month logic are query context, not display-row identity.
- New display categories can be created without a data account and are stored as `GROUP` rows.
- New data-bearing rows are created by selecting or dragging a data account and are stored as `METRIC` rows.
- New row allocation uses the selected parent row, or the target insertion sibling's parent, to determine hierarchy prefix and next child segment.
- Migration from old keys must be deterministic and reversible by backup: compute old-to-new mapping first, update row keys through temporary keys, then update parent references.
- Migration must validate total row count, unique new keys, no missing parents, no `GROUP` rows with data, no `METRIC` rows without data, no invalid data-account references, and no foreign-key errors.
- The initial Excel style workbook can seed default display structure only when the display table is empty; after seeding, the database display structure is authoritative.
- Existing display configuration rows should be preserved during migration rather than reimported from Excel.
- The issue tracker entry for this PRD uses local markdown and is marked `ready-for-agent`.

## Testing Decisions

- Tests should focus on visible and API-level behavior: row identities, tree shape, value rendering and persistence invariants.
- Migration tests should verify that every old row receives exactly one new row key.
- Migration tests should verify that every old parent reference is translated to the correct new parent reference.
- Migration tests should verify that non-root rows cannot be migrated when their old parent is missing.
- Migration tests should verify that sibling counts above `99` are rejected or surfaced clearly.
- Migration tests should verify that migrated row keys match the grammar for `TOTAL`, `OVERVIEW`, and `PRODUCT.<code>`.
- Migration tests should verify that row count is unchanged after migration.
- Migration tests should verify there are no duplicate row keys after migration.
- Migration tests should verify there are no orphaned `parent_row_key` values after migration.
- Migration tests should verify `GROUP` rows have no `data_acct_code`.
- Migration tests should verify `METRIC` rows have valid `data_acct_code` values.
- API tests should verify display-config create returns a hierarchy-position `row_key` for new `GROUP` rows.
- API tests should verify display-config create returns a hierarchy-position `row_key` for new `METRIC` rows.
- API tests should verify creating under a parent uses that parent as the key prefix and increments child segment.
- API tests should verify inserting after a sibling uses the sibling's parent context.
- API tests should verify display-report rows expose `row_type`.
- API tests should verify display-report `GROUP` rows do not expose business values for rendering.
- API tests should verify display-report `METRIC` rows still return values from budget data through `data_acct_code`.
- Frontend verification should cover opening **预算展示报表**, expanding/collapsing hierarchy, viewing `GROUP` rows as blank, and viewing `METRIC` rows with values.
- Frontend verification should cover adding a display category and confirming its key shape.
- Frontend verification should cover dragging a data account into the display tree and confirming its key shape and data binding.
- Export verification should confirm workbook labels call the key a display row key rather than an indicator code.
- Existing prior art includes database bootstrap schema tests, data-account write tests, budget-output display report API checks, and production build verification.

## Out of Scope

- Redesigning **数据科目维护表** itself.
- Changing the official **唯一指标号码** rule in `data_account`.
- Changing **标准数据科目指标树** structure.
- Changing budget data physical storage or formula calculation logic.
- Reintroducing old `report_account` or `report_data_mapping` as a primary source.
- Rebuilding the whole report grid UI framework.
- Changing user permissions for report configuration.
- Reimporting the report structure from Excel as the normal maintenance path.
- Deleting business display rows during row-key migration.
- Solving every semantic mapping issue between historical report rows and data accounts.
- Changing **费用预算执行报表** or other department-fee reports.
- Defining a new report styling/theme system.

## Further Notes

- This PRD records the product decision that **预算展示报表** is a display structure plus data-account projection, not a new metric master-data system.
- The most important invariant is the split between `row_key` and `data_acct_code`: display position and metric identity must stay separate.
- The `PRODUCT.A01.xx` prefix is intentional for **单产品明细** because each product-detail display tree is its own report view.
- Pure display categories should be allowed even when they do not map to **数据科目维护表**.
- Data-bearing rows must always map to **数据科目维护表**; if no formal data account exists, the gap should be surfaced as a configuration problem rather than hidden as zero.
- Future agents should avoid deriving row type from key text. `row_type` is the explicit contract.
