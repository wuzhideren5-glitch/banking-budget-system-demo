"""Bootstrap schema for the business cost-income ratio module."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from app.db_bootstrap._ddl_normalize import normalize_ddl, find_missing_markers
from typing import Protocol

from app.db_bootstrap.bcir_enabled_state_0519 import bcir_indicator_enabled, bcir_item_enabled
from app.services.business_cost_income_derived import default_bcir_manual_entry_mode


class AsyncSqlConnection(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...

    async def executescript(self, sql_script: str) -> object: ...


BUSINESS_COST_INCOME_SCHEMA = """
CREATE TABLE IF NOT EXISTS business_cost_income_item (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL DEFAULT 2026,
  product_code VARCHAR(64) NOT NULL DEFAULT '',
  section VARCHAR(16) NOT NULL CHECK (section IN ('input', 'output')),
  name VARCHAR(255) NOT NULL,
  parent_id INT DEFAULT NULL,
  display_group TINYINT(1) NOT NULL DEFAULT 0 CHECK (display_group IN (0, 1)),
  data_acct_code VARCHAR(255) NOT NULL DEFAULT '',
  org_product_ref VARCHAR(255) NOT NULL DEFAULT '',
  org_product_entity_code VARCHAR(64) NOT NULL DEFAULT '',
  org_product_table_name VARCHAR(255) NOT NULL DEFAULT '',
  org_product_metric_code VARCHAR(255) NOT NULL DEFAULT '',
  org_product_metric_name VARCHAR(255) NOT NULL DEFAULT '',
  manual_entry_mode VARCHAR(32) NOT NULL DEFAULT 'disabled' CHECK (manual_entry_mode IN ('disabled', 'manual', 'manual_preferred')),
  value_mode VARCHAR(32) NOT NULL DEFAULT 'tree' CHECK (value_mode IN ('tree', 'self', 'self_and_tree')),
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  UNIQUE (budget_year, product_code, section, name),
  FOREIGN KEY (parent_id) REFERENCES business_cost_income_item(id)
);

CREATE INDEX idx_bci_item_section
ON business_cost_income_item(budget_year, product_code, section, sort_order, id);

CREATE TABLE IF NOT EXISTS business_cost_income_indicator (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL DEFAULT 2026,
  product_code VARCHAR(64) NOT NULL DEFAULT '',
  name VARCHAR(255) NOT NULL,
  parent_id INT DEFAULT NULL,
  display_group TINYINT(1) NOT NULL DEFAULT 0 CHECK (display_group IN (0, 1)),
  topic_metric_node_code VARCHAR(255) DEFAULT NULL,
  numerator_section VARCHAR(16) NOT NULL CHECK (numerator_section IN ('input', 'output')),
  numerator_item_id INT NOT NULL,
  numerator_value_mode VARCHAR(32) NOT NULL DEFAULT 'tree' CHECK (numerator_value_mode IN ('tree', 'self', 'self_and_tree')),
  denominator_section VARCHAR(16) NOT NULL CHECK (denominator_section IN ('input', 'output')),
  denominator_item_id INT NOT NULL,
  denominator_value_mode VARCHAR(32) NOT NULL DEFAULT 'tree' CHECK (denominator_value_mode IN ('tree', 'self', 'self_and_tree')),
  format VARCHAR(16) NOT NULL DEFAULT 'ratio' CHECK (format IN ('ratio', 'percent', 'number')),
  annualize TINYINT(1) NOT NULL DEFAULT 0 CHECK (annualize IN (0, 1)),
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  FOREIGN KEY (parent_id) REFERENCES business_cost_income_indicator(id),
  FOREIGN KEY (numerator_item_id) REFERENCES business_cost_income_item(id) ON DELETE CASCADE,
  FOREIGN KEY (denominator_item_id) REFERENCES business_cost_income_item(id) ON DELETE CASCADE
);

CREATE INDEX idx_bci_indicator_enabled
ON business_cost_income_indicator(product_code, enabled, sort_order, id);

CREATE TABLE IF NOT EXISTS business_cost_income_source_mapping (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL DEFAULT 2026,
  item_id INT NOT NULL,
  field VARCHAR(16) NOT NULL CHECK (field IN ('actual', 'budget')),
  data_acct_code VARCHAR(255) NOT NULL,
  agg_method VARCHAR(32) NOT NULL DEFAULT 'sum',
  filters_json VARCHAR(4096) NOT NULL DEFAULT '{}',
  enabled TINYINT(1) NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  UNIQUE (budget_year, item_id, field, data_acct_code),
  FOREIGN KEY (item_id) REFERENCES business_cost_income_item(id) ON DELETE CASCADE
);

CREATE INDEX idx_bci_source_mapping_item
ON business_cost_income_source_mapping(budget_year, item_id, field, enabled, id);

CREATE TABLE IF NOT EXISTS business_cost_income_value (
  id INT AUTO_INCREMENT PRIMARY KEY,
  budget_year INT NOT NULL DEFAULT 2026,
  year INT NOT NULL,
  month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
  entity_name VARCHAR(128) NOT NULL,
  group_name VARCHAR(128) NOT NULL DEFAULT '',
  product_code VARCHAR(64) NOT NULL DEFAULT '',
  item_section VARCHAR(16) NOT NULL CHECK (item_section IN ('input', 'output')),
  item_id INT NOT NULL,
  field VARCHAR(16) NOT NULL CHECK (field IN ('actual', 'budget', 'forecast')),
  value DOUBLE NOT NULL DEFAULT 0,
  update_time VARCHAR(64) NOT NULL,
  UNIQUE (
    budget_year, year, month,
    entity_name, group_name, product_code,
    item_section, item_id, field
  ),
  FOREIGN KEY (item_id) REFERENCES business_cost_income_item(id) ON DELETE CASCADE
);

CREATE INDEX idx_bci_value_lookup
ON business_cost_income_value(
  budget_year, year, entity_name, group_name, product_code, item_section, item_id, field, month
);
"""


BUSINESS_COST_INCOME_REQUIRED_COLUMNS = {
    "business_cost_income_item": {
        "id",
        "budget_year",
        "product_code",
        "section",
        "name",
        "parent_id",
        "display_group",
        "data_acct_code",
        "manual_entry_mode",
        "value_mode",
        "sort_order",
        "enabled",
    },
    "business_cost_income_indicator": {
        "id",
        "budget_year",
        "product_code",
        "name",
        "parent_id",
        "display_group",
        "topic_metric_node_code",
        "numerator_section",
        "numerator_item_id",
        "numerator_value_mode",
        "denominator_section",
        "denominator_item_id",
        "denominator_value_mode",
        "format",
        "annualize",
        "sort_order",
        "enabled",
    },
    "business_cost_income_source_mapping": {
        "id",
        "budget_year",
        "item_id",
        "field",
        "data_acct_code",
        "agg_method",
        "filters_json",
        "enabled",
    },
    "business_cost_income_value": {
        "id",
        "budget_year",
        "year",
        "month",
        "entity_name",
        "group_name",
        "product_code",
        "item_section",
        "item_id",
        "field",
        "value",
        "update_time",
    },
}


BCIR_YEAR_COLUMNS = {
    "business_cost_income_item": "budget_year INTEGER NOT NULL DEFAULT 2026",
    "business_cost_income_indicator": "budget_year INTEGER NOT NULL DEFAULT 2026",
    "business_cost_income_source_mapping": "budget_year INTEGER NOT NULL DEFAULT 2026",
    "business_cost_income_value": "budget_year INTEGER NOT NULL DEFAULT 2026",
}


BCIR_ITEM_ORG_PRODUCT_COLUMNS = {
    "org_product_ref": "TEXT NOT NULL DEFAULT ''",
    "org_product_entity_code": "TEXT NOT NULL DEFAULT ''",
    "org_product_table_name": "TEXT NOT NULL DEFAULT ''",
    "org_product_metric_code": "TEXT NOT NULL DEFAULT ''",
    "org_product_metric_name": "TEXT NOT NULL DEFAULT ''",
}


BUSINESS_COST_INCOME_REQUIRED_SQL_MARKERS = {
    "business_cost_income_item": (
        "product_code TEXT NOT NULL DEFAULT ''",
        "CHECK (section IN ('input', 'output'))",
        "parent_id INTEGER DEFAULT NULL REFERENCES business_cost_income_item(id)",
        "display_group INTEGER NOT NULL DEFAULT 0 CHECK (display_group IN (0, 1))",
        "data_acct_code TEXT NOT NULL DEFAULT ''",
        "manual_entry_mode TEXT NOT NULL DEFAULT 'disabled' CHECK (manual_entry_mode IN ('disabled', 'manual', 'manual_preferred'))",
        "value_mode TEXT NOT NULL DEFAULT 'tree' CHECK (value_mode IN ('tree', 'self', 'self_and_tree'))",
        "CHECK (enabled IN (0, 1))",
        "UNIQUE (budget_year, product_code, section, name)",
    ),
    "business_cost_income_indicator": (
        "product_code TEXT NOT NULL DEFAULT ''",
        "parent_id INTEGER DEFAULT NULL REFERENCES business_cost_income_indicator(id)",
        "display_group INTEGER NOT NULL DEFAULT 0 CHECK (display_group IN (0, 1))",
        "CHECK (numerator_section IN ('input', 'output'))",
        "numerator_value_mode TEXT NOT NULL DEFAULT 'tree' CHECK (numerator_value_mode IN ('tree', 'self', 'self_and_tree'))",
        "CHECK (denominator_section IN ('input', 'output'))",
        "denominator_value_mode TEXT NOT NULL DEFAULT 'tree' CHECK (denominator_value_mode IN ('tree', 'self', 'self_and_tree'))",
        "CHECK (format IN ('ratio', 'percent', 'number'))",
        "annualize INTEGER NOT NULL DEFAULT 0 CHECK (annualize IN (0, 1))",
    ),
    "business_cost_income_source_mapping": (
        "CHECK (field IN ('actual', 'budget'))",
        "UNIQUE (budget_year, item_id, field, data_acct_code)",
    ),
    "business_cost_income_value": (
        "CHECK (month BETWEEN 1 AND 12)",
        "CHECK (item_section IN ('input', 'output'))",
        "CHECK (field IN ('actual', 'budget', 'forecast'))",
    ),
}

BCIR_PRODUCT_CODES: tuple[str, ...] = (
    "A",
    "A01",
    "A02",
    "A03",
    "A04",
    "A05",
    "B",
    "B01",
    "B02",
    "C",
    "C01",
    "C02",
    "CORP",
    "D",
    "D01",
    "E",
    "E01",
    "F",
    "F01",
)

# Tuple: name, parent_name, local_metric_suffix (empty for group nodes), enabled.
DEFAULT_INPUT_ITEM_SPECS: tuple[tuple[str, str | None, str, bool], ...] = (
    ("业务支出", None, "", True),
    ("营销支出", "业务支出", "", True),
    ("营销费用", "营销支出", "05.01.01.02.001", True),
    ("积分", "营销支出", "04.03.02.01.016", True),
    ("销售人力费用", "营销支出", "", True),
    ("运营费用（不含存款保险费）", "业务支出", "", True),
    ("客户运营费用", "运营费用（不含存款保险费）", "", True),
    ("专项费用", "客户运营费用", "", True),
    ("其他客户运营", "客户运营费用", "", True),
    ("风险运营费用", "运营费用（不含存款保险费）", "", True),
    ("内催费用", "风险运营费用", "", True),
    ("其他风险运营", "风险运营费用", "", True),
    # Ledger bridge for reconciliation only; not under 业务支出 rollup.
    ("账套核对（运营不含存款保险）", None, "", False),
    ("运营费用", "账套核对（运营不含存款保险）", "05.01.01.02.002", False),
    ("存款保险费（减项）", "账套核对（运营不含存款保险）", "01.02.05.01.028", False),
)

# Backward-compatible alias for callers expecting (name, parent_name) pairs.
DEFAULT_INPUT_ITEMS = tuple((name, parent) for name, parent, _suffix, _enabled in DEFAULT_INPUT_ITEM_SPECS)

BCIR_AUM_OUTPUT_PRODUCT_CODES: frozenset[str] = frozenset({"A02", "A04"})
BCIR_MFAU_OUTPUT_PRODUCT_CODES: frozenset[str] = frozenset({"A04"})
BCIR_B_LINE_PRODUCT_CODES: frozenset[str] = frozenset({"B", "B01", "B02"})
BCIR_B_LINE_NEW_ISSUANCE_INPUT_PRODUCT_CODES: frozenset[str] = frozenset({"B", "B01"})
BCIR_A03_NEW_ISSUANCE_INPUT_PRODUCT_CODES: frozenset[str] = frozenset({"A03"})
BCIR_NEW_ISSUANCE_LUM_OUTPUT_PRODUCT_CODES: frozenset[str] = frozenset({"A03", "B", "B01"})
BCIR_NEW_ISSUANCE_LUM_BIAOFU_OUTPUT_PRODUCT_CODES: frozenset[str] = frozenset({"A03"})
BCIR_LEGACY_FLAT_INDICATOR_PRODUCT_CODES: frozenset[str] = frozenset({"CORP"})

# Extra input roots/leaves required by 0519 topic indicators on A-line templates.
TOPIC_INPUT_EXTENSION_SPECS: tuple[tuple[str, str | None, str, bool], ...] = (
    ("营销支出（客户维度）", None, "", True),
    ("新客营销支出", "营销支出（客户维度）", "05.02.09.01.001", True),
    ("存客营销支出", "营销支出（客户维度）", "05.02.09.01.002", True),
    ("新开通客户投入", "新客营销支出", "05.02.09.01.003", True),
)

A03_TOPIC_INPUT_SPECS: tuple[tuple[str, str | None, str, bool], ...] = (
    ("新发放投入", None, "05.02.09.01.004", True),
)

# Tuple: name, parent_name, local_metric_suffix (empty for group nodes), enabled.
B_LINE_INPUT_ITEM_SPECS: tuple[tuple[str, str | None, str, bool], ...] = (
    ("业务支出合计", None, "", True),
    ("营销支出", "业务支出合计", "", True),
    ("营销费用", "营销支出", "05.01.01.02.001", True),
    ("积分", "营销支出", "04.03.02.01.016", True),
    ("销售人力费用", "营销支出", "", True),
    ("运营费用（不含存款保险费）", "业务支出合计", "", True),
    ("客户运营费用", "运营费用（不含存款保险费）", "", True),
    ("专项运营", "客户运营费用", "", True),
    ("其他客户运营", "客户运营费用", "", True),
    ("风险运营费用", "运营费用（不含存款保险费）", "", True),
    ("内催费用", "风险运营费用", "", True),
    ("其他风险运营", "风险运营费用", "", True),
    ("营销支出（客户维度）", None, "", True),
    ("新客营销支出", "营销支出（客户维度）", "05.02.09.01.001", True),
    ("存客营销支出", "营销支出（客户维度）", "05.02.09.01.002", True),
    ("新开通客户投入", "新客营销支出", "05.02.09.01.003", True),
    ("新发放投入", None, "05.02.09.01.004", True),
)

B_LINE_INDICATOR_GROUPS: tuple[str, ...] = (
    "核心费率指标",
    "营销费率指标",
    "运营专项指标",
)

# Tuple: name, parent_group, numerator_name, denominator_name, format,
# numerator_value_mode, denominator_value_mode, product_codes (None = all B-line).
B_LINE_INDICATOR_LEAF_SPECS: tuple[
    tuple[str, str, str, str, str, str, str, frozenset[str] | None],
    ...,
] = (
    ("业务支出成本收入比", "核心费率指标", "业务支出合计", "营业收入（还原）", "percent", "tree", "tree", None),
    ("营销支出日均LUM费率", "营销费率指标", "营销支出", "日均LUM", "percent", "tree", "tree", None),
    ("运营费用日均LUM费率", "运营专项指标", "运营费用（不含存款保险费）", "日均LUM", "percent", "tree", "tree", None),
    ("营销支出收入费率", "核心费率指标", "营销支出", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新客营销日均LUM费率", "营销费率指标", "新客营销支出", "新客日均LUM", "percent", "tree", "tree", None),
    ("存客营销日均LUM费率", "营销费率指标", "存客营销支出", "存客日均LUM", "percent", "self", "tree", None),
    ("户均客户运营成本", "运营专项指标", "客户运营费用", "平均有效客户数", "percent", "tree", "tree", None),
    ("运营费用收入费率", "核心费率指标", "运营费用（不含存款保险费）", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新开通客户户均成本", "营销费率指标", "新开通客户投入", "新开通客户数", "percent", "tree", "tree", None),
    ("内催费率", "运营专项指标", "内催费用", "内催回收额", "percent", "tree", "tree", None),
    ("其他风险运营费率", "运营专项指标", "其他风险运营", "日均LUM", "percent", "tree", "tree", None),
    (
        "新发放LUM费率",
        "营销费率指标",
        "新发放投入",
        "新发放LUM",
        "percent",
        "tree",
        "tree",
        BCIR_B_LINE_NEW_ISSUANCE_INPUT_PRODUCT_CODES,
    ),
)

# 0519 topic indicators shared by A/C/D/E/F leaf products (LUM template).
LUM_TOPIC_INDICATOR_LEAF_SPECS: tuple[
    tuple[str, str, str, str, str, str, str, frozenset[str] | None],
    ...,
] = (
    ("业务支出成本收入比", "核心费率指标", "业务支出合计", "营业收入（还原）", "percent", "tree", "tree", None),
    ("营销支出日均LUM费率", "营销费率指标", "营销支出", "日均LUM", "percent", "tree", "tree", None),
    ("运营费用日均LUM费率", "运营专项指标", "运营费用（不含存款保险费）", "日均LUM", "percent", "tree", "tree", None),
    ("营销支出收入费率", "核心费率指标", "营销支出", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新客营销日均LUM费率", "营销费率指标", "新客营销支出", "新客日均LUM", "percent", "tree", "tree", None),
    ("存客营销日均LUM费率", "营销费率指标", "存客营销支出", "存客日均LUM", "percent", "self", "tree", None),
    ("户均客户运营成本", "运营专项指标", "客户运营费用", "平均有效客户数", "percent", "tree", "tree", None),
    ("运营费用收入费率", "核心费率指标", "运营费用（不含存款保险费）", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新开通客户户均成本", "营销费率指标", "新开通客户投入", "新开通客户数", "percent", "tree", "tree", None),
    ("内催费率", "运营专项指标", "内催费用", "内催回收额", "percent", "tree", "tree", None),
    ("其他风险运营费率", "运营专项指标", "其他风险运营", "日均LUM", "percent", "tree", "tree", None),
)

AUM_TOPIC_INDICATOR_LEAF_SPECS: tuple[
    tuple[str, str, str, str, str, str, str, frozenset[str] | None],
    ...,
] = (
    ("业务支出成本收入比", "核心费率指标", "业务支出合计", "营业收入（还原）", "percent", "tree", "tree", None),
    ("营销支出日均AuM费率", "营销费率指标", "营销支出", "日均AuM", "percent", "tree", "tree", None),
    ("运营费用日均AuM费率", "运营专项指标", "运营费用（不含存款保险费）", "日均AuM", "percent", "tree", "tree", None),
    ("营销支出收入费率", "核心费率指标", "营销支出", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新客营销AuM余额费率", "营销费率指标", "新客营销支出", "新客AuM余额", "percent", "tree", "tree", None),
    ("户均客户运营成本", "运营专项指标", "客户运营费用", "平均有效客户数", "percent", "tree", "tree", None),
    ("运营费用收入费率", "核心费率指标", "运营费用（不含存款保险费）", "营业收入（还原）", "percent", "tree", "tree", None),
    ("存客营销日均AuM费率", "营销费率指标", "存客营销支出", "存客日均AuM", "percent", "self", "tree", None),
    ("新开通客户户均成本", "营销费率指标", "新开通客户投入", "新开通客户数", "percent", "tree", "tree", None),
    ("内催费率", "运营专项指标", "内催费用", "内催回收额", "percent", "tree", "tree", None),
    ("其他风险运营费率", "运营专项指标", "其他风险运营", "日均LUM", "percent", "tree", "tree", None),
)

A04_TOPIC_INDICATOR_LEAF_SPECS: tuple[
    tuple[str, str, str, str, str, str, str, frozenset[str] | None],
    ...,
] = (
    ("业务支出成本收入比", "核心费率指标", "业务支出合计", "营业收入（还原）", "percent", "tree", "tree", None),
    ("营销支出日均AuM费率", "营销费率指标", "营销支出", "日均AuM", "percent", "tree", "tree", None),
    ("运营费用日均AuM费率", "运营专项指标", "运营费用（不含存款保险费）", "日均AuM", "percent", "tree", "tree", None),
    ("营销支出收入费率", "核心费率指标", "营销支出", "营业收入（还原）", "percent", "tree", "tree", None),
    ("新客营销AuM余额费率", "营销费率指标", "新客营销支出", "新客AuM余额", "percent", "tree", "tree", None),
    ("MFAU户均客户运营成本", "运营专项指标", "客户运营费用", "MFAU客户数", "percent", "tree", "tree", None),
    ("运营费用收入费率", "核心费率指标", "运营费用（不含存款保险费）", "营业收入（还原）", "percent", "tree", "tree", None),
    ("存客营销日均AuM费率", "营销费率指标", "存客营销支出", "存客日均AuM", "percent", "self", "tree", None),
    ("新开通客户户均成本", "营销费率指标", "新开通客户投入", "新开通客户数", "percent", "tree", "tree", None),
    ("内催费率", "运营专项指标", "内催费用", "内催回收额", "percent", "tree", "tree", None),
    ("其他风险运营费率", "运营专项指标", "其他风险运营", "日均LUM", "percent", "tree", "tree", None),
)

A03_TOPIC_EXTRA_INDICATOR_LEAF_SPECS: tuple[
    tuple[str, str, str, str, str, str, str, frozenset[str] | None],
    ...,
] = (
    ("标服3.0发放费率", "运营专项指标", "专项运营", "新发放LUM（标服）", "percent", "tree", "tree", None),
    ("新发放LUM费率", "营销费率指标", "新发放投入", "新发放LUM", "percent", "tree", "tree", None),
)

# Tuple: name, parent_name, local_metric_suffix, product_codes (None = all BCIR products).
DEFAULT_OUTPUT_ITEM_SPECS: tuple[tuple[str, str | None, str, frozenset[str] | None], ...] = (
    ("经营指标", None, "", None),
    ("营业收入", "经营指标", "03.09.05.01.039", None),
    ("内催回收额", "经营指标", "05.02.09.03.001", None),
    ("LUM规模", None, "", None),
    ("日均LUM", "LUM规模", "05.02.09.02.010", None),
    ("新客日均LUM", "LUM规模", "05.02.09.02.001", None),
    ("存客日均LUM", "LUM规模", "05.02.09.02.002", None),
    ("新发放LUM", "LUM规模", "05.02.09.02.005", BCIR_NEW_ISSUANCE_LUM_OUTPUT_PRODUCT_CODES),
    ("新发放LUM（标服）", "LUM规模", "05.02.09.02.006", BCIR_NEW_ISSUANCE_LUM_BIAOFU_OUTPUT_PRODUCT_CODES),
    ("AuM规模", None, "", BCIR_AUM_OUTPUT_PRODUCT_CODES),
    ("存客日均AuM", "AuM规模", "05.02.09.02.007", BCIR_AUM_OUTPUT_PRODUCT_CODES),
    ("新客AuM余额", "AuM规模", "05.02.09.02.008", BCIR_AUM_OUTPUT_PRODUCT_CODES),
    ("日均AuM", "AuM规模", "05.02.09.02.011", BCIR_AUM_OUTPUT_PRODUCT_CODES),
    ("客户数量", None, "", None),
    ("平均有效客户数", "客户数量", "05.02.09.02.004", None),
    ("新开通客户数", "客户数量", "05.02.09.02.003", None),
    ("MFAU客户数", "客户数量", "05.02.09.02.009", BCIR_MFAU_OUTPUT_PRODUCT_CODES),
)

# Backward-compatible alias: common output items shared by every product template.
DEFAULT_OUTPUT_ITEMS = tuple(
    (name, parent)
    for name, parent, _suffix, products in DEFAULT_OUTPUT_ITEM_SPECS
    if products is None
)

DEFAULT_INDICATORS = (
    ("成本收入比", "业务支出", "营业收入", "percent"),
    ("营销支出收入费率", "营销支出", "营业收入", "percent"),
    ("运营费用收入费率", "运营费用（不含存款保险费）", "营业收入", "percent"),
    ("风险运营回收率", "内催费用", "内催回收额", "percent"),
)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _missing_sql_markers(table_sql: str, markers: tuple[str, ...]) -> list[str]:
    """Check if all markers appear in the DDL text, using cross-database normalization."""
    return find_missing_markers(table_sql, markers)


def _table_columns_sync(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }


def _table_sql_sync(conn: sqlite3.Connection, table_name: str) -> str:
    """Return the DDL text for a table via SHOW CREATE TABLE or sqlite_master."""
    try:
        row = conn.execute(f"SHOW CREATE TABLE `{table_name}`").fetchone()
        return str(row[1] or "") if row else ""
    except Exception:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return str(row[0] or "") if row else ""


def _table_exists_sync(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


async def _table_columns(db: AsyncSqlConnection, table_name: str) -> set[str]:
    cur = await db.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    rows = await cur.fetchall()  # type: ignore[attr-defined]
    return {str(row[1]) for row in rows}


async def _table_sql(db: AsyncSqlConnection, table_name: str) -> str:
    """Return the DDL text for a table via SHOW CREATE TABLE or sqlite_master."""
    try:
        cur = await db.execute(f"SHOW CREATE TABLE `{table_name}`")
        row = await cur.fetchone()  # type: ignore[attr-defined]
        return str(row[1] or "") if row else ""
    except Exception:
        cur = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )
        row = await cur.fetchone()  # type: ignore[attr-defined]
        return str(row[0] or "") if row else ""


async def _table_exists(db: AsyncSqlConnection, table_name: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    row = await cur.fetchone()  # type: ignore[attr-defined]
    return row is not None


def ensure_business_cost_income_budget_year_columns_sync(
    conn: sqlite3.Connection,
    budget_year: int,
) -> None:
    """Ensure annual BCIR private tables carry the merged MySQL budget year."""
    for table_name, column_sql in BCIR_YEAR_COLUMNS.items():
        if not _table_exists_sync(conn, table_name):
            continue
        columns = _table_columns_sync(conn, table_name)
        if "budget_year" not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
        conn.execute(
            f"UPDATE {table_name} SET budget_year = ? WHERE budget_year IS NULL OR budget_year = 0",
            (int(budget_year),),
        )


async def ensure_business_cost_income_budget_year_columns(
    db: AsyncSqlConnection,
    budget_year: int,
) -> None:
    """Async variant for annual BCIR budget_year columns."""
    for table_name, column_sql in BCIR_YEAR_COLUMNS.items():
        if not await _table_exists(db, table_name):
            continue
        columns = await _table_columns(db, table_name)
        if "budget_year" not in columns:
            await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
        await db.execute(
            f"UPDATE {table_name} SET budget_year = ? WHERE budget_year IS NULL OR budget_year = 0",
            (int(budget_year),),
        )


def _needs_business_cost_income_rebuild_sync(conn: sqlite3.Connection) -> bool:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        if table_name == "business_cost_income_source_mapping" and not _table_exists_sync(conn, table_name):
            return True
        columns = _table_columns_sync(conn, table_name)
        if not columns:
            continue
        if required_columns - columns:
            return True
        if _missing_sql_markers(_table_sql_sync(conn, table_name), BUSINESS_COST_INCOME_REQUIRED_SQL_MARKERS.get(table_name, ())):
            return True
    return False


async def _needs_business_cost_income_rebuild(db: AsyncSqlConnection) -> bool:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        if table_name == "business_cost_income_source_mapping" and not await _table_exists(db, table_name):
            return True
        columns = await _table_columns(db, table_name)
        if not columns:
            continue
        if required_columns - columns:
            return True
        if _missing_sql_markers(await _table_sql(db, table_name), BUSINESS_COST_INCOME_REQUIRED_SQL_MARKERS.get(table_name, ())):
            return True
    return False


def _reject_existing_legacy_business_cost_income_tables_sync(conn: sqlite3.Connection) -> None:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        columns = _table_columns_sync(conn, table_name)
        if not columns:
            continue
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )


async def _reject_existing_legacy_business_cost_income_tables(db: AsyncSqlConnection) -> None:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        columns = await _table_columns(db, table_name)
        if not columns:
            continue
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )


def _select_legacy_bcir_item_rows_sync(conn: sqlite3.Connection) -> list[tuple]:
    columns = _table_columns_sync(conn, "business_cost_income_item")
    if not columns:
        return []
    select_parts = [
        "id",
        "product_code" if "product_code" in columns else "'' AS product_code",
        "section",
        "name",
        "parent_id",
        "display_group" if "display_group" in columns else "0 AS display_group",
        "data_acct_code" if "data_acct_code" in columns else "'' AS data_acct_code",
        "COALESCE(manual_entry_mode, 'disabled')" if "manual_entry_mode" in columns else "'disabled' AS manual_entry_mode",
        "value_mode" if "value_mode" in columns else "'tree' AS value_mode",
        "sort_order",
        "enabled",
    ]
    return conn.execute(
        f"""
        SELECT {", ".join(select_parts)}
        FROM business_cost_income_item
        ORDER BY id
        """
    ).fetchall()


async def _select_legacy_bcir_item_rows(db: AsyncSqlConnection) -> list[tuple]:
    columns = await _table_columns(db, "business_cost_income_item")
    if not columns:
        return []
    select_parts = [
        "id",
        "product_code" if "product_code" in columns else "'' AS product_code",
        "section",
        "name",
        "parent_id",
        "display_group" if "display_group" in columns else "0 AS display_group",
        "data_acct_code" if "data_acct_code" in columns else "'' AS data_acct_code",
        "COALESCE(manual_entry_mode, 'disabled')" if "manual_entry_mode" in columns else "'disabled' AS manual_entry_mode",
        "value_mode" if "value_mode" in columns else "'tree' AS value_mode",
        "sort_order",
        "enabled",
    ]
    cur = await db.execute(
        f"""
        SELECT {", ".join(select_parts)}
        FROM business_cost_income_item
        ORDER BY id
        """
    )
    return await cur.fetchall()  # type: ignore[attr-defined]


def _needs_product_template_reseed_sync(conn: sqlite3.Connection) -> bool:
    product_rows = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM business_cost_income_item
            WHERE TRIM(product_code) != ''
            """
        ).fetchone()[0]
        or 0
    )
    value_rows = int(conn.execute("SELECT COUNT(*) FROM business_cost_income_value").fetchone()[0] or 0)
    return product_rows == 0 and value_rows == 0


def _ensure_bcir_item_org_product_columns_sync(conn: sqlite3.Connection) -> None:
    if not _table_exists_sync(conn, "business_cost_income_item"):
        return
    columns = _table_columns_sync(conn, "business_cost_income_item")
    for column_name, column_sql in BCIR_ITEM_ORG_PRODUCT_COLUMNS.items():
        if column_name not in columns:
            conn.execute(f"ALTER TABLE business_cost_income_item ADD COLUMN {column_name} {column_sql}")


async def _ensure_bcir_item_org_product_columns(db: AsyncSqlConnection) -> None:
    if not await _table_exists(db, "business_cost_income_item"):
        return
    columns = await _table_columns(db, "business_cost_income_item")
    for column_name, column_sql in BCIR_ITEM_ORG_PRODUCT_COLUMNS.items():
        if column_name not in columns:
            await db.execute(f"ALTER TABLE business_cost_income_item ADD COLUMN {column_name} {column_sql}")


async def _needs_product_template_reseed(db: AsyncSqlConnection) -> bool:
    cur = await db.execute(
        """
        SELECT COUNT(*)
        FROM business_cost_income_item
        WHERE TRIM(product_code) != ''
        """
    )
    product_rows = int((await cur.fetchone())[0] or 0)  # type: ignore[attr-defined]
    cur = await db.execute("SELECT COUNT(*) FROM business_cost_income_value")
    value_rows = int((await cur.fetchone())[0] or 0)  # type: ignore[attr-defined]
    return product_rows == 0 and value_rows == 0


def _rebuild_business_cost_income_schema_sync(conn: sqlite3.Connection) -> None:
    item_rows = []
    indicator_rows = []
    value_rows = []
    if _table_exists_sync(conn, "business_cost_income_item"):
        item_rows = _select_legacy_bcir_item_rows_sync(conn)
    if _table_exists_sync(conn, "business_cost_income_indicator"):
        indicator_rows = conn.execute(
            """
            SELECT id, name, numerator_section, numerator_item_id,
                   denominator_section, denominator_item_id,
                   format, sort_order, enabled
            FROM business_cost_income_indicator
            ORDER BY id
            """
        ).fetchall()
    if _table_exists_sync(conn, "business_cost_income_value"):
        value_rows = conn.execute(
            """
            SELECT year, month, entity_name, group_name, product_code,
                   item_section, item_id, field, value, update_time
            FROM business_cost_income_value
            ORDER BY id
            """
        ).fetchall()

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        DROP TABLE IF EXISTS business_cost_income_source_mapping;
        DROP TABLE IF EXISTS business_cost_income_indicator;
        DROP TABLE IF EXISTS business_cost_income_value;
        DROP TABLE IF EXISTS business_cost_income_item;
        """
    )
    conn.executescript(BUSINESS_COST_INCOME_SCHEMA)
    for row in item_rows:
        conn.execute(
            """
            INSERT INTO business_cost_income_item(
              id, product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row[0]),
                str(row[1] or ""),
                str(row[2]),
                str(row[3]),
                row[4],
                int(row[5] or 0),
                str(row[6] or ""),
                str(row[7] or "disabled"),
                str(row[8] or "tree"),
                int(row[9] or 0),
                int(row[10] or 0),
            ),
        )
    for row in indicator_rows:
        conn.execute(
            """
            INSERT INTO business_cost_income_indicator(
              id, product_code, name, parent_id, display_group, topic_metric_node_code,
              numerator_section, numerator_item_id, numerator_value_mode,
              denominator_section, denominator_item_id, denominator_value_mode,
              format, annualize, sort_order, enabled
            ) VALUES (?, '', ?, NULL, 0, NULL, ?, ?, 'tree', ?, ?, 'tree', ?, 0, ?, ?)
            """,
            (
                int(row[0]),
                str(row[1]),
                str(row[2]),
                int(row[3]),
                str(row[4]),
                int(row[5]),
                str(row[6]),
                int(row[7] or 0),
                int(row[8] or 0),
            ),
        )
    for row in value_rows:
        conn.execute(
            """
            INSERT INTO business_cost_income_value(
              year, month, entity_name, group_name, product_code,
              item_section, item_id, field, value, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
    conn.execute("PRAGMA foreign_keys = ON")


async def _rebuild_business_cost_income_schema(db: AsyncSqlConnection) -> None:
    item_rows = []
    indicator_rows = []
    value_rows = []
    if await _table_exists(db, "business_cost_income_item"):
        item_rows = await _select_legacy_bcir_item_rows(db)
    if await _table_exists(db, "business_cost_income_indicator"):
        cur = await db.execute(
            """
            SELECT id, name, numerator_section, numerator_item_id,
                   denominator_section, denominator_item_id,
                   format, sort_order, enabled
            FROM business_cost_income_indicator
            ORDER BY id
            """
        )
        indicator_rows = await cur.fetchall()  # type: ignore[attr-defined]
    if await _table_exists(db, "business_cost_income_value"):
        cur = await db.execute(
            """
            SELECT year, month, entity_name, group_name, product_code,
                   item_section, item_id, field, value, update_time
            FROM business_cost_income_value
            ORDER BY id
            """
        )
        value_rows = await cur.fetchall()  # type: ignore[attr-defined]

    await db.execute("PRAGMA foreign_keys = OFF")
    await db.executescript(
        """
        DROP TABLE IF EXISTS business_cost_income_source_mapping;
        DROP TABLE IF EXISTS business_cost_income_indicator;
        DROP TABLE IF EXISTS business_cost_income_value;
        DROP TABLE IF EXISTS business_cost_income_item;
        """
    )
    await db.executescript(BUSINESS_COST_INCOME_SCHEMA)
    for row in item_rows:
        await db.execute(
            """
            INSERT INTO business_cost_income_item(
              id, product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row[0]),
                str(row[1] or ""),
                str(row[2]),
                str(row[3]),
                row[4],
                int(row[5] or 0),
                str(row[6] or ""),
                str(row[7] or "disabled"),
                str(row[8] or "tree"),
                int(row[9] or 0),
                int(row[10] or 0),
            ),
        )
    for row in indicator_rows:
        await db.execute(
            """
            INSERT INTO business_cost_income_indicator(
              id, product_code, name, parent_id, display_group, topic_metric_node_code,
              numerator_section, numerator_item_id, numerator_value_mode,
              denominator_section, denominator_item_id, denominator_value_mode,
              format, annualize, sort_order, enabled
            ) VALUES (?, '', ?, NULL, 0, NULL, ?, ?, 'tree', ?, ?, 'tree', ?, 0, ?, ?)
            """,
            (
                int(row[0]),
                str(row[1]),
                str(row[2]),
                int(row[3]),
                str(row[4]),
                int(row[5]),
                str(row[6]),
                int(row[7] or 0),
                int(row[8] or 0),
            ),
        )
    for row in value_rows:
        await db.execute(
            """
            INSERT INTO business_cost_income_value(
              year, month, entity_name, group_name, product_code,
              item_section, item_id, field, value, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
    await db.execute("PRAGMA foreign_keys = ON")


def _assert_current_business_cost_income_contract_sync(conn: sqlite3.Connection) -> None:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        columns = _table_columns_sync(conn, table_name)
        if not columns:
            raise RuntimeError(f"业务支出成本收入比表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        missing_markers = _missing_sql_markers(
            _table_sql_sync(conn, table_name),
            BUSINESS_COST_INCOME_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


def _resolve_product_data_acct_code(
    common_conn: sqlite3.Connection | None,
    *,
    product_code: str,
    local_metric_suffix: str,
) -> str:
    suffix = str(local_metric_suffix or "").strip().upper()
    if not suffix or common_conn is None:
        return ""
    data_acct_code = f"{product_code}.{suffix}"
    row = common_conn.execute(
        "SELECT data_acct_code FROM data_account WHERE data_acct_code = ?",
        (data_acct_code,),
    ).fetchone()
    return str(row[0]) if row else ""


def _insert_source_mappings_sync(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    data_acct_code: str,
) -> None:
    if not data_acct_code:
        return
    for field in ("actual", "budget"):
        conn.execute(
            """
            INSERT INTO business_cost_income_source_mapping(
              item_id, field, data_acct_code, agg_method, filters_json, enabled
            ) VALUES (?, ?, ?, 'sum', '{}', 1)
            """,
            (int(item_id), field, data_acct_code),
        )


def _input_item_display_group(name: str, specs: tuple[tuple[str, str | None, str, bool], ...]) -> int:
    parent_names = {parent for _name, parent, _suffix, _enabled in specs if parent}
    return 1 if name in parent_names else 0


def _output_item_display_group(name: str, specs: tuple[tuple[str, str | None, str, frozenset[str] | None], ...]) -> int:
    parent_names = {parent for _name, parent, _suffix, _products in specs if parent}
    return 1 if name in parent_names else 0


def _is_b_line_product(product_code: str) -> bool:
    return str(product_code or "").strip().upper() in BCIR_B_LINE_PRODUCT_CODES


def _indicator_template(product_code: str) -> str:
    normalized_product = str(product_code or "").strip().upper()
    if normalized_product in BCIR_LEGACY_FLAT_INDICATOR_PRODUCT_CODES:
        return "legacy"
    if normalized_product in BCIR_B_LINE_PRODUCT_CODES:
        return "b_line"
    if normalized_product == "A02":
        return "aum"
    if normalized_product == "A04":
        return "a04"
    if normalized_product == "A03":
        return "a03_lum"
    return "lum"


def _uses_grouped_topic_indicators(product_code: str) -> bool:
    return _indicator_template(product_code) != "legacy"


def _map_indicator_item_name(product_code: str, item_name: str) -> str:
    normalized_product = str(product_code or "").strip().upper()
    if normalized_product in BCIR_B_LINE_PRODUCT_CODES:
        return str(item_name or "").strip()
    mapping = {
        "业务支出合计": "业务支出",
        "营业收入（还原）": "营业收入",
        "专项运营": "专项费用",
    }
    return mapping.get(str(item_name or "").strip(), str(item_name or "").strip())


def _input_item_specs_for_product(product_code: str) -> tuple[tuple[str, str | None, str, bool], ...]:
    normalized_product = str(product_code or "").strip().upper()
    if normalized_product in BCIR_B_LINE_PRODUCT_CODES:
        specs: list[tuple[str, str | None, str, bool]] = []
        for name, parent, suffix, enabled in B_LINE_INPUT_ITEM_SPECS:
            if name == "新发放投入" and normalized_product not in BCIR_B_LINE_NEW_ISSUANCE_INPUT_PRODUCT_CODES:
                continue
            specs.append((name, parent, suffix, enabled))
        return tuple(specs)

    specs = list(DEFAULT_INPUT_ITEM_SPECS)
    if _uses_grouped_topic_indicators(normalized_product):
        specs.extend(TOPIC_INPUT_EXTENSION_SPECS)
    if normalized_product in BCIR_A03_NEW_ISSUANCE_INPUT_PRODUCT_CODES:
        specs.extend(A03_TOPIC_INPUT_SPECS)
    return tuple(specs)


def _output_item_specs_for_product(product_code: str) -> list[tuple[str, str | None, str, frozenset[str] | None]]:
    normalized_product = str(product_code or "").strip().upper()
    specs: list[tuple[str, str | None, str, frozenset[str] | None]] = []
    for spec in DEFAULT_OUTPUT_ITEM_SPECS:
        name, parent, suffix, products = spec
        if products is not None and normalized_product not in products:
            continue
        if normalized_product in BCIR_B_LINE_PRODUCT_CODES and name == "营业收入":
            name = "营业收入（还原）"
        specs.append((name, parent, suffix, products))
    return specs


def _indicator_leaf_specs_for_product(
    product_code: str,
) -> list[tuple[str, str, str, str, str, str, str, frozenset[str] | None]]:
    normalized_product = str(product_code or "").strip().upper()
    template = _indicator_template(normalized_product)
    if template == "legacy":
        return [
            (name, "", numerator_name, denominator_name, fmt, "tree", "tree", None)
            for name, numerator_name, denominator_name, fmt in DEFAULT_INDICATORS
        ]

    if template == "b_line":
        base_specs = B_LINE_INDICATOR_LEAF_SPECS
    elif template == "aum":
        base_specs = AUM_TOPIC_INDICATOR_LEAF_SPECS
    elif template == "a04":
        base_specs = A04_TOPIC_INDICATOR_LEAF_SPECS
    elif template == "a03_lum":
        base_specs = (*LUM_TOPIC_INDICATOR_LEAF_SPECS, *A03_TOPIC_EXTRA_INDICATOR_LEAF_SPECS)
    else:
        base_specs = LUM_TOPIC_INDICATOR_LEAF_SPECS

    leaves: list[tuple[str, str, str, str, str, str, str, frozenset[str] | None]] = []
    for spec in base_specs:
        _name, _group, _num, _den, _fmt, _num_mode, _den_mode, products = spec
        if products is not None and normalized_product not in products:
            continue
        leaves.append(spec)
    return leaves


def _seed_product_indicators_sync(
    conn: sqlite3.Connection,
    *,
    product_code: str,
    item_ids: dict[tuple[str, str], int],
) -> None:
    normalized_product = str(product_code or "").strip().upper()
    group_ids: dict[str, int] = {}
    sort_order = 0
    grouped = _uses_grouped_topic_indicators(normalized_product)

    if grouped:
        placeholder_num_id = item_ids.get(
            ("input", _map_indicator_item_name(normalized_product, "业务支出合计"))
        )
        placeholder_den_id = item_ids.get(
            ("output", _map_indicator_item_name(normalized_product, "营业收入（还原）"))
        )
        if placeholder_num_id is None or placeholder_den_id is None:
            return
        for group_name in B_LINE_INDICATOR_GROUPS:
            cur = conn.execute(
                """
                INSERT INTO business_cost_income_indicator(
                  product_code, name, parent_id, display_group, topic_metric_node_code,
                  numerator_section, numerator_item_id, numerator_value_mode,
                  denominator_section, denominator_item_id, denominator_value_mode,
                  format, annualize, sort_order, enabled
                ) VALUES (?, ?, NULL, 1, NULL, 'input', ?, 'tree', 'output', ?, 'tree', 'ratio', 0, ?, ?)
                """,
                (
                    normalized_product,
                    group_name,
                    placeholder_num_id,
                    placeholder_den_id,
                    sort_order,
                    1 if bcir_indicator_enabled(normalized_product, group_name) else 0,
                ),
            )
            group_ids[group_name] = int(cur.lastrowid)
            sort_order += 1

    for leaf_spec in _indicator_leaf_specs_for_product(normalized_product):
        name, parent_group, numerator_name, denominator_name, fmt, num_mode, den_mode, _products = leaf_spec
        mapped_numerator = _map_indicator_item_name(normalized_product, numerator_name)
        mapped_denominator = _map_indicator_item_name(normalized_product, denominator_name)
        numerator_id = item_ids.get(("input", mapped_numerator))
        denominator_id = item_ids.get(("output", mapped_denominator))
        if numerator_id is None or denominator_id is None:
            continue
        if grouped:
            parent_id = group_ids.get(parent_group)
            if parent_id is None:
                continue
            conn.execute(
                """
                INSERT INTO business_cost_income_indicator(
                  product_code, name, parent_id, display_group, topic_metric_node_code,
                  numerator_section, numerator_item_id, numerator_value_mode,
                  denominator_section, denominator_item_id, denominator_value_mode,
                  format, annualize, sort_order, enabled
                ) VALUES (?, ?, ?, 0, NULL, 'input', ?, ?, 'output', ?, ?, ?, 0, ?, ?)
                """,
                (
                    normalized_product,
                    name,
                    parent_id,
                    numerator_id,
                    num_mode,
                    denominator_id,
                    den_mode,
                    fmt,
                    sort_order,
                    1 if bcir_indicator_enabled(normalized_product, name) else 0,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO business_cost_income_indicator(
                  product_code, name, parent_id, display_group, topic_metric_node_code,
                  numerator_section, numerator_item_id, numerator_value_mode,
                  denominator_section, denominator_item_id, denominator_value_mode,
                  format, annualize, sort_order, enabled
                ) VALUES (?, ?, NULL, 0, NULL, 'input', ?, 'tree', 'output', ?, 'tree', ?, 0, ?, ?)
                """,
                (
                    normalized_product,
                    name,
                    numerator_id,
                    denominator_id,
                    fmt,
                    sort_order,
                    1 if bcir_indicator_enabled(normalized_product, name) else 0,
                ),
            )
        sort_order += 1


def _seed_product_business_cost_income_config_sync(
    conn: sqlite3.Connection,
    common_conn: sqlite3.Connection | None,
    *,
    product_code: str,
) -> dict[str, int]:
    normalized_product = str(product_code or "").strip().upper()
    item_ids: dict[tuple[str, str], int] = {}
    input_specs = _input_item_specs_for_product(normalized_product)

    for sort_order, (name, parent_name, local_suffix, enabled) in enumerate(input_specs):
        parent_id = item_ids.get(("input", parent_name)) if parent_name else None
        display_group = _input_item_display_group(name, input_specs)
        data_acct_code = _resolve_product_data_acct_code(
            common_conn,
            product_code=normalized_product,
            local_metric_suffix=local_suffix,
        )
        manual_entry_mode = default_bcir_manual_entry_mode(
            "input",
            name,
            has_children=bool(display_group),
        )
        cur = conn.execute(
            """
            INSERT INTO business_cost_income_item(
              product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
            ) VALUES (?, 'input', ?, ?, ?, ?, ?, 'tree', ?, ?)
            """,
            (
                normalized_product,
                name,
                parent_id,
                display_group,
                data_acct_code,
                manual_entry_mode,
                sort_order,
                1 if bcir_item_enabled(normalized_product, "input", name, default=enabled) else 0,
            ),
        )
        item_id = int(cur.lastrowid)
        item_ids[("input", name)] = item_id
        _insert_source_mappings_sync(conn, item_id=item_id, data_acct_code=data_acct_code)

    for sort_order, (name, parent_name, local_suffix, _products) in enumerate(
        _output_item_specs_for_product(normalized_product)
    ):
        parent_id = item_ids.get(("output", parent_name)) if parent_name else None
        display_group = _output_item_display_group(name, _output_item_specs_for_product(normalized_product))
        data_acct_code = _resolve_product_data_acct_code(
            common_conn,
            product_code=normalized_product,
            local_metric_suffix=local_suffix,
        )
        manual_entry_mode = default_bcir_manual_entry_mode(
            "output",
            name,
            has_children=bool(display_group),
        )
        cur = conn.execute(
            """
            INSERT INTO business_cost_income_item(
              product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
            ) VALUES (?, 'output', ?, ?, ?, ?, ?, 'tree', ?, ?)
            """,
            (
                normalized_product,
                name,
                parent_id,
                display_group,
                data_acct_code,
                manual_entry_mode,
                sort_order,
                1 if bcir_item_enabled(normalized_product, "output", name) else 0,
            ),
        )
        item_id = int(cur.lastrowid)
        item_ids[("output", name)] = item_id
        _insert_source_mappings_sync(conn, item_id=item_id, data_acct_code=data_acct_code)

    _seed_product_indicators_sync(conn, product_code=normalized_product, item_ids=item_ids)

    return item_ids


def _merge_bcir_item_id(conn: sqlite3.Connection, *, from_id: int, to_id: int) -> None:
    if from_id == to_id:
        return
    conn.execute(
        """
        DELETE FROM business_cost_income_value
        WHERE item_id = ? AND id IN (
          SELECT id FROM (
            SELECT drop_row.id
            FROM business_cost_income_value drop_row
            JOIN business_cost_income_value keep
              ON keep.item_id = ?
             AND keep.budget_year = drop_row.budget_year
             AND keep.year = drop_row.year
             AND keep.month = drop_row.month
             AND keep.entity_name = drop_row.entity_name
             AND keep.group_name = drop_row.group_name
             AND keep.product_code = drop_row.product_code
             AND keep.item_section = drop_row.item_section
             AND keep.field = drop_row.field
            WHERE drop_row.item_id = ?
          ) duplicate_rows
        )
        """,
        (from_id, to_id, from_id),
    )
    conn.execute(
        "UPDATE business_cost_income_value SET item_id = ? WHERE item_id = ?",
        (to_id, from_id),
    )
    conn.execute(
        "UPDATE business_cost_income_indicator SET numerator_item_id = ? WHERE numerator_item_id = ?",
        (to_id, from_id),
    )
    conn.execute(
        "UPDATE business_cost_income_indicator SET denominator_item_id = ? WHERE denominator_item_id = ?",
        (to_id, from_id),
    )
    conn.execute(
        "UPDATE business_cost_income_item SET parent_id = ? WHERE parent_id = ?",
        (to_id, from_id),
    )
    conn.execute(
        "DELETE FROM business_cost_income_source_mapping WHERE item_id = ?",
        (from_id,),
    )


def _bcir_item_canonical_rank(row: sqlite3.Row) -> tuple:
    item_id = int(row["id"])
    product_code = str(row["product_code"] or "")
    data_acct_code = str(row["data_acct_code"] or "")
    enabled = int(row["enabled"] or 0)
    normalized_product = product_code.strip().upper()
    return (
        0 if product_code.strip() == normalized_product else 1,
        0 if data_acct_code.strip() else 1,
        0 if enabled else 1,
        item_id,
    )


def _bcir_item_canonical_rank_tuple(row: tuple) -> tuple:
    item_id = int(row[0])
    product_code = str(row[1] or "")
    data_acct_code = str(row[4] or "")
    enabled = int(row[5] or 0)
    normalized_product = product_code.strip().upper()
    return (
        0 if product_code.strip() == normalized_product else 1,
        0 if data_acct_code.strip() else 1,
        0 if enabled else 1,
        item_id,
    )


def _normalize_legacy_bcir_item_names_sync(conn: sqlite3.Connection) -> int:
    """Rename legacy BCIR item aliases in-place before duplicate merging."""
    renamed = 0
    for product_code in BCIR_B_LINE_PRODUCT_CODES:
        rows = conn.execute(
            """
            SELECT id, budget_year
            FROM business_cost_income_item
            WHERE product_code = ? AND section = 'input' AND name = '营销积分支出'
            """,
            (product_code,),
        ).fetchall()
        for row in rows:
            budget_year = int(row[1] or 0)
            duplicate = conn.execute(
                """
                SELECT id
                FROM business_cost_income_item
                WHERE budget_year = ? AND product_code = ? AND section = 'input' AND name = '积分'
                LIMIT 1
                """,
                (budget_year, product_code),
            ).fetchone()
            old_id = int(row[0])
            if duplicate is not None:
                _merge_bcir_item_id(conn, from_id=old_id, to_id=int(duplicate[0]))
                conn.execute("DELETE FROM business_cost_income_item WHERE id = ?", (old_id,))
            else:
                conn.execute(
                    """
                    UPDATE business_cost_income_item
                    SET name = '积分'
                    WHERE id = ?
                    """,
                    (old_id,),
                )
            renamed += 1
    return renamed


async def _normalize_legacy_bcir_item_names(db: AsyncSqlConnection) -> int:
    renamed = 0
    for product_code in BCIR_B_LINE_PRODUCT_CODES:
        cur = await db.execute(
            """
            SELECT id, budget_year
            FROM business_cost_income_item
            WHERE product_code = ? AND section = 'input' AND name = '营销积分支出'
            """,
            (product_code,),
        )
        rows = await cur.fetchall()  # type: ignore[attr-defined]
        for row in rows:
            budget_year = int(row[1] or 0)
            cur = await db.execute(
                """
                SELECT id
                FROM business_cost_income_item
                WHERE budget_year = ? AND product_code = ? AND section = 'input' AND name = '积分'
                LIMIT 1
                """,
                (budget_year, product_code),
            )
            duplicate = await cur.fetchone()  # type: ignore[attr-defined]
            old_id = int(row[0])
            if duplicate is not None:
                await _merge_bcir_item_id_async(db, from_id=old_id, to_id=int(duplicate[0]))
                await db.execute("DELETE FROM business_cost_income_item WHERE id = ?", (old_id,))
            else:
                await db.execute(
                    """
                    UPDATE business_cost_income_item
                    SET name = '积分'
                    WHERE id = ?
                    """,
                    (old_id,),
                )
            renamed += 1
    return renamed


async def _merge_bcir_item_id_async(db: AsyncSqlConnection, *, from_id: int, to_id: int) -> None:
    if from_id == to_id:
        return
    await db.execute(
        """
        DELETE FROM business_cost_income_value
        WHERE item_id = ? AND id IN (
          SELECT id FROM (
            SELECT drop_row.id
            FROM business_cost_income_value drop_row
            JOIN business_cost_income_value keep
              ON keep.item_id = ?
             AND keep.budget_year = drop_row.budget_year
             AND keep.year = drop_row.year
             AND keep.month = drop_row.month
             AND keep.entity_name = drop_row.entity_name
             AND keep.group_name = drop_row.group_name
             AND keep.product_code = drop_row.product_code
             AND keep.item_section = drop_row.item_section
             AND keep.field = drop_row.field
            WHERE drop_row.item_id = ?
          ) duplicate_rows
        )
        """,
        (from_id, to_id, from_id),
    )
    await db.execute("UPDATE business_cost_income_value SET item_id = ? WHERE item_id = ?", (to_id, from_id))
    await db.execute(
        "UPDATE business_cost_income_indicator SET numerator_item_id = ? WHERE numerator_item_id = ?",
        (to_id, from_id),
    )
    await db.execute(
        "UPDATE business_cost_income_indicator SET denominator_item_id = ? WHERE denominator_item_id = ?",
        (to_id, from_id),
    )
    await db.execute("UPDATE business_cost_income_item SET parent_id = ? WHERE parent_id = ?", (to_id, from_id))
    await db.execute("DELETE FROM business_cost_income_source_mapping WHERE item_id = ?", (from_id,))

async def repair_bcir_item_identity(db: AsyncSqlConnection) -> dict[str, int]:
    """Async variant of BCIR item identity repair that reuses the active DB connection."""
    stats = {"trimmed_names": 0, "normalized_products": 0, "merged_duplicates": 0, "renamed_legacy_items": 0}
    cur = await db.execute(
        """
        UPDATE business_cost_income_item
        SET name = TRIM(name)
        WHERE name != TRIM(name)
        """
    )
    stats["trimmed_names"] = int(getattr(cur, "rowcount", 0) or 0)
    stats["renamed_legacy_items"] = await _normalize_legacy_bcir_item_names(db)

    cur = await db.execute(
        """
        SELECT id, product_code, section, name, data_acct_code, enabled, budget_year
        FROM business_cost_income_item
        ORDER BY id
        """
    )
    rows = await cur.fetchall()  # type: ignore[attr-defined]
    grouped: dict[tuple[int, str, str, str], list[tuple]] = {}
    for row in rows:
        key = (
            int(row[6] or 0),
            str(row[1] or "").strip().upper(),
            str(row[2]),
            str(row[3] or "").strip(),
        )
        grouped.setdefault(key, []).append(tuple(row))

    for group in grouped.values():
        if len(group) <= 1:
            continue
        ordered = sorted(group, key=_bcir_item_canonical_rank_tuple)
        canonical_id = int(ordered[0][0])
        for duplicate in ordered[1:]:
            duplicate_id = int(duplicate[0])
            await _merge_bcir_item_id_async(db, from_id=duplicate_id, to_id=canonical_id)
            await db.execute("DELETE FROM business_cost_income_item WHERE id = ?", (duplicate_id,))
            stats["merged_duplicates"] += 1

    cur = await db.execute(
        """
        UPDATE business_cost_income_item
        SET product_code = UPPER(TRIM(product_code))
        WHERE product_code != UPPER(TRIM(product_code))
        """
    )
    normalized_items = int(getattr(cur, "rowcount", 0) or 0)
    cur = await db.execute(
        """
        UPDATE business_cost_income_indicator
        SET product_code = UPPER(TRIM(product_code))
        WHERE product_code != UPPER(TRIM(product_code))
        """
    )
    normalized_indicators = int(getattr(cur, "rowcount", 0) or 0)
    stats["normalized_products"] = normalized_items + normalized_indicators
    return stats


def repair_bcir_item_identity_sync(conn: sqlite3.Connection) -> dict[str, int]:
    """Normalize product/name keys and merge duplicate BCIR items for the same product."""
    stats = {"trimmed_names": 0, "normalized_products": 0, "merged_duplicates": 0, "renamed_legacy_items": 0}
    row_factory = getattr(conn, "row_factory", None)
    if hasattr(conn, "row_factory"):
        conn.row_factory = sqlite3.Row
    trimmed = conn.execute(
        """
        UPDATE business_cost_income_item
        SET name = TRIM(name)
        WHERE name != TRIM(name)
        """
    ).rowcount
    stats["trimmed_names"] = int(trimmed or 0)
    stats["renamed_legacy_items"] = _normalize_legacy_bcir_item_names_sync(conn)

    cur = conn.execute(
        """
        SELECT id, product_code, section, name, data_acct_code, enabled, budget_year
        FROM business_cost_income_item
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    if rows and not isinstance(rows[0], sqlite3.Row):
        columns = [str(desc[0]) for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in rows]
    grouped: dict[tuple[int, str, str, str], list] = {}
    for row in rows:
        try:
            row_budget_year = int(row["budget_year"] or 0)
        except (KeyError, TypeError, IndexError):
            row_budget_year = int(row[6] or 0)
        key = (
            row_budget_year,
            str(row["product_code"] or "").strip().upper(),
            str(row["section"]),
            str(row["name"] or "").strip(),
        )
        grouped.setdefault(key, []).append(row)

    for group in grouped.values():
        if len(group) <= 1:
            continue
        ordered = sorted(group, key=_bcir_item_canonical_rank)
        canonical_id = int(ordered[0]["id"])
        for duplicate in ordered[1:]:
            duplicate_id = int(duplicate["id"])
            _merge_bcir_item_id(conn, from_id=duplicate_id, to_id=canonical_id)
            conn.execute("DELETE FROM business_cost_income_item WHERE id = ?", (duplicate_id,))
            stats["merged_duplicates"] += 1

    normalized_items = conn.execute(
        """
        UPDATE business_cost_income_item
        SET product_code = UPPER(TRIM(product_code))
        WHERE product_code != UPPER(TRIM(product_code))
        """
    ).rowcount
    normalized_indicators = conn.execute(
        """
        UPDATE business_cost_income_indicator
        SET product_code = UPPER(TRIM(product_code))
        WHERE product_code != UPPER(TRIM(product_code))
        """
    ).rowcount
    stats["normalized_products"] = int((normalized_items or 0) + (normalized_indicators or 0))
    if hasattr(conn, "row_factory"):
        conn.row_factory = row_factory
    return stats


def reseed_default_business_cost_income_config_sync(
    conn: sqlite3.Connection,
    common_conn: sqlite3.Connection | None = None,
    *,
    product_codes: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Replace BCIR default trees with the current 业务支出 input structure."""
    conn.execute("DELETE FROM business_cost_income_source_mapping")
    conn.execute("DELETE FROM business_cost_income_value")
    conn.execute("DELETE FROM business_cost_income_indicator")
    conn.execute("DELETE FROM business_cost_income_item")

    stats = {"products": 0, "input_items": 0, "output_items": 0, "indicators": 0}
    for product_code in product_codes or BCIR_PRODUCT_CODES:
        _seed_product_business_cost_income_config_sync(conn, common_conn, product_code=product_code)
        stats["products"] += 1

    stats["input_items"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM business_cost_income_item WHERE section = 'input'"
        ).fetchone()[0]
        or 0
    )
    stats["output_items"] = int(
        conn.execute(
            "SELECT COUNT(*) FROM business_cost_income_item WHERE section = 'output'"
        ).fetchone()[0]
        or 0
    )
    stats["indicators"] = int(
        conn.execute("SELECT COUNT(*) FROM business_cost_income_indicator").fetchone()[0] or 0
    )
    return stats


def _seed_default_business_cost_income_config_sync(
    conn: sqlite3.Connection,
    common_conn: sqlite3.Connection | None = None,
) -> None:
    existing_count = int(
        conn.execute("SELECT COUNT(*) FROM business_cost_income_item").fetchone()[0] or 0
    )
    if existing_count:
        return
    reseed_default_business_cost_income_config_sync(conn, common_conn)


async def _assert_current_business_cost_income_contract(db: AsyncSqlConnection) -> None:
    for table_name, required_columns in BUSINESS_COST_INCOME_REQUIRED_COLUMNS.items():
        columns = await _table_columns(db, table_name)
        if not columns:
            raise RuntimeError(f"业务支出成本收入比表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )
        missing_markers = _missing_sql_markers(
            await _table_sql(db, table_name),
            BUSINESS_COST_INCOME_REQUIRED_SQL_MARKERS.get(table_name, ()),
        )
        if missing_markers:
            raise RuntimeError(
                f"业务支出成本收入比表 {table_name} 缺少当前约束，系统不再自动迁移："
                + ", ".join(missing_markers)
            )


def ensure_business_cost_income_schema(conn: sqlite3.Connection, budget_year: int = 2026) -> None:
    """Ensure business cost-income private tables exist in an annual budget DB."""
    ensure_business_cost_income_budget_year_columns_sync(conn, budget_year)
    _reject_existing_legacy_business_cost_income_tables_sync(conn)
    if _needs_business_cost_income_rebuild_sync(conn):
        _rebuild_business_cost_income_schema_sync(conn)
    else:
        conn.executescript(BUSINESS_COST_INCOME_SCHEMA)
    ensure_business_cost_income_budget_year_columns_sync(conn, budget_year)
    _ensure_bcir_item_org_product_columns_sync(conn)
    _assert_current_business_cost_income_contract_sync(conn)
    if _needs_product_template_reseed_sync(conn):
        reseed_default_business_cost_income_config_sync(conn)
    else:
        _seed_default_business_cost_income_config_sync(conn)
    repair_bcir_item_identity_sync(conn)


def ensure_business_cost_income_schema_with_common(
    conn: sqlite3.Connection,
    common_conn: sqlite3.Connection | None,
    budget_year: int = 2026,
) -> None:
    """Sync variant that resolves product-prefixed data account bindings."""
    ensure_business_cost_income_budget_year_columns_sync(conn, budget_year)
    _reject_existing_legacy_business_cost_income_tables_sync(conn)
    if _needs_business_cost_income_rebuild_sync(conn):
        _rebuild_business_cost_income_schema_sync(conn)
    else:
        conn.executescript(BUSINESS_COST_INCOME_SCHEMA)
    ensure_business_cost_income_budget_year_columns_sync(conn, budget_year)
    _ensure_bcir_item_org_product_columns_sync(conn)
    _assert_current_business_cost_income_contract_sync(conn)
    if _needs_product_template_reseed_sync(conn):
        reseed_default_business_cost_income_config_sync(conn, common_conn)
    else:
        _seed_default_business_cost_income_config_sync(conn, common_conn)
    repair_bcir_item_identity_sync(conn)


async def ensure_business_cost_income_schema_async(db: AsyncSqlConnection, budget_year: int = 2026) -> None:
    """Async adapter for FastAPI routes that lazily touch annual budget DBs."""
    await ensure_business_cost_income_budget_year_columns(db, budget_year)
    await _reject_existing_legacy_business_cost_income_tables(db)
    if await _needs_business_cost_income_rebuild(db):
        await _rebuild_business_cost_income_schema(db)
    else:
        await db.executescript(BUSINESS_COST_INCOME_SCHEMA)
    await ensure_business_cost_income_budget_year_columns(db, budget_year)
    await _ensure_bcir_item_org_product_columns(db)
    await _assert_current_business_cost_income_contract(db)
    if await _needs_product_template_reseed(db):
        await db.execute("DELETE FROM business_cost_income_source_mapping")
        await db.execute("DELETE FROM business_cost_income_value")
        await db.execute("DELETE FROM business_cost_income_indicator")
        await db.execute("DELETE FROM business_cost_income_item")
    cur = await db.execute("SELECT COUNT(*) FROM business_cost_income_item")
    existing_count = int((await cur.fetchone())[0] or 0)  # type: ignore[attr-defined]
    if existing_count == 0:
        await db.execute("PRAGMA foreign_keys = ON")
        for product_code in BCIR_PRODUCT_CODES:
            item_ids: dict[tuple[str, str], int] = {}
            input_specs = _input_item_specs_for_product(product_code)
            for sort_order, (name, parent_name, local_suffix, enabled) in enumerate(input_specs):
                parent_id = item_ids.get(("input", parent_name)) if parent_name else None
                display_group = _input_item_display_group(name, input_specs)
                data_acct_code = f"{product_code}.{local_suffix}" if local_suffix else ""
                manual_entry_mode = default_bcir_manual_entry_mode(
                    "input",
                    name,
                    has_children=bool(display_group),
                )
                cur = await db.execute(
                    """
                    INSERT INTO business_cost_income_item(
                      product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
                    ) VALUES (?, 'input', ?, ?, ?, ?, ?, 'tree', ?, ?)
                    """,
                    (
                        product_code,
                        name,
                        parent_id,
                        display_group,
                        data_acct_code,
                        manual_entry_mode,
                        sort_order,
                        1 if bcir_item_enabled(product_code, "input", name, default=enabled) else 0,
                    ),
                )
                item_ids[("input", name)] = int(cur.lastrowid)  # type: ignore[attr-defined]
            output_specs = _output_item_specs_for_product(product_code)
            for sort_order, (name, parent_name, local_suffix, _products) in enumerate(output_specs):
                parent_id = item_ids.get(("output", parent_name)) if parent_name else None
                display_group = _output_item_display_group(name, output_specs)
                data_acct_code = f"{product_code}.{local_suffix}" if local_suffix else ""
                manual_entry_mode = default_bcir_manual_entry_mode(
                    "output",
                    name,
                    has_children=bool(display_group),
                )
                cur = await db.execute(
                    """
                    INSERT INTO business_cost_income_item(
                      product_code, section, name, parent_id, display_group, data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
                    ) VALUES (?, 'output', ?, ?, ?, ?, ?, 'tree', ?, ?)
                    """,
                    (
                        product_code,
                        name,
                        parent_id,
                        display_group,
                        data_acct_code,
                        manual_entry_mode,
                        sort_order,
                        1 if bcir_item_enabled(product_code, "output", name) else 0,
                    ),
                )
                item_ids[("output", name)] = int(cur.lastrowid)  # type: ignore[attr-defined]
            group_ids: dict[str, int] = {}
            indicator_sort = 0
            grouped = _uses_grouped_topic_indicators(product_code)
            if grouped:
                placeholder_num_id = item_ids.get(
                    ("input", _map_indicator_item_name(product_code, "业务支出合计"))
                )
                placeholder_den_id = item_ids.get(
                    ("output", _map_indicator_item_name(product_code, "营业收入（还原）"))
                )
                if placeholder_num_id is not None and placeholder_den_id is not None:
                    for group_name in B_LINE_INDICATOR_GROUPS:
                        cur = await db.execute(
                            """
                            INSERT INTO business_cost_income_indicator(
                              product_code, name, parent_id, display_group, topic_metric_node_code,
                              numerator_section, numerator_item_id, numerator_value_mode,
                              denominator_section, denominator_item_id, denominator_value_mode,
                              format, annualize, sort_order, enabled
                            ) VALUES (?, ?, NULL, 1, NULL, 'input', ?, 'tree', 'output', ?, 'tree', 'ratio', 0, ?, ?)
                            """,
                            (
                                product_code,
                                group_name,
                                placeholder_num_id,
                                placeholder_den_id,
                                indicator_sort,
                                1 if bcir_indicator_enabled(product_code, group_name) else 0,
                            ),
                        )
                        group_ids[group_name] = int(cur.lastrowid)  # type: ignore[attr-defined]
                        indicator_sort += 1
            for leaf_spec in _indicator_leaf_specs_for_product(product_code):
                name, parent_group, numerator_name, denominator_name, fmt, num_mode, den_mode, _products = leaf_spec
                mapped_numerator = _map_indicator_item_name(product_code, numerator_name)
                mapped_denominator = _map_indicator_item_name(product_code, denominator_name)
                numerator_id = item_ids.get(("input", mapped_numerator))
                denominator_id = item_ids.get(("output", mapped_denominator))
                if numerator_id is None or denominator_id is None:
                    continue
                if grouped:
                    parent_id = group_ids.get(parent_group)
                    if parent_id is None:
                        continue
                    await db.execute(
                        """
                        INSERT INTO business_cost_income_indicator(
                          product_code, name, parent_id, display_group, topic_metric_node_code,
                          numerator_section, numerator_item_id, numerator_value_mode,
                          denominator_section, denominator_item_id, denominator_value_mode,
                          format, annualize, sort_order, enabled
                        ) VALUES (?, ?, ?, 0, NULL, 'input', ?, ?, 'output', ?, ?, ?, 0, ?, ?)
                        """,
                        (
                            product_code,
                            name,
                            parent_id,
                            numerator_id,
                            num_mode,
                            denominator_id,
                            den_mode,
                            fmt,
                            indicator_sort,
                            1 if bcir_indicator_enabled(product_code, name) else 0,
                        ),
                    )
                else:
                    await db.execute(
                        """
                        INSERT INTO business_cost_income_indicator(
                          product_code, name, parent_id, display_group, topic_metric_node_code,
                          numerator_section, numerator_item_id, numerator_value_mode,
                          denominator_section, denominator_item_id, denominator_value_mode,
                          format, annualize, sort_order, enabled
                        ) VALUES (?, ?, NULL, 0, NULL, 'input', ?, 'tree', 'output', ?, 'tree', ?, 0, ?, ?)
                        """,
                        (
                            product_code,
                            name,
                            numerator_id,
                            denominator_id,
                            fmt,
                            indicator_sort,
                            1 if bcir_indicator_enabled(product_code, name) else 0,
                        ),
                    )
                indicator_sort += 1
    await repair_bcir_item_identity(db)
