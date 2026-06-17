---
name: team-submit-packaging-md
description: Create a teammate-facing Markdown guide and clean TeamSubmit source package for the banking budget project. Use when teammates need packaging rules, a packaging MD, or an AI-ready skill for submitting code/features to the maintainer for merge review; this is not a CTO deployment package with env/data/dist.
---

# Team Submit Packaging MD

## Purpose

Produce a clean **team submission package** and a readable Markdown handoff for merge/review.

This skill is for teammate source submissions, not test-server deployment handoff:

- Team submit package: source code, project docs, changed templates, changed initialization/migration code, and a delivery note.
- CTO deployment package: source plus `.env`, live DB/data, `apps/web/dist`, deployment scripts, and runtime assets. Use the CTO release packaging flow instead.

## Default Outputs

Use ASCII-safe names for cross-machine and WeChat handoff stability:

```text
TEAM_SUBMIT_PACKAGING.md
TeamSubmit_YYYYMMDD_name_feature.zip
SUBMISSION_NOTE.md
```

If an automated packaging script is available on the maintainer machine, prefer it. Otherwise use the portable shell command in this skill.

## Required Include Policy

Always include when present:

- `apps/`
- `docs/`
- `README.md`
- `AGENTS.md`
- `CONTEXT.md`
- `CHANGELOG.md`
- `package.json`
- `package-lock.json`
- `skills-lock.json`
- `start.sh`
- `stop.sh`
- `docs/development/test-server-deployment.md`
- `测试服务器部署说明.md` only if this root file exists locally
- `SUBMISSION_NOTE.md`

For older teammate folders, also include legacy roots when present and directly relevant:

- `src/`
- `backend/`
- `Design docs/`
- `download_template/`
- `knowledge_base/`

## Conditional Include Policy

Include these only when the current feature really depends on them:

- `resources/download_template/`: import/export templates changed.
- `resources/knowledge_base/`: agent semantics, prompts, metric definitions, or knowledge-base logic changed.
- `resources/business_inputs/<specific-file>`: a specific workbook/image/CSV is required for the submitted feature.
- Root `*.xlsx`, `*.xls`, `*.csv`, images, or PPT files: only when explicitly referenced in `SUBMISSION_NOTE.md`.
- SQL, migration, bootstrap, init scripts, and DB-impact docs: required when schema, primary key, uniqueness, reconciliation, default rules, org tree, subject tree, metric library, or initialization data changed.

## Exclude Policy

Never include in a team submit source package unless the maintainer explicitly asks for a CTO deployment package:

- `.git/`
- `node_modules/`
- `.venv/`, `.venv312/`, `backend/.venv/`, `apps/api/.venv/`
- `.env`, `.env.local`, secret files, credentials, tokens
- `var/data/`, `data/`, SQLite DB snapshots
- `apps/web/dist/`, root `dist/`
- `archive/`, `releases/`, historical zips, rollback packages, raw teammate packages
- `var/logs/`, `var/pids/`, `outputs/`, backups, caches, generated exports
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.vite/`
- `.DS_Store`, `*.pyc`, `*.log`, `*.pid`, WPS/Excel temp lock files like `.~*` and `~$*`

## Irregular Folder Detection

Do not rely on folder names only. Teammate folders are often named like `最终版`, `0519`, `new`, `panpan打包`, or `新建文件夹`.

Treat a directory as a raw teammate package or historical package and exclude it when it contains:

- Its own `package.json`, `apps/`, `src/`, `backend/`, or `Design docs/` as a nested complete project.
- Zip/rar/7z/tar archives.
- Names or contents suggesting `release`, `releases`, `archive`, `backup`, `回退包`, `历史包`, or another teammate's package.
- Runtime folders such as `node_modules`, `.venv`, `dist`, `var/data`, or DB files.

If there are many Excel/PPT/image files, include only the files explicitly tied to the feature and list their purpose in `SUBMISSION_NOTE.md`.

## Database Change Gate

Never deliver local DB snapshots as the schema change.

If any of these changed, require a separate DB-impact Markdown or Excel before merge:

- New table.
- New field.
- Primary key change.
- Unique constraint change.
- Reconciliation, rollup, mapping, or relationship change.
- Initialization/default data change.
- Department tree, subject tree, metric library, rules, or org structure change.

The DB-impact note must include table name, field name, type, required/default value, key/constraint changes, initialization source, PDD/PRD consistency, and rollback plan.

## Submission Note Template

Create `SUBMISSION_NOTE.md` in the package root:

```markdown
# 本次提交说明

## 本次新增内容

- 新增/修改了什么功能：
- 解决了什么问题：
- 入口页面/菜单位置：

## 修改范围

- 前端：
- 后端：
- 接口：
- 数据库/初始化：
- 模板/Excel：
- 文档：

## 数据库影响

- 是否新增表：
- 是否新增字段：
- 是否修改主键/唯一约束：
- 是否修改钩稽关系：
- 是否需要初始化数据：
- 如有数据库影响，已附数据库影响说明/Excel：

## 依赖与启动

- 是否新增 npm 依赖：
- 是否新增 Python 依赖：
- 是否修改启动端口或环境变量：

## 验证情况

- `npm run build`：
- `python3 -m compileall -q apps/api/app`：
- 页面验证截图/说明：
- 接口验证说明：

## 已知风险

- 风险 1：
- 风险 2：
```

## Preferred Automated Packaging

When the maintainer machine has the team-submit script:

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明"
```

Add precise extras only when required:

```bash
python /Users/penghui/.codex/skills/team-submit/scripts/package_team_submit.py \
  --project-root "$PWD" \
  --name "TeamSubmit_YYYYMMDD_name_feature" \
  --summary "本次新增内容：请填写本次功能说明" \
  --include-download-template \
  --extra "resources/business_inputs/文件名.xlsx"
```

## Portable Manual Packaging

Use this from the project root. It only adds files that exist:

```bash
PACKAGE_NAME="TeamSubmit_YYYYMMDD_name_feature"

INCLUDE_PATHS=()
for path in \
  apps docs src backend "Design docs" \
  README.md AGENTS.md CONTEXT.md CHANGELOG.md \
  package.json package-lock.json skills-lock.json \
  start.sh stop.sh \
  docs/development/test-server-deployment.md \
  测试服务器部署说明.md \
  TEAM_SUBMIT_PACKAGING.md SUBMISSION_NOTE.md
do
  [ -e "$path" ] && INCLUDE_PATHS+=("$path")
done

zip -r "${PACKAGE_NAME}.zip" "${INCLUDE_PATHS[@]}" \
  -x "*/node_modules/*" "*/.venv/*" "*/.venv312/*" "*/.git/*" \
     "*/var/data/*" "*/data/*" "*/dist/*" "*/archive/*" "*/releases/*" \
     "*/var/logs/*" "*/var/pids/*" "*/outputs/*" "*/__pycache__/*" \
     "*/.pytest_cache/*" "*/.mypy_cache/*" "*/.ruff_cache/*" "*/.vite/*" \
     "*.pyc" "*.log" "*.pid" ".DS_Store" "*/.~*" "*/~$*"
```

For changed templates or a specific workbook, add the exact path to `INCLUDE_PATHS`; do not include whole unrelated business-input folders.

## Validation

Run what is feasible and record failures/reasons in `SUBMISSION_NOTE.md`:

```bash
npm run build
python3 -m compileall -q apps/api/app
zip -T TeamSubmit_YYYYMMDD_name_feature.zip
```

Before handoff, inspect the zip:

```bash
zipinfo -1 TeamSubmit_YYYYMMDD_name_feature.zip | rg '(^|/)(node_modules|\.venv|var/data|data|dist|archive|releases)(/|$)|\.env|\.db$'
```

This command should return no forbidden files for a normal team submit package.

## Final Report Format

When finished, report:

- Zip path, size, and file count.
- Delivery note path.
- Whether `apps/`, `docs/`, configs, and required extras are included.
- Whether forbidden runtime/deployment assets are excluded.
- Validation commands run and results.
- Any DB-impact items that still need maintainer confirmation.
