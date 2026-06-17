export const EXPENSE_BUDGET_AMOUNT_UNITS = [
  { value: "hundred_million", label: "亿元" },
  { value: "million", label: "百万元" },
  { value: "ten_thousand", label: "万元" },
  { value: "yuan", label: "元" },
] as const;

export type ExpenseBudgetAmountUnit = (typeof EXPENSE_BUDGET_AMOUNT_UNITS)[number]["value"];

const UNIT_DIVISORS: Record<ExpenseBudgetAmountUnit, number> = {
  yuan: 1,
  ten_thousand: 10_000,
  million: 1_000_000,
  hundred_million: 100_000_000,
};

export function amountUnitLabel(unit: ExpenseBudgetAmountUnit): string {
  return EXPENSE_BUDGET_AMOUNT_UNITS.find((item) => item.value === unit)?.label ?? unit;
}

export function toDisplayAmount(baseYuan: number, unit: ExpenseBudgetAmountUnit): number {
  const scaled = baseYuan / UNIT_DIVISORS[unit];
  if (unit === "hundred_million") {
    return Math.round(scaled * 100) / 100;
  }
  return Math.round(scaled);
}

export function toBaseAmount(displayAmount: number, unit: ExpenseBudgetAmountUnit): number {
  return Math.round(displayAmount * UNIT_DIVISORS[unit] * 100) / 100;
}

export function formatDisplayAmount(baseYuan: number, unit: ExpenseBudgetAmountUnit): string {
  const display = toDisplayAmount(baseYuan, unit);
  if (unit === "hundred_million") {
    return display.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return display.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function formatDisplayAmountInput(baseYuan: number, unit: ExpenseBudgetAmountUnit): string {
  const display = toDisplayAmount(baseYuan, unit);
  if (unit === "hundred_million") {
    return display.toFixed(2);
  }
  return String(display);
}
