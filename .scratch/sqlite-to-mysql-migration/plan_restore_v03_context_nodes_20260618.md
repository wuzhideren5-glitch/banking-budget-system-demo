# 计划：v03 上下文节点恢复（MySQL）

日期：2026-06-18  
依赖：`.scratch/sqlite-to-mysql-migration/v03_authority_notes_20260618.md`

## 目标

将 v03 中有、MySQL 无、且**不属于** `.05`/`.99`/`.90`/`.91`（第二段）退休/重建分支的**上下文补全节点** INSERT 到 `data_account_metric_node`。

## 脚本

`apps/api/scripts/restore_v03_context_nodes_to_mysql.py`

```bash
cd apps/api && . .venv/bin/activate
python scripts/restore_v03_context_nodes_to_mysql.py --dry-run
python scripts/restore_v03_context_nodes_to_mysql.py --apply
python scripts/restore_v03_context_nodes_to_mysql.py --verify-only
```

## 验收

- [ ] 排除 §2 退休/过时分支（见 v03_authority_notes）
- [ ] 父节点不存在且不在同批恢复内的 code 跳过
- [ ] 插入后 `_sync_derived_metric_node_identity` 已执行
- [ ] `--verify-only` 对 eligible 列表 0 缺失
- [ ] 活跃节点数 = 2444 + 插入数

## 实测

| 检查项 | 结果 |
|--------|------|
| 导入前活跃节点 | 2444 |
| v03 维护（隐式分组 + 去重） | 6 分组行插入；2 镜像行删除 |
| MySQL 插入（含前两轮 65 + 本轮 12） | **77** |
| 隐式分组修复（parent/table） | **42** 行 UPDATE |
| 导入后活跃节点 | **2521** |
| `--verify-only` | **0** 缺失 |
| 公式 `--verify-only` | **0** mismatch |
