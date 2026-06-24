-- All CREATE TABLE statements extracted from deploy/mysql/banking_budget_20260623_full.sql.gz

-- table: _data_account_metric_binding
CREATE TABLE `_data_account_metric_binding` (
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_node_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_type` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`data_acct_code`),
  UNIQUE KEY `metric_node_code` (`metric_node_code`,`scope_code`),
  CONSTRAINT `_data_account_metric_binding_chk_1` CHECK ((`scope_type` in (_utf8mb4'PRODUCT',_utf8mb4'CORP'))),
  CONSTRAINT `_data_account_metric_binding_chk_2` CHECK ((`data_acct_code` = `metric_node_code`)),
  CONSTRAINT `_data_account_metric_binding_chk_3` CHECK ((`scope_code` = substr(`metric_node_code`,1,(locate(_utf8mb4'.',`metric_node_code`) - 1)))),
  CONSTRAINT `_data_account_metric_binding_chk_4` CHECK ((((`scope_type` = _utf8mb4'CORP') and (`scope_code` = _utf8mb4'CORP')) or ((`scope_type` = _utf8mb4'PRODUCT') and (`scope_code` <> _utf8mb4'CORP'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: bi_ai_subject_mapping
CREATE TABLE `bi_ai_subject_mapping` (
  `id` int NOT NULL AUTO_INCREMENT,
  `level5_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `level5_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `level6_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `level6_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `budget_release_caliber` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `fee_category` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `fee_major` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `manage_department_override` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `sort_order` int NOT NULL DEFAULT '0',
  `source_file` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `created_at` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `level6_code` (`level6_code`,`level6_name`,`sort_order`)
) ENGINE=InnoDB AUTO_INCREMENT=137 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_data
CREATE TABLE `budget_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `period_id` int NOT NULL,
  `budget_actual` tinyint(1) NOT NULL,
  `version_id` int NOT NULL,
  `value` double NOT NULL DEFAULT '0',
  `formula_value` double DEFAULT NULL,
  `manual_value` double DEFAULT NULL,
  `value_source` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `need_calc` tinyint(1) NOT NULL DEFAULT '1',
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `budget_year` (`budget_year`,`data_acct_code`,`product_code`,`period_id`,`version_id`,`budget_actual`),
  KEY `version_id` (`version_id`),
  KEY `idx_budget_data_year` (`budget_year`),
  KEY `idx_budget_data_lookup` (`budget_year`,`data_acct_code`,`product_code`,`version_id`),
  CONSTRAINT `budget_data_ibfk_1` FOREIGN KEY (`version_id`) REFERENCES `version` (`version_id`),
  CONSTRAINT `budget_data_chk_1` CHECK ((`budget_actual` in (0,1))),
  CONSTRAINT `budget_data_chk_2` CHECK ((`value_source` in (_utf8mb4'manual',_utf8mb4'formula',_utf8mb4'none',_utf8mb4'rollup')))
) ENGINE=InnoDB AUTO_INCREMENT=2029484894 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_output_display_item
CREATE TABLE `budget_output_display_item` (
  `row_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_view` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_row_key` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_ref` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_entity_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_table_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_metric_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_metric_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `row_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `level` int NOT NULL DEFAULT '1',
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  PRIMARY KEY (`row_key`),
  KEY `idx_budget_output_display_item_order` (`display_view`,`is_active`,`sort_order`,`row_key`),
  KEY `idx_budget_output_display_item_parent` (`parent_row_key`),
  CONSTRAINT `budget_output_display_item_ibfk_1` FOREIGN KEY (`parent_row_key`) REFERENCES `budget_output_display_item` (`row_key`) ON DELETE SET NULL,
  CONSTRAINT `budget_output_display_item_chk_1` CHECK ((`row_type` in (_utf8mb4'GROUP',_utf8mb4'METRIC'))),
  CONSTRAINT `budget_output_display_item_chk_2` CHECK ((`is_active` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_output_display_item_backup_20260618
CREATE TABLE `budget_output_display_item_backup_20260618` (
  `row_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_view` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_row_key` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_ref` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_entity_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_table_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_metric_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_product_metric_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `row_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `level` int NOT NULL DEFAULT '1',
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_pivot_aggregate
CREATE TABLE `budget_pivot_aggregate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `grain` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level4` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level5` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_code_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_code_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quarter` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_actual` tinyint(1) NOT NULL,
  `version_id` int NOT NULL,
  `version_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `value` double NOT NULL DEFAULT '0',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_source` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_budget_pivot_aggregate_year` (`budget_year`),
  KEY `idx_budget_pivot_aggregate_grain` (`grain`),
  KEY `idx_budget_pivot_aggregate_version` (`version_id`,`grain`),
  CONSTRAINT `budget_pivot_aggregate_chk_1` CHECK ((`grain` in (_utf8mb4'year',_utf8mb4'quarter',_utf8mb4'month'))),
  CONSTRAINT `budget_pivot_aggregate_chk_2` CHECK ((`budget_actual` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=2027933312 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_subject_catalog
CREATE TABLE `budget_subject_catalog` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parent_id` int DEFAULT NULL,
  `level_number` int NOT NULL,
  `subject_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `manage_department` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `formula_text` text COLLATE utf8mb4_unicode_ci,
  `sort_order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `budget_subject_catalog_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `budget_subject_catalog_chk_1` CHECK ((`level_number` between 1 and 5))
) ENGINE=InnoDB AUTO_INCREMENT=61 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: budget_summary
CREATE TABLE `budget_summary` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `metric_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level4` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level5` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_code_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_code_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quarter` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_actual` tinyint(1) NOT NULL,
  `version_id` int NOT NULL,
  `version_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `value` double NOT NULL DEFAULT '0',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_source` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `version_id` (`version_id`),
  KEY `idx_budget_summary_year` (`budget_year`),
  CONSTRAINT `budget_summary_ibfk_1` FOREIGN KEY (`version_id`) REFERENCES `version` (`version_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2030340095 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: business_cost_income_indicator
CREATE TABLE `business_cost_income_indicator` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL DEFAULT '2026',
  `product_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_id` int DEFAULT NULL,
  `display_group` int NOT NULL DEFAULT '0',
  `topic_metric_node_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `numerator_section` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `numerator_item_id` int NOT NULL,
  `numerator_value_mode` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'tree',
  `denominator_section` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `denominator_item_id` int NOT NULL,
  `denominator_value_mode` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'tree',
  `format` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ratio',
  `annualize` int NOT NULL DEFAULT '0',
  `sort_order` int NOT NULL DEFAULT '0',
  `enabled` int NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  KEY `numerator_item_id` (`numerator_item_id`),
  KEY `denominator_item_id` (`denominator_item_id`),
  KEY `idx_bci_indicator_enabled` (`product_code`,`enabled`,`sort_order`,`id`),
  CONSTRAINT `business_cost_income_indicator_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `business_cost_income_indicator` (`id`),
  CONSTRAINT `business_cost_income_indicator_ibfk_2` FOREIGN KEY (`numerator_item_id`) REFERENCES `business_cost_income_item` (`id`) ON DELETE CASCADE,
  CONSTRAINT `business_cost_income_indicator_ibfk_3` FOREIGN KEY (`denominator_item_id`) REFERENCES `business_cost_income_item` (`id`) ON DELETE CASCADE,
  CONSTRAINT `business_cost_income_indicator_chk_1` CHECK ((`display_group` in (0,1))),
  CONSTRAINT `business_cost_income_indicator_chk_2` CHECK ((`numerator_section` in (_utf8mb4'input',_utf8mb4'output'))),
  CONSTRAINT `business_cost_income_indicator_chk_3` CHECK ((`numerator_value_mode` in (_utf8mb4'tree',_utf8mb4'self',_utf8mb4'self_and_tree'))),
  CONSTRAINT `business_cost_income_indicator_chk_4` CHECK ((`denominator_section` in (_utf8mb4'input',_utf8mb4'output'))),
  CONSTRAINT `business_cost_income_indicator_chk_5` CHECK ((`denominator_value_mode` in (_utf8mb4'tree',_utf8mb4'self',_utf8mb4'self_and_tree'))),
  CONSTRAINT `business_cost_income_indicator_chk_6` CHECK ((`format` in (_utf8mb4'ratio',_utf8mb4'percent',_utf8mb4'number'))),
  CONSTRAINT `business_cost_income_indicator_chk_7` CHECK ((`annualize` in (0,1))),
  CONSTRAINT `business_cost_income_indicator_chk_8` CHECK ((`enabled` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=2026000267 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: business_cost_income_item
CREATE TABLE `business_cost_income_item` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL DEFAULT '2026',
  `product_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `section` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_id` int DEFAULT NULL,
  `display_group` int NOT NULL DEFAULT '0',
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `org_product_ref` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `org_product_entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `org_product_table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `org_product_metric_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `org_product_metric_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `manual_entry_mode` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'disabled',
  `value_mode` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'tree',
  `sort_order` int NOT NULL DEFAULT '0',
  `enabled` int NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_bci_item_year_product_section_name` (`budget_year`,`product_code`,`section`,`name`),
  KEY `parent_id` (`parent_id`),
  KEY `idx_bci_item_section` (`product_code`,`section`,`sort_order`,`id`),
  CONSTRAINT `business_cost_income_item_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `business_cost_income_item` (`id`),
  CONSTRAINT `business_cost_income_item_chk_1` CHECK ((`section` in (_utf8mb4'input',_utf8mb4'output'))),
  CONSTRAINT `business_cost_income_item_chk_2` CHECK ((`display_group` in (0,1))),
  CONSTRAINT `business_cost_income_item_chk_3` CHECK ((`manual_entry_mode` in (_utf8mb4'disabled',_utf8mb4'manual',_utf8mb4'manual_preferred'))),
  CONSTRAINT `business_cost_income_item_chk_4` CHECK ((`value_mode` in (_utf8mb4'tree',_utf8mb4'self',_utf8mb4'self_and_tree'))),
  CONSTRAINT `business_cost_income_item_chk_5` CHECK ((`enabled` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=2026000573 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: business_cost_income_source_mapping
CREATE TABLE `business_cost_income_source_mapping` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL DEFAULT '2026',
  `item_id` int NOT NULL,
  `field` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `data_acct_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `agg_method` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'sum',
  `filters_json` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '{}',
  `enabled` int NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_bci_source_mapping_year_item_field_code` (`budget_year`,`item_id`,`field`,`data_acct_code`),
  KEY `idx_bci_source_mapping_item` (`item_id`,`field`,`enabled`,`id`),
  CONSTRAINT `business_cost_income_source_mapping_ibfk_1` FOREIGN KEY (`item_id`) REFERENCES `business_cost_income_item` (`id`) ON DELETE CASCADE,
  CONSTRAINT `business_cost_income_source_mapping_chk_1` CHECK ((`field` in (_utf8mb4'actual',_utf8mb4'budget'))),
  CONSTRAINT `business_cost_income_source_mapping_chk_2` CHECK ((`enabled` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: business_cost_income_value
CREATE TABLE `business_cost_income_value` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL DEFAULT '2026',
  `year` int NOT NULL,
  `month` int NOT NULL,
  `entity_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `group_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `product_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `item_section` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_id` int NOT NULL,
  `field` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` double NOT NULL DEFAULT '0',
  `update_time` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_bci_value_year_lookup` (`budget_year`,`year`,`month`,`entity_name`,`group_name`,`product_code`,`item_section`,`item_id`,`field`),
  KEY `item_id` (`item_id`),
  KEY `idx_bci_value_lookup` (`year`,`entity_name`,`group_name`,`product_code`,`item_section`,`item_id`,`field`,`month`),
  CONSTRAINT `business_cost_income_value_ibfk_1` FOREIGN KEY (`item_id`) REFERENCES `business_cost_income_item` (`id`) ON DELETE CASCADE,
  CONSTRAINT `business_cost_income_value_chk_1` CHECK ((`month` between 1 and 12)),
  CONSTRAINT `business_cost_income_value_chk_2` CHECK ((`item_section` in (_utf8mb4'input',_utf8mb4'output'))),
  CONSTRAINT `business_cost_income_value_chk_3` CHECK ((`field` in (_utf8mb4'actual',_utf8mb4'budget',_utf8mb4'forecast')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: compare_budget_summary
CREATE TABLE `compare_budget_summary` (
  `id` int NOT NULL AUTO_INCREMENT,
  `show_level` int NOT NULL,
  `data_file_id` int NOT NULL,
  `source_year` int NOT NULL,
  `source_version_id` int NOT NULL,
  `source_version_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level4` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level5` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_code_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_code_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quarter` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_actual` tinyint(1) NOT NULL,
  `value` double NOT NULL DEFAULT '0',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_source` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `sync_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_compare_budget_summary_show_level` (`show_level`),
  KEY `idx_compare_budget_summary_source` (`source_year`,`source_version_id`),
  CONSTRAINT `compare_budget_summary_chk_1` CHECK ((`show_level` between 1 and 5)),
  CONSTRAINT `compare_budget_summary_chk_2` CHECK ((`budget_actual` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=4849 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: compare_pivot_aggregate
CREATE TABLE `compare_pivot_aggregate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `grain` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `show_level` int NOT NULL,
  `data_file_id` int NOT NULL,
  `source_year` int NOT NULL,
  `source_version_id` int NOT NULL,
  `source_version_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level4` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_level5` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dept_level3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `data_code_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_code_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `year` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quarter` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_actual` tinyint(1) NOT NULL,
  `value` double NOT NULL DEFAULT '0',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_source` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'manual',
  `sync_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_compare_pivot_aggregate_grain` (`grain`),
  KEY `idx_compare_pivot_aggregate_level` (`show_level`,`grain`),
  CONSTRAINT `compare_pivot_aggregate_chk_1` CHECK ((`grain` in (_utf8mb4'year',_utf8mb4'quarter',_utf8mb4'month'))),
  CONSTRAINT `compare_pivot_aggregate_chk_2` CHECK ((`show_level` between 1 and 5)),
  CONSTRAINT `compare_pivot_aggregate_chk_3` CHECK ((`budget_actual` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: compare_settings
CREATE TABLE `compare_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `setting_key` (`setting_key`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: compare_sync_job_log
CREATE TABLE `compare_sync_job_log` (
  `job_id` int NOT NULL AUTO_INCREMENT,
  `start_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `end_time` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `trigger_source` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` text COLLATE utf8mb4_unicode_ci,
  `operator_user_id` int DEFAULT NULL,
  PRIMARY KEY (`job_id`)
) ENGINE=InnoDB AUTO_INCREMENT=545 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: current_fact
CREATE TABLE `current_fact` (
  `id` int NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: data_account_metric_node
CREATE TABLE `data_account_metric_node` (
  `node_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `node_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `product_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `local_metric_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logic_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `functional_group_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `level` int NOT NULL,
  `node_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `horizontal_rollup` tinyint(1) NOT NULL DEFAULT '0',
  `vertical_rollup` tinyint(1) NOT NULL DEFAULT '0',
  `runtime_account_enabled` tinyint(1) NOT NULL DEFAULT '0',
  `budget_formula` text COLLATE utf8mb4_unicode_ci,
  `actual_formula` text COLLATE utf8mb4_unicode_ci,
  `budget_rule_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `budget_rule_config_json` json DEFAULT NULL,
  `need_calc` tinyint(1) NOT NULL DEFAULT '0',
  `formula_calc_mode` tinyint(1) NOT NULL DEFAULT '0',
  `allow_manual_entry` tinyint(1) NOT NULL DEFAULT '1',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '金额',
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `annual_agg_rule` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `nature` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '其他',
  PRIMARY KEY (`node_code`),
  KEY `idx_data_account_metric_node_parent` (`parent_code`),
  CONSTRAINT `data_account_metric_node_ibfk_1` FOREIGN KEY (`parent_code`) REFERENCES `data_account_metric_node` (`node_code`),
  CONSTRAINT `data_account_metric_node_chk_1` CHECK ((`level` between 1 and 8)),
  CONSTRAINT `data_account_metric_node_chk_2` CHECK ((`node_type` in (_utf8mb4'CATEGORY',_utf8mb4'GROUP',_utf8mb4'METRIC'))),
  CONSTRAINT `data_account_metric_node_chk_3` CHECK ((`horizontal_rollup` in (0,1))),
  CONSTRAINT `data_account_metric_node_chk_4` CHECK ((`vertical_rollup` in (0,1))),
  CONSTRAINT `data_account_metric_node_chk_5` CHECK ((`runtime_account_enabled` in (0,1))),
  CONSTRAINT `data_account_metric_node_chk_6` CHECK ((`need_calc` in (0,1))),
  CONSTRAINT `data_account_metric_node_chk_7` CHECK ((`formula_calc_mode` between 0 and 3)),
  CONSTRAINT `data_account_metric_node_chk_8` CHECK ((`allow_manual_entry` in (0,1))),
  CONSTRAINT `data_account_metric_node_chk_9` CHECK ((`is_active` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: data_account_metric_node_backup_20260618
CREATE TABLE `data_account_metric_node_backup_20260618` (
  `node_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `node_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `product_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `local_metric_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logic_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `functional_group_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `metric_table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `level` int NOT NULL,
  `node_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `horizontal_rollup` tinyint(1) NOT NULL DEFAULT '0',
  `vertical_rollup` tinyint(1) NOT NULL DEFAULT '0',
  `runtime_account_enabled` tinyint(1) NOT NULL DEFAULT '0',
  `budget_formula` text COLLATE utf8mb4_unicode_ci,
  `actual_formula` text COLLATE utf8mb4_unicode_ci,
  `budget_rule_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `budget_rule_config_json` json DEFAULT NULL,
  `need_calc` tinyint(1) NOT NULL DEFAULT '0',
  `formula_calc_mode` tinyint(1) NOT NULL DEFAULT '0',
  `allow_manual_entry` tinyint(1) NOT NULL DEFAULT '1',
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '金额',
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `annual_agg_rule` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: databases
CREATE TABLE `databases` (
  `id` int NOT NULL AUTO_INCREMENT,
  `data_file_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year` int NOT NULL,
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `data_file_name` (`data_file_name`)
) ENGINE=InnoDB AUTO_INCREMENT=612 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: dept_account
CREATE TABLE `dept_account` (
  `dept_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dept_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '微众银行',
  `parent_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `level` int NOT NULL,
  `is_leaf` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`dept_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: edit_show_version
CREATE TABLE `edit_show_version` (
  `id` int NOT NULL AUTO_INCREMENT,
  `data_file_id` int NOT NULL,
  `version_id` int NOT NULL,
  `edit_show_sign` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `data_file_id` (`data_file_id`),
  CONSTRAINT `edit_show_version_ibfk_1` FOREIGN KEY (`data_file_id`) REFERENCES `databases` (`id`),
  CONSTRAINT `edit_show_version_chk_1` CHECK ((`edit_show_sign` between 0 and 5))
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_actual_detail_raw
CREATE TABLE `expense_actual_detail_raw` (
  `id` int NOT NULL AUTO_INCREMENT,
  `batch_id` int DEFAULT NULL,
  `import_kind` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'current_year_actual',
  `data_date` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `period_ym` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `period_text` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `org_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dep_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dep_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subject_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subject_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `journal_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `serial_no` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `line_desc` text COLLATE utf8mb4_unicode_ci,
  `amount` double NOT NULL DEFAULT '0',
  `fee_type_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fee_type_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bi_ai_source_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bi_ai_source_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manage_department_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_name_raw` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_name_mapped` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `monthly_caliber` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `budget_subject_raw` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `budget_subject_mapped` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fee_major_mapped` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fee_category_mapped` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `budget_release_caliber_mapped` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manage_department2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `special_control_tag` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_matched` tinyint(1) NOT NULL DEFAULT '0',
  `subject_matched` tinyint(1) NOT NULL DEFAULT '0',
  `match_note` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  KEY `batch_id` (`batch_id`),
  CONSTRAINT `expense_actual_detail_raw_ibfk_1` FOREIGN KEY (`batch_id`) REFERENCES `expense_actual_import_batch` (`id`) ON DELETE SET NULL,
  CONSTRAINT `expense_actual_detail_raw_chk_1` CHECK ((`owner_matched` in (0,1))),
  CONSTRAINT `expense_actual_detail_raw_chk_2` CHECK ((`subject_matched` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=2446 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_actual_import_batch
CREATE TABLE `expense_actual_import_batch` (
  `id` int NOT NULL AUTO_INCREMENT,
  `import_kind` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'current_year_actual',
  `file_name` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `import_mode` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `periods_text` text COLLATE utf8mb4_unicode_ci,
  `total_rows` int NOT NULL DEFAULT '0',
  `matched_owner_rows` int NOT NULL DEFAULT '0',
  `matched_subject_rows` int NOT NULL DEFAULT '0',
  `unmatched_rows` int NOT NULL DEFAULT '0',
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_budget_entry
CREATE TABLE `expense_budget_entry` (
  `id` int NOT NULL AUTO_INCREMENT,
  `batch_id` int DEFAULT NULL,
  `budget_year` int NOT NULL,
  `owner_name_raw` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name_mapped` text COLLATE utf8mb4_unicode_ci,
  `budget_subject_raw` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_subject_mapped` text COLLATE utf8mb4_unicode_ci,
  `amount` double NOT NULL DEFAULT '0',
  `adjustment_amount` double NOT NULL DEFAULT '0',
  `owner_matched` int NOT NULL DEFAULT '0',
  `subject_matched` int NOT NULL DEFAULT '0',
  `match_note` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  KEY `idx_expense_budget_entry_year` (`budget_year`),
  KEY `idx_expense_budget_entry_batch` (`batch_id`),
  CONSTRAINT `expense_budget_entry_ibfk_1` FOREIGN KEY (`batch_id`) REFERENCES `expense_budget_entry_batch` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_budget_entry_chk_1` CHECK ((`owner_matched` in (0,1))),
  CONSTRAINT `expense_budget_entry_chk_2` CHECK ((`subject_matched` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=360 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_budget_entry_batch
CREATE TABLE `expense_budget_entry_batch` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `file_name` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `import_mode` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `total_rows` int NOT NULL DEFAULT '0',
  `matched_rows` int NOT NULL DEFAULT '0',
  `unmatched_rows` int NOT NULL DEFAULT '0',
  `created_at` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_annual_entry
CREATE TABLE `expense_forecast_annual_entry` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_year` int NOT NULL,
  `forecast_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_value` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_id` int NOT NULL,
  `field_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `field_value` double NOT NULL DEFAULT '0',
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_year` (`forecast_year`,`forecast_version`,`scope_type`,`scope_value`,`subject_id`,`field_name`),
  KEY `subject_id` (`subject_id`),
  KEY `idx_expense_forecast_annual_lookup` (`forecast_year`,`forecast_version`,`scope_type`,`scope_value`),
  CONSTRAINT `expense_forecast_annual_entry_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_annual_entry_chk_1` CHECK ((`scope_type` in (_utf8mb4'entity',_utf8mb4'group',_utf8mb4'owner'))),
  CONSTRAINT `expense_forecast_annual_entry_chk_2` CHECK ((`field_name` in (_utf8mb4'business_submission',_utf8mb4'capital_advice')))
) ENGINE=InnoDB AUTO_INCREMENT=315 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_calc_result
CREATE TABLE `expense_forecast_calc_result` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_year` int NOT NULL,
  `forecast_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_id` int NOT NULL,
  `month` int NOT NULL,
  `rule_id` int DEFAULT NULL,
  `calc_value` double NOT NULL DEFAULT '0',
  `calc_basis_json` json DEFAULT NULL,
  `calc_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ok',
  `calc_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_year` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`,`month`),
  KEY `subject_id` (`subject_id`),
  KEY `rule_id` (`rule_id`),
  KEY `idx_expense_forecast_calc_lookup` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`),
  CONSTRAINT `expense_forecast_calc_result_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_calc_result_ibfk_2` FOREIGN KEY (`rule_id`) REFERENCES `expense_forecast_rule` (`id`) ON DELETE SET NULL,
  CONSTRAINT `expense_forecast_calc_result_chk_1` CHECK ((`month` between 1 and 12))
) ENGINE=InnoDB AUTO_INCREMENT=1251 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_entry
CREATE TABLE `expense_forecast_entry` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_year` int NOT NULL,
  `forecast_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_value` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_id` int NOT NULL,
  `month` int NOT NULL,
  `forecast_value` double NOT NULL DEFAULT '0',
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_year` (`forecast_year`,`forecast_version`,`scope_type`,`scope_value`,`subject_id`,`month`),
  KEY `subject_id` (`subject_id`),
  KEY `idx_expense_forecast_lookup` (`forecast_year`,`forecast_version`,`scope_type`,`scope_value`),
  CONSTRAINT `expense_forecast_entry_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_entry_chk_1` CHECK ((`scope_type` in (_utf8mb4'entity',_utf8mb4'group',_utf8mb4'owner'))),
  CONSTRAINT `expense_forecast_entry_chk_2` CHECK ((`month` between 1 and 12))
) ENGINE=InnoDB AUTO_INCREMENT=1256 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_override
CREATE TABLE `expense_forecast_override` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_year` int NOT NULL,
  `forecast_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_id` int NOT NULL,
  `month` int NOT NULL,
  `rule_id` int DEFAULT NULL,
  `system_value` double NOT NULL DEFAULT '0',
  `override_value` double NOT NULL DEFAULT '0',
  `override_reason` text COLLATE utf8mb4_unicode_ci,
  `operator_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_year` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`,`month`),
  KEY `subject_id` (`subject_id`),
  KEY `rule_id` (`rule_id`),
  KEY `idx_expense_forecast_override_lookup` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`),
  CONSTRAINT `expense_forecast_override_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_override_ibfk_2` FOREIGN KEY (`rule_id`) REFERENCES `expense_forecast_rule` (`id`) ON DELETE SET NULL,
  CONSTRAINT `expense_forecast_override_chk_1` CHECK ((`month` between 1 and 12))
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_rule
CREATE TABLE `expense_forecast_rule` (
  `id` int NOT NULL AUTO_INCREMENT,
  `forecast_year` int NOT NULL,
  `forecast_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_id` int NOT NULL,
  `scheme_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `allow_manual_override` tinyint(1) NOT NULL DEFAULT '0',
  `auto_refresh_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `manual_recalc_enabled` tinyint(1) NOT NULL DEFAULT '1',
  `metric_source_priority` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'metric_first',
  `effective_from_month` int NOT NULL DEFAULT '1',
  `effective_to_month` int NOT NULL DEFAULT '12',
  `priority` int NOT NULL DEFAULT '100',
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forecast_year` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`),
  KEY `subject_id` (`subject_id`),
  KEY `idx_expense_forecast_rule_lookup` (`forecast_year`,`forecast_version`,`owner_name`,`subject_id`),
  CONSTRAINT `expense_forecast_rule_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `budget_subject_catalog` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_rule_chk_1` CHECK ((`scheme_code` in (_utf8mb4'MANUAL',_utf8mb4'RESIDUAL_ALLOC',_utf8mb4'METRIC_EXPR'))),
  CONSTRAINT `expense_forecast_rule_chk_2` CHECK ((`metric_source_priority` in (_utf8mb4'metric_first',_utf8mb4'inline_first'))),
  CONSTRAINT `expense_forecast_rule_chk_3` CHECK ((`effective_from_month` between 1 and 12)),
  CONSTRAINT `expense_forecast_rule_chk_4` CHECK ((`effective_to_month` between 1 and 12))
) ENGINE=InnoDB AUTO_INCREMENT=163 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_rule_param
CREATE TABLE `expense_forecast_rule_param` (
  `id` int NOT NULL AUTO_INCREMENT,
  `rule_id` int NOT NULL,
  `param_group` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'common',
  `param_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `param_value` text COLLATE utf8mb4_unicode_ci,
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'string',
  PRIMARY KEY (`id`),
  UNIQUE KEY `rule_id` (`rule_id`,`param_group`,`param_key`),
  CONSTRAINT `expense_forecast_rule_param_ibfk_1` FOREIGN KEY (`rule_id`) REFERENCES `expense_forecast_rule` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=943 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_forecast_rule_variable
CREATE TABLE `expense_forecast_rule_variable` (
  `id` int NOT NULL AUTO_INCREMENT,
  `rule_id` int NOT NULL,
  `variable_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `variable_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_key` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_subkey` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `default_value` double DEFAULT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_expense_forecast_rule_variable_rule` (`rule_id`,`sort_order`,`id`),
  CONSTRAINT `expense_forecast_rule_variable_ibfk_1` FOREIGN KEY (`rule_id`) REFERENCES `expense_forecast_rule` (`id`) ON DELETE CASCADE,
  CONSTRAINT `expense_forecast_rule_variable_chk_1` CHECK ((`source_type` in (_utf8mb4'metric_tree',_utf8mb4'forecast_inline',_utf8mb4'actual',_utf8mb4'annual_field',_utf8mb4'constant')))
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_framework_budget_department
CREATE TABLE `expense_framework_budget_department` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `group_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `budget_department` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `group_name` (`group_name`,`owner_name`,`budget_department`)
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_framework_product_department
CREATE TABLE `expense_framework_product_department` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `group_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_department` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `group_name` (`group_name`,`owner_name`,`product_department`)
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_framework_subject
CREATE TABLE `expense_framework_subject` (
  `budget_subject` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `level_label` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manage_department` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `formula_text` text COLLATE utf8mb4_unicode_ci,
  `sort_order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`budget_subject`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: expense_sync_meta
CREATE TABLE `expense_sync_meta` (
  `sync_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_mtime` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `synced_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `row_count` int NOT NULL DEFAULT '0',
  `note` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`sync_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: feishu_user_binding
CREATE TABLE `feishu_user_binding` (
  `open_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`open_id`),
  KEY `idx_feishu_user_binding_user_id` (`user_id`),
  CONSTRAINT `feishu_user_binding_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: intelligent_budget_tasks
CREATE TABLE `intelligent_budget_tasks` (
  `task_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_text` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parsed_target` longtext COLLATE utf8mb4_unicode_ci,
  `status` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `stage` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `step_summary` longtext COLLATE utf8mb4_unicode_ci,
  `baseline_solution` longtext COLLATE utf8mb4_unicode_ci,
  `solutions` longtext COLLATE utf8mb4_unicode_ci,
  `negotiation_message` longtext COLLATE utf8mb4_unicode_ci,
  `negotiation_suggestions` longtext COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT (now()),
  PRIMARY KEY (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: manage_dept_owner_mapping
CREATE TABLE `manage_dept_owner_mapping` (
  `id` int NOT NULL AUTO_INCREMENT,
  `manage_department` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_department` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `manage_department` (`manage_department`)
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: operation_log
CREATE TABLE `operation_log` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `action_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_desc` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_table` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `affected_rows` int DEFAULT NULL,
  `before_data` text COLLATE utf8mb4_unicode_ci,
  `after_data` text COLLATE utf8mb4_unicode_ci,
  `ip_address` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`log_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3134 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_data_entry_draft
CREATE TABLE `org_product_data_entry_draft` (
  `user_id` int NOT NULL,
  `user_display_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year` int NOT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_json` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`user_id`,`entity_code`,`year`,`table_name`),
  KEY `idx_org_product_data_entry_draft_entity_year` (`entity_code`,`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_data_entry_snapshot
CREATE TABLE `org_product_data_entry_snapshot` (
  `entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year` int NOT NULL,
  `month_index` int DEFAULT NULL,
  `table_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload_json` longtext COLLATE utf8mb4_unicode_ci,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`entity_code`,`year`),
  KEY `idx_org_product_data_entry_snapshot_entity` (`entity_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_data_entry_snapshot_v2
CREATE TABLE `org_product_data_entry_snapshot_v2` (
  `entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year` int NOT NULL,
  `version_id` int NOT NULL,
  `version_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month_index` int DEFAULT NULL,
  `table_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload_json` longtext COLLATE utf8mb4_unicode_ci,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`entity_code`,`year`,`version_id`,`table_name`),
  KEY `idx_org_product_data_entry_snapshot_v2_entity_year` (`entity_code`,`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_metric_table_catalog
CREATE TABLE `org_product_metric_table_catalog` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entity_scope` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  `status` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `remark` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `entity_scope` (`entity_scope`,`table_name`),
  KEY `idx_test_compat_check` (`entity_scope`,`sort_order`),
  KEY `idx_test_direct_connect` (`entity_scope`,`sort_order`),
  KEY `idx_org_product_metric_table_catalog_scope` (`entity_scope`,`sort_order`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_metric_table_payload
CREATE TABLE `org_product_metric_table_payload` (
  `entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_json` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`entity_code`,`table_name`),
  KEY `idx_org_product_metric_table_payload_entity` (`entity_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_output_snapshot_v1
CREATE TABLE `org_product_output_snapshot_v1` (
  `entity_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year` int NOT NULL,
  `input_version_id` int NOT NULL,
  `output_version_id` int NOT NULL,
  `output_version_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_json` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`entity_code`,`year`,`input_version_id`,`output_version_id`,`table_name`),
  KEY `idx_org_product_output_snapshot_entity_year` (`entity_code`,`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: org_product_tree_snapshot
CREATE TABLE `org_product_tree_snapshot` (
  `id` int NOT NULL,
  `payload_json` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `org_product_tree_snapshot_chk_1` CHECK ((`id` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: period
CREATE TABLE `period` (
  `period_id` int NOT NULL AUTO_INCREMENT,
  `year` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `month` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quarter` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `year_month` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `days` int NOT NULL,
  PRIMARY KEY (`period_id`),
  UNIQUE KEY `year_month` (`year_month`)
) ENGINE=InnoDB AUTO_INCREMENT=3049 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: settings
CREATE TABLE `settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `setting_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `budget_year` (`budget_year`,`setting_key`),
  KEY `idx_settings_year` (`budget_year`)
) ENGINE=InnoDB AUTO_INCREMENT=2026001709 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_ppt_chart_config
CREATE TABLE `smart_ppt_chart_config` (
  `config_id` int NOT NULL AUTO_INCREMENT,
  `config_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `chart_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_config_json` json NOT NULL,
  `visual_config_json` json DEFAULT NULL,
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`config_id`),
  UNIQUE KEY `config_code` (`config_code`)
) ENGINE=InnoDB AUTO_INCREMENT=221 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_ppt_instance
CREATE TABLE `smart_ppt_instance` (
  `instance_id` int NOT NULL AUTO_INCREMENT,
  `scene_id` int NOT NULL,
  `instance_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parameter_values_json` json NOT NULL,
  `output_file_path` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `generation_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `last_generated_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`instance_id`),
  KEY `idx_smart_ppt_instance_scene` (`scene_id`,`created_at` DESC),
  CONSTRAINT `smart_ppt_instance_ibfk_1` FOREIGN KEY (`scene_id`) REFERENCES `smart_ppt_scene` (`scene_id`),
  CONSTRAINT `smart_ppt_instance_chk_1` CHECK ((`generation_status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'success',_utf8mb4'failed')))
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_ppt_scene
CREATE TABLE `smart_ppt_scene` (
  `scene_id` int NOT NULL AUTO_INCREMENT,
  `scene_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scene_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scene_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'board',
  `description` text COLLATE utf8mb4_unicode_ci,
  `slide_template_json` json DEFAULT NULL,
  `default_params_json` json DEFAULT NULL,
  `sort_order` int DEFAULT '0',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`scene_id`),
  UNIQUE KEY `scene_code` (`scene_code`),
  KEY `idx_smart_ppt_scene_sort` (`sort_order`,`scene_id`)
) ENGINE=InnoDB AUTO_INCREMENT=221 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_blueprint
CREATE TABLE `smart_report_blueprint` (
  `blueprint_id` int NOT NULL AUTO_INCREMENT,
  `blueprint_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_filename` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `inspection_json` json NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `output_file_path` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_generated_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`blueprint_id`),
  CONSTRAINT `smart_report_blueprint_chk_1` CHECK ((`status` in (_utf8mb4'draft',_utf8mb4'confirmed',_utf8mb4'archived')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_calc_metric
CREATE TABLE `smart_report_calc_metric` (
  `metric_code` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expression` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `components_json` json NOT NULL,
  `value_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '金额',
  `format_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'number',
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`metric_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_instance
CREATE TABLE `smart_report_instance` (
  `instance_id` int NOT NULL AUTO_INCREMENT,
  `template_id` int NOT NULL,
  `instance_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parameter_values_json` json NOT NULL,
  `text_values_json` json DEFAULT NULL,
  `data_snapshot_json` json DEFAULT NULL,
  `output_file_path` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `generation_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `last_generated_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_refresh_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`instance_id`),
  KEY `idx_smart_report_instance_template` (`template_id`),
  CONSTRAINT `smart_report_instance_ibfk_1` FOREIGN KEY (`template_id`) REFERENCES `smart_report_template` (`template_id`),
  CONSTRAINT `smart_report_instance_chk_1` CHECK ((`generation_status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'success',_utf8mb4'failed')))
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_job
CREATE TABLE `smart_report_job` (
  `job_id` int NOT NULL AUTO_INCREMENT,
  `instance_id` int DEFAULT NULL,
  `job_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `started_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `finished_at` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`job_id`),
  KEY `instance_id` (`instance_id`),
  CONSTRAINT `smart_report_job_ibfk_1` FOREIGN KEY (`instance_id`) REFERENCES `smart_report_instance` (`instance_id`) ON DELETE SET NULL,
  CONSTRAINT `smart_report_job_chk_1` CHECK ((`job_type` in (_utf8mb4'generate',_utf8mb4'refresh'))),
  CONSTRAINT `smart_report_job_chk_2` CHECK ((`job_status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'success',_utf8mb4'failed')))
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_template
CREATE TABLE `smart_report_template` (
  `template_id` int NOT NULL AUTO_INCREMENT,
  `template_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `template_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `template_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'analysis',
  `file_path` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `version_no` int NOT NULL DEFAULT '1',
  `remark` text COLLATE utf8mb4_unicode_ci,
  `created_by` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`template_id`),
  UNIQUE KEY `template_code` (`template_code`),
  CONSTRAINT `smart_report_template_chk_1` CHECK ((`template_type` in (_utf8mb4'analysis',_utf8mb4'report',_utf8mb4'summary',_utf8mb4'ppt'))),
  CONSTRAINT `smart_report_template_chk_2` CHECK ((`status` in (_utf8mb4'active',_utf8mb4'inactive',_utf8mb4'archived')))
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: smart_report_template_variable
CREATE TABLE `smart_report_template_variable` (
  `variable_id` int NOT NULL AUTO_INCREMENT,
  `template_id` int NOT NULL,
  `variable_key` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `variable_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `variable_type` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `binding_config_json` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_order` int NOT NULL DEFAULT '0',
  `created_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`variable_id`),
  UNIQUE KEY `template_id` (`template_id`,`variable_key`),
  KEY `idx_smart_report_variable_template` (`template_id`),
  CONSTRAINT `smart_report_template_variable_ibfk_1` FOREIGN KEY (`template_id`) REFERENCES `smart_report_template` (`template_id`) ON DELETE CASCADE,
  CONSTRAINT `smart_report_template_variable_chk_1` CHECK ((`variable_type` in (_utf8mb4'metric',_utf8mb4'formula',_utf8mb4'calc',_utf8mb4'parameter',_utf8mb4'text',_utf8mb4'table',_utf8mb4'chart',_utf8mb4'analysis')))
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: user_sessions
CREATE TABLE `user_sessions` (
  `session_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `must_change_password` tinyint(1) NOT NULL DEFAULT '0',
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expire_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_seen_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`session_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `user_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `user_sessions_chk_1` CHECK ((`must_change_password` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: users
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_login_password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `daily_login_password` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `permission_type` int NOT NULL,
  `first_login_flag` tinyint(1) NOT NULL DEFAULT '1',
  `create_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `update_time` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_name` (`user_name`),
  CONSTRAINT `users_chk_1` CHECK ((`permission_type` in (1,2,3))),
  CONSTRAINT `users_chk_2` CHECK ((`first_login_flag` in (0,1)))
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- table: version
CREATE TABLE `version` (
  `version_id` int NOT NULL AUTO_INCREMENT,
  `budget_year` int NOT NULL,
  `version_date_time` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_month` int NOT NULL DEFAULT '1',
  PRIMARY KEY (`version_id`),
  KEY `idx_version_year` (`budget_year`),
  CONSTRAINT `version_chk_1` CHECK ((`current_month` between 1 and 13))
) ENGINE=InnoDB AUTO_INCREMENT=2026000004 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

