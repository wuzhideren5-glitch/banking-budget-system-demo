export function requireNonEmpty(value: string, fieldLabel: string): string | null {
  if (!value.trim()) return `${fieldLabel}不能为空`;
  return null;
}

export function validateReportCode(code: string): string | null {
  if (!/^[A-Z]\d+$/.test(code)) {
    return "报告科目代码格式错误，应为大写字母开头 + 数字（例如 X01）";
  }
  return null;
}

export function validateDepartmentNodeCode(
  nodeType: "department" | "product",
  code: string
): string | null {
  if (nodeType === "department" && !/^Y\d+$/.test(code)) {
    return "部门代码格式错误，应为 Y 开头 + 数字（例如 Y11）";
  }
  if (nodeType === "product" && !/^Z\d{4}$/.test(code)) {
    return "产品代码格式错误，应为 Z + 4 位数字（例如 Z0001）";
  }
  return null;
}
