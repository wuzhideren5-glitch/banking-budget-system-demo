# Controlled Resources

`resources/` stores current reusable project resources only. Historical Excel evidence, old generated previews, old import samples, and retired package assets belong under `archive/`, not here.

## Current Areas

当前 `resources/` 顶层目录精确清单（工作树门禁读取）：`business_inputs`, `download_template`, `knowledge_base`。

| Area | Current use |
| --- | --- |
| [`business_inputs/`](business_inputs/) | Current source workbooks and decks used as business evidence or rebuild sources. Every file must be listed in `business_inputs/README.md`. |
| [`download_template/`](download_template/) | Current downloadable/import templates used by the product. Every file must be listed in `download_template/README.md`. |
| [`knowledge_base/`](knowledge_base/) | Current Agent knowledge-base seeds, prompt resources, generated config, and quickstart docs. Each first-level knowledge layer must keep its own `README.md`. |

## Rules

- New business-input files must be listed in the exact file list in `business_inputs/README.md`.
- New downloadable/import templates must be listed in the exact file list in `download_template/README.md`.
- Remove retired file names from those exact lists when files move to `archive/`.
- Old samples, review drafts, generated HTML, test exports, and migrated historical workbooks go to `archive/handover/legacy_import_workbooks/` or `archive/runtime_snapshots/generated_outputs/`.
- Runtime logs, outputs, and database backups go to `var/`, not `resources/`.
