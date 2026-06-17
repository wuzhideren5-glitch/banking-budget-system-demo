# shier 0603 Merge Result - 2026-06-09

## Source Package

- `releases/TeamSubmit_20260603_shier_expense_budget_fixes`
- Declared scope from `SUBMISSION_NOTE.md`:
  - BI-AI subject mapping manage-department override.
  - Expense actual import manage-department validation.
  - Expense budget execution report daily/outsourcing actual split fixes.

## Merged

1. BI-AI subject mapping manage-department maintenance
   - Added `bi_ai_subject_mapping.manage_department_override`.
   - Added reference-data and update APIs.
   - Added frontend multi-select editor in `BiAiSubjectMappingTab`.
   - Preserved current 12-column BI source workbook structure.

2. Expense actual import manage-department validation
   - Added effective manage-department context from budget subject catalog and BI-AI mapping.
   - Added mismatch warning: imported matched owner department must be in BI-AI mapping manage-department list.
   - Kept existing `bi_ai_source_*` DTO fields instead of shier package's older `control_item_*` rename.

3. Expense budget execution actual routing
   - Added routing for shared `外包服务费` by `budget_release_caliber_mapped`.
   - `日常外包服务费` and `IT外包服务费` are now separated before report aggregation.
   - This addresses the duplicated daily outsource actual amount risk described in the package note.

## Intentionally Not Bulk-Merged

- The package contains many unrelated historical diffs. They were not copied wholesale.
- The BI mapping parser was not downgraded to the package's 5/6-level-only source structure.
- The frontend expense import page was not replaced by the package version because current trunk already supports the three import kinds.

## Validation

- `python3 -m compileall` on touched backend modules: passed.
- `.venv` `app.main` import: passed.
- `ensure_databases()`: passed.
- `apps/web npm run build`: passed, with existing Vite chunk-size warning.
- Behavior probes:
  - `外包服务费 + 日常外包服务费 -> 日常外包服务费`.
  - `外包服务费 + IT外包服务费 -> IT外包服务费`.
  - Manage-department warning appears only when imported department is outside mapping department list.
