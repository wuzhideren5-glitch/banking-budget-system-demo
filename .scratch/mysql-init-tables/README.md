# MySQL 初始化建表提取
- 来源 dump: `deploy/mysql/banking_budget_20260623_full.sql.gz`
- 代码补充: `apps/api/app/services/annual_aggregation.py` 中的 `budget_annual_aggregate` 懒初始化表
- 当前 fresh/init 应初始化物理表: 59 张
- 当前 init 还会创建视图: `data_account`, `data_account_metric_binding`
- runtime dump 中额外存在但未纳入当前 fresh/init 表: 4 张

## 当前 fresh/init 表清单

1. `bi_ai_subject_mapping`
2. `budget_annual_aggregate`
3. `budget_data`
4. `budget_output_display_item`
5. `budget_pivot_aggregate`
6. `budget_subject_catalog`
7. `budget_summary`
8. `business_cost_income_indicator`
9. `business_cost_income_item`
10. `business_cost_income_source_mapping`
11. `business_cost_income_value`
12. `compare_budget_summary`
13. `compare_pivot_aggregate`
14. `compare_settings`
15. `compare_sync_job_log`
16. `data_account_metric_node`
17. `databases`
18. `dept_account`
19. `edit_show_version`
20. `expense_actual_detail_raw`
21. `expense_actual_import_batch`
22. `expense_budget_entry`
23. `expense_budget_entry_batch`
24. `expense_forecast_annual_entry`
25. `expense_forecast_calc_result`
26. `expense_forecast_entry`
27. `expense_forecast_override`
28. `expense_forecast_rule`
29. `expense_forecast_rule_param`
30. `expense_forecast_rule_variable`
31. `expense_framework_budget_department`
32. `expense_framework_product_department`
33. `expense_framework_subject`
34. `expense_sync_meta`
35. `feishu_user_binding`
36. `intelligent_budget_tasks`
37. `manage_dept_owner_mapping`
38. `operation_log`
39. `org_product_data_entry_draft`
40. `org_product_data_entry_snapshot`
41. `org_product_data_entry_snapshot_v2`
42. `org_product_metric_table_catalog`
43. `org_product_metric_table_payload`
44. `org_product_output_snapshot_v1`
45. `org_product_tree_snapshot`
46. `period`
47. `settings`
48. `smart_ppt_chart_config`
49. `smart_ppt_instance`
50. `smart_ppt_scene`
51. `smart_report_blueprint`
52. `smart_report_calc_metric`
53. `smart_report_instance`
54. `smart_report_job`
55. `smart_report_template`
56. `smart_report_template_variable`
57. `user_sessions`
58. `users`
59. `version`

## dump 中额外存在但不算当前 fresh/init 的表

- `_data_account_metric_binding`
- `budget_output_display_item_backup_20260618`
- `current_fact`
- `data_account_metric_node_backup_20260618`

## 对应 SQL 文件

- `mysql_required_init_create_tables.sql`
- `mysql_runtime_dump_all_create_tables.sql`
