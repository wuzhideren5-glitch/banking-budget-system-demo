"""Shared mode contracts for expense budget execution reports."""
from __future__ import annotations


DISPLAY_REPORT_MODES = frozenset({"query", "template", "subject"})
EXPORT_REPORT_MODES = frozenset({"query", "template", "subject", "flat"})
REPORT_PERSPECTIVES = frozenset({"entity", "group", "owner_dept"})
