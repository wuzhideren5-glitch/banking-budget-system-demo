"""Current database contracts for the department-expense module."""

import re

DEPT_GROUP_LEVEL = 1
DEPT_OWNER_LEVEL = 2
MAX_DEPT_LEVEL = DEPT_OWNER_LEVEL

BUDGET_SUBJECT_LEVEL_NAME_TO_NUMBER = {"一级": 1, "二级": 2, "三级": 3, "四级": 4, "五级": 5}
BUDGET_SUBJECT_LEVEL_NUMBER_TO_NAME = {
    value: key for key, value in BUDGET_SUBJECT_LEVEL_NAME_TO_NUMBER.items()
}
MIN_BUDGET_SUBJECT_LEVEL = min(BUDGET_SUBJECT_LEVEL_NAME_TO_NUMBER.values())
MAX_BUDGET_SUBJECT_LEVEL = max(BUDGET_SUBJECT_LEVEL_NAME_TO_NUMBER.values())


def validate_dept_code_with_parent(code: str, level: int, parent_code: str | None) -> str | None:
    if level == DEPT_GROUP_LEVEL:
        if not re.match(r"^Y\d{1,2}$", code):
            return "1级部门科目代码格式错误（示例：Y1 或 Y01）"
        return None
    if not parent_code:
        return f"缺少上级部门科目，无法校验第{level}级部门科目代码"
    if not code.startswith(parent_code):
        return f"第{level}级部门科目代码必须继承上级代码前缀"
    suffix = code[len(parent_code):]
    if not re.match(r"^\d{1,2}$", suffix):
        return f"第{level}级部门科目代码应为“上级代码 + 1-2位数字”"
    return None
