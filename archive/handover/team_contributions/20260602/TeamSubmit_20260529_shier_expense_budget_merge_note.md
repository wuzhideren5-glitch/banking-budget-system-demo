# TeamSubmit_20260529_shier_expense_budget 合并说明

## 合并范围

- 本轮只甄别合入部门费用侧功能增量，不整包覆盖当前主线。
- 合入范围包括 BI-AI 科目映射表、费用执行明细三类导入、导入批次导出/删除、费用预算执行报表去年同期读取口径和零值白名单节点展示。
- 当前主线的数据科目体系、部门科目体系、费用预测 `METRIC_EXPR` 规则合同、测试服务器 8443/8009 端口口径均保持不变。

## 功能增量

- `BI-AI科目映射表`：新增 `/api/bi-ai-subject-mapping/list` 与 `/api/bi-ai-subject-mapping/reload`，前端在 BI 映射维护中新增页签展示。
- `费用执行明细导入`：支持 `本年实际导入`、`本年预算导入`、`上年实际导入` 三类 `import_kind`，批次列表、覆盖写入、导出和删除按导入类别隔离。
- `费用执行明细导出`：支持按批次导出匹配结果，导出包含费用大类、费用类别、预算发布口径、归口管理部门2和专项管控打标。
- `费用预算执行报表`：本年实际仅读 `current_year_actual`；去年同期优先读取 `prior_year_actual` 导入明细，无导入时回退年度库数据。
- `费用类型树`：保留 `超额奖金` 这类业务要求固定展示但金额可能为 0 的科目节点。

## 数据库影响

- 本轮涉及新增表和新增字段，已输出确认表：
  - `archive/handover/team_contributions/20260602/TeamSubmit_20260529_shier_expense_budget_db_impact.xlsx`
- 新增表：`bi_ai_subject_mapping`。
- 新增字段：
  - `expense_actual_import_batch.import_kind`
  - `expense_actual_detail_raw.import_kind`
  - `expense_actual_detail_raw.data_date`
  - `expense_actual_detail_raw.journal_name`
  - `expense_actual_detail_raw.serial_no`
  - `expense_actual_detail_raw.line_desc`
  - `expense_actual_detail_raw.fee_major_mapped`
  - `expense_actual_detail_raw.fee_category_mapped`
  - `expense_actual_detail_raw.budget_release_caliber_mapped`
  - `expense_actual_detail_raw.manage_department2`
  - `expense_actual_detail_raw.special_control_tag`
- 不修改既有主键，不修改既有唯一约束，不重建 `dept_account` 或部门预算科目树。
- 用户已确认数据库影响表后执行 scoped 落库；落库前已备份 `var/data/common.db` 到 `var/backups/common_before_team_submit_20260529_expense_schema_20260602_112224.db`。
- 当前现场 `common.db` 已存在 `bi_ai_subject_mapping` 和费用执行导入新增字段；`PRAGMA foreign_key_check` 返回空。

## 配置落库状态

- 业务已补充 `BI科目匹配表.xlsx`，当前已复制到 `resources/business_inputs/BI科目匹配表.xlsx` 并落库到 `bi_ai_subject_mapping`，有效配置 68 条。
- Excel 仅作为重建来源，BI-AI 映射维护、费用执行明细解析和费用预算执行报表均读取数据库配置；除“费用执行明细导入”由用户按期上传 Excel 外，其余映射和规则配置应落库运行。
- 费用执行明细导入已改为优先按“管控口径编码/名称”匹配 BI-AI 映射，最新本年实际导入 342 行全部补齐费用大类、费用类别和预算发布口径。
- 月报格式已按 TeamSubmit 口径读取 `budget_release_caliber_mapped`，业务费用、IT费用、日常费用归口管理和日常费用其他区块不再只按部门预算科目旧口径聚合。

## 验证口径

> 2026-06-03 更新：本文是 TeamSubmit_20260529 合并历史说明。对应验证脚本已归档到 `archive/handover/team_contributions/20260602/validate_team_submit_20260529_expense_merge.py`，不再作为当前 `apps/api/scripts/` 运维入口；当前主线 schema 以 `apps/api/app/db_bootstrap/expense.py` 和当前运行库为准。

- 后端需通过 `compileall` 和 `app.main` 导入，确认新增路由注册。
- 前端需通过 `npm run build`。
- 数据库确认前不直接执行现场库迁移；待确认后由启动链路的幂等 schema 创建/补列逻辑落库。
- 当时新增确认后执行脚本 `archive/handover/team_contributions/20260602/validate_team_submit_20260529_expense_merge.py`。默认模式只复制 `common.db` 并在副本上验证 schema；用户确认数据库影响表后，才可使用 `--apply` 对现场库落库，脚本会先备份 `common.db`。
- 已在 `var/output/merge_validation/common_team_submit_20260529_schema_check.db` 副本上验证 schema 创建/补列逻辑：`bi_ai_subject_mapping` 可创建，`expense_actual_import_batch.import_kind` 和 `expense_actual_detail_raw` 10 个新增字段可补齐，`PRAGMA foreign_key_check` 返回空。
- 已运行归档验证脚本默认 dry-run：副本库 schema 创建/补列成功，现场库当时仍未新增 `bi_ai_subject_mapping` 或 `import_kind` 字段。
- 已使用提交包内 `resources/business_inputs/部门费用执行.xls` 在临时数据目录验证导入预览和写入：预览 342 行，期间为 2026-01 至 2026-04，owner 与预算科目均匹配 342 行，临时库 `prior_year_actual` 写入 342 行。
- 提交包内 `部门费用执行.xls` 只有 16 列，不含 R 列归口管理部门2，因此预览会提示“归口管理部门2未匹配”；这属于样例表字段缺失，不是导入解析失败。

## 已执行落库与回滚

已执行：

```bash
PYTHONPATH=apps/api .venv/bin/python archive/handover/team_contributions/20260602/validate_team_submit_20260529_expense_merge.py --apply
```

执行后已验收/仍建议复核：

```bash
PYTHONPATH=apps/api .venv/bin/python -m compileall -q apps/api/app
npm --workspace apps/web exec tsc -- --noEmit
npm run build
```

如需回滚，使用备份文件 `var/backups/common_before_team_submit_20260529_expense_schema_20260602_112224.db` 覆盖 `var/data/common.db`。
