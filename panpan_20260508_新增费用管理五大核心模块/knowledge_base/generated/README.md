# 自动生成目录说明

本目录由脚本 `backend/scripts/build_knowledge_base.py` 自动生成。

- `kb_build_report.json`：本次构建的来源数据库、表记录量、时间戳。

建议：

- 将该目录中的报告文件纳入版本管理，便于回溯每次知识库构建状态。
- 若主数据规模变化较大，可对比两次报告中的 `table_counts` 评估数据覆盖质量。
