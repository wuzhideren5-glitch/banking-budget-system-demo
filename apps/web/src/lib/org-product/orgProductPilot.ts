/** 阶段 1 试点：B01 企业金融 · 企业金融业务状况表 */
export const PILOT_ENTITY_CODE = "B01";
export const PILOT_TABLE_NAME = "企业金融业务状况表";

export function pickPilotEntityCode(
  candidates: string[],
  prior: string,
  fallback: string
): string {
  const trimmed = prior.trim();
  if (trimmed && candidates.includes(trimmed)) return trimmed;
  if (candidates.includes(PILOT_ENTITY_CODE)) return PILOT_ENTITY_CODE;
  return fallback;
}

/** 在指标表名列表中优先选中试点表 */
export function pickPilotTableName(tableNames: string[], prior: string): string {
  const names = tableNames.map((n) => n.trim()).filter(Boolean);
  if (!names.length) return PILOT_TABLE_NAME;
  const trimmed = prior.trim();
  if (trimmed && names.includes(trimmed)) return trimmed;
  const exact = names.find((n) => n === PILOT_TABLE_NAME);
  if (exact) return exact;
  const fuzzy = names.find((n) => n.includes("企业金融") && n.includes("业务状况"));
  if (fuzzy) return fuzzy;
  const status = names.find((n) => n.includes("业务状况"));
  return status ?? names[0];
}

/** 预测输出「年度汇总」列口径说明 */
export function annualAggHint(nature: string, hasFormula: boolean): string {
  const n = String(nature || "").trim();
  if (hasFormula && isRateLikeNature(n)) {
    return "按公式重算（引用项为全年口径）";
  }
  if (n === "资产余额" || n === "负债余额") return "取 12 月";
  if (n === "资产日均" || n === "负债日均") return "按当月天数加权全年日均";
  if (n === "收入" || n === "支出" || n === "利润") return "12 个月合计";
  if (isRateLikeNature(n)) return "取 12 月（未配公式时）";
  return "12 个月算术平均";
}

function isRateLikeNature(nature: string): boolean {
  if (["收入", "支出", "利润", "资产余额", "负债余额", "资产日均", "负债日均"].includes(nature)) {
    return false;
  }
  return nature.includes("率") || nature.includes("占比") || nature.includes("比例");
}
