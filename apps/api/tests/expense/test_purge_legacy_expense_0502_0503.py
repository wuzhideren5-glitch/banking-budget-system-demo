from __future__ import annotations

import unittest

from app.services.business_admin_expense_metric_tree import is_legacy_expense_hr_or_non_hr_branch


class PurgeLegacyExpense05020503Tests(unittest.TestCase):
    def test_detects_0502_and_0503_branches(self) -> None:
        self.assertTrue(is_legacy_expense_hr_or_non_hr_branch("CORP.05.02"))
        self.assertTrue(is_legacy_expense_hr_or_non_hr_branch("CORP.05.03.01.004"))
        self.assertTrue(is_legacy_expense_hr_or_non_hr_branch("A01.05.02.01.001"))

    def test_keeps_0501_indirect_subtree(self) -> None:
        self.assertFalse(is_legacy_expense_hr_or_non_hr_branch("CORP.05.01"))
        self.assertFalse(is_legacy_expense_hr_or_non_hr_branch("CORP.05.01.02"))
        self.assertFalse(is_legacy_expense_hr_or_non_hr_branch("CORP.05.01.02.03.01.001"))


if __name__ == "__main__":
    unittest.main()
