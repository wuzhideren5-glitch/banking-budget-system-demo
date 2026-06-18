from __future__ import annotations

import unittest
from pathlib import Path

from app.services.department_expense_contracts import validate_dept_code_with_parent


class DepartmentExpenseContractsTests(unittest.TestCase):
    def test_validates_department_code_hierarchy_contract(self) -> None:
        self.assertIsNone(validate_dept_code_with_parent("Y1", 1, None))
        self.assertIsNone(validate_dept_code_with_parent("Y01", 1, None))
        self.assertIsNone(validate_dept_code_with_parent("Y101", 2, "Y1"))
        self.assertIsNone(validate_dept_code_with_parent("Y10101", 2, "Y101"))

        self.assertEqual(
            validate_dept_code_with_parent("X1", 1, None),
            "1级部门科目代码格式错误（示例：Y1 或 Y01）",
        )
        self.assertEqual(
            validate_dept_code_with_parent("Y101", 2, None),
            "缺少上级部门科目，无法校验第2级部门科目代码",
        )
        self.assertEqual(
            validate_dept_code_with_parent("Y201", 2, "Y1"),
            "第2级部门科目代码必须继承上级代码前缀",
        )
        self.assertEqual(
            validate_dept_code_with_parent("Y1ABC", 2, "Y1"),
            "第2级部门科目代码应为“上级代码 + 1-2位数字”",
        )

    def test_main_no_longer_keeps_department_code_validation_implementation(self) -> None:
        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("def _validate_dept_code_with_parent", main_source)
        self.assertNotIn("1级部门科目代码格式错误", main_source)
        self.assertIn("validate_dept_code_with_parent", main_source)


if __name__ == "__main__":
    unittest.main()
