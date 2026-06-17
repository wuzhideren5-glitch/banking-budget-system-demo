# 机构及产品指标与运行引用对齐

## 当前口径

- 机构及产品指标体系是唯一指标配置入口。
- 旧数据科目独立配置入口已下线；`data_account*` 仅作为机构及产品指标运行引用表，承载公式、预算事实和读模型所需的同码绑定结果。
- 机构及产品指标编码、数据科目编码、预算事实 `data_acct_code` 使用同一业务主键。
- 潘潘旧费用类已迁入机构及产品指标体系，不再保留独立迁移区或单独保护页。

## 数据约束

- 第二段为 `99` 的旧保护编码已迁回第二段 `05`。
- 普通叶子编码中的 `99` 可以保留，例如 `A01.21.99` 表示手续费收入下的其他项。
- 旧状态 `PROTECTED_05_REVIEW_ONLY` 不得回流；验证门禁会把它作为旧保护残留直接报错。
- 预算事实、预算展示配置、运行引用节点与绑定表都应引用机构及产品指标主键。

## 验收检查

```bash
sqlite3 var/data/common.db "select count(*) from data_account where data_acct_code glob '*.*' and substr(data_acct_code,instr(data_acct_code,'.')+1,2)='99';"
sqlite3 var/data/common.db "select count(*) from data_account_metric_node where node_code glob '*.*' and substr(node_code,instr(node_code,'.')+1,2)='99';"
sqlite3 var/data/common.db "select count(*) from org_product_metric_table where payload_json like '%PROTECTED_05_REVIEW_ONLY%';"
sqlite3 var/data/budget_2026.db "select count(*) from budget_data where data_acct_code glob '*.*' and substr(data_acct_code,instr(data_acct_code,'.')+1,2)='99';"
```
