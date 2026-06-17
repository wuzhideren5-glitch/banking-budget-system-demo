import { expect, test } from "@playwright/test";
import { buildExpenseBudgetExecutionExportPayload } from "../src/lib/expenseBudgetExecutionApi";
import type { ExpenseBudgetExecutionExportRequest } from "../src/lib/expenseBudgetExecutionApi";
import {
  buildExpenseBudgetExecutionExportRequest,
  buildExpenseBudgetExecutionReportRequest,
  getExpenseBudgetExecutionAmountDivisor,
  getExpenseBudgetExecutionModeView,
  normalizeExpenseBudgetExecutionAmountUnit,
  normalizeExpenseBudgetExecutionReportMode,
  normalizeExpenseBudgetExecutionReportMonth,
  normalizeExpenseBudgetExecutionSubjectId,
} from "../src/lib/expenseBudgetExecutionViewModel";

const baseState = {
  reportMode: "template" as const,
  perspective: "group" as const,
  amountUnit: "ten_thousand" as const,
  activeKeyword: "差旅",
  includeZeroRows: true,
  queryEntityName: "查询主体",
  queryGroupName: "查询事业群",
  queryOwnerDept: "查询归属部门",
  queryReportMonth: "2",
  subjectEntityName: "科目主体",
  subjectReportMonth: "3",
  subjectSelectedId: "12",
  templateEntityName: "模板主体",
  templateGroupName: "模板事业群",
  templateOwnerDept: "模板归属部门",
  templateReportMonth: "4",
};

test("keeps display request free of export-only amount unit", () => {
  const request = buildExpenseBudgetExecutionReportRequest(baseState);

  expect("amountUnit" in request).toBe(false);
  expect(request).toMatchObject({
    mode: "template",
    perspective: "group",
    keyword: "差旅",
    includeZeroRows: true,
    entityName: "模板主体",
    groupName: "模板事业群",
    ownerDept: "模板归属部门",
    reportMonth: "4",
  });
});

test("keeps amount unit on export request only", () => {
  const request = buildExpenseBudgetExecutionExportRequest({
    ...baseState,
    includeMonthlyActuals: true,
    includeLastYearMonthlyActuals: false,
  });

  expect(request.amountUnit).toBe("ten_thousand");
  expect(request.reportMonth).toBe(4);
  expect(request.includeMonthlyActuals).toBe(true);
  expect(request.includeLastYearMonthlyActuals).toBe(false);
});

test("derives export monthly flags without caller tree-section knowledge", () => {
  const request = buildExpenseBudgetExecutionExportRequest({
    ...baseState,
    includeMonthlyActuals: true,
    includeLastYearMonthlyActuals: true,
  });

  expect(request.includeMonthlyActuals).toBe(true);
  expect(request.includeLastYearMonthlyActuals).toBe(true);
});

test("serializes flat export mode separately from display modes", () => {
  const request: ExpenseBudgetExecutionExportRequest = {
    mode: "flat",
    perspective: "owner_dept",
    amountUnit: "thousand",
    keyword: "办公",
    includeZeroRows: false,
    entityName: "微众银行",
    groupName: "科技事业群",
    ownerDept: "平台部",
    includeMonthlyActuals: false,
    includeLastYearMonthlyActuals: false,
  };

  expect(buildExpenseBudgetExecutionExportPayload(request)).toEqual({
    mode: "flat",
    perspective: "owner_dept",
    amount_unit: "thousand",
    keyword: "办公",
    include_zero_rows: false,
    entity_name: "微众银行",
    group_name: "科技事业群",
    owner_dept: "平台部",
    subject_id: undefined,
    report_month: undefined,
    include_monthly_actuals: false,
    include_last_year_monthly_actuals: false,
  });
});

test("keeps report mode UI facts in the view model", () => {
  expect(
    getExpenseBudgetExecutionModeView({
      reportMode: "query",
      templateKeyword: "模板关键字",
      subjectKeyword: "科目关键字",
    }),
  ).toEqual({
    isTreeReportMode: false,
    hasTreeSection: true,
    activeKeyword: "",
    keywordMode: null,
  });

  expect(
    getExpenseBudgetExecutionModeView({
      reportMode: "template",
      templateKeyword: "模板关键字",
      subjectKeyword: "科目关键字",
    }),
  ).toEqual({
    isTreeReportMode: true,
    hasTreeSection: true,
    activeKeyword: "模板关键字",
    keywordMode: "template",
  });

  expect(
    getExpenseBudgetExecutionModeView({
      reportMode: "subject",
      templateKeyword: "模板关键字",
      subjectKeyword: "科目关键字",
    }),
  ).toEqual({
    isTreeReportMode: true,
    hasTreeSection: true,
    activeKeyword: "科目关键字",
    keywordMode: "subject",
  });
});

test("normalizes report month values in the view model", () => {
  expect(normalizeExpenseBudgetExecutionReportMonth(null)).toBe("");
  expect(normalizeExpenseBudgetExecutionReportMonth("")).toBe("");
  expect(normalizeExpenseBudgetExecutionReportMonth("0")).toBe("");
  expect(normalizeExpenseBudgetExecutionReportMonth("13")).toBe("");
  expect(normalizeExpenseBudgetExecutionReportMonth("3.5")).toBe("");
  expect(normalizeExpenseBudgetExecutionReportMonth("04")).toBe("4");
  expect(normalizeExpenseBudgetExecutionReportMonth(12)).toBe("12");
});

test("normalizes display request report month in the view model", () => {
  expect(
    buildExpenseBudgetExecutionReportRequest({
      ...baseState,
      reportMode: "query",
      queryReportMonth: "04",
    }).reportMonth,
  ).toBe("4");

  expect(
    buildExpenseBudgetExecutionReportRequest({
      ...baseState,
      reportMode: "query",
      queryReportMonth: "13",
    }).reportMonth,
  ).toBe("");
});

test("normalizes stored report mode values in the view model", () => {
  expect(normalizeExpenseBudgetExecutionReportMode("query")).toBe("query");
  expect(normalizeExpenseBudgetExecutionReportMode("template")).toBe("template");
  expect(normalizeExpenseBudgetExecutionReportMode("subject")).toBe("subject");
  expect(normalizeExpenseBudgetExecutionReportMode(null)).toBeNull();
  expect(normalizeExpenseBudgetExecutionReportMode("flat")).toBeNull();
  expect(normalizeExpenseBudgetExecutionReportMode("legacy-template")).toBeNull();
});

test("normalizes stored amount unit values in the view model", () => {
  expect(normalizeExpenseBudgetExecutionAmountUnit("yuan")).toBe("yuan");
  expect(normalizeExpenseBudgetExecutionAmountUnit("thousand")).toBe("thousand");
  expect(normalizeExpenseBudgetExecutionAmountUnit("ten_thousand")).toBe("ten_thousand");
  expect(normalizeExpenseBudgetExecutionAmountUnit("million")).toBe("million");
  expect(normalizeExpenseBudgetExecutionAmountUnit("hundred_million")).toBe("hundred_million");
  expect(normalizeExpenseBudgetExecutionAmountUnit(null)).toBeNull();
  expect(normalizeExpenseBudgetExecutionAmountUnit("wan")).toBeNull();
  expect(normalizeExpenseBudgetExecutionAmountUnit("legacy-yuan")).toBeNull();
});

test("keeps amount unit divisor lookup in the view model", () => {
  expect(getExpenseBudgetExecutionAmountDivisor("yuan")).toBe(1);
  expect(getExpenseBudgetExecutionAmountDivisor("thousand")).toBe(1_000);
  expect(getExpenseBudgetExecutionAmountDivisor("ten_thousand")).toBe(10_000);
  expect(getExpenseBudgetExecutionAmountDivisor("million")).toBe(1_000_000);
  expect(getExpenseBudgetExecutionAmountDivisor("hundred_million")).toBe(100_000_000);
  expect(getExpenseBudgetExecutionAmountDivisor("legacy-yuan")).toBe(1);
});

test("normalizes subject id values in the view model", () => {
  expect(normalizeExpenseBudgetExecutionSubjectId(null)).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("")).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("0")).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("-1")).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("3.5")).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("abc")).toBe("");
  expect(normalizeExpenseBudgetExecutionSubjectId("007")).toBe("7");
  expect(normalizeExpenseBudgetExecutionSubjectId(12)).toBe("12");
});

test("drops invalid subject id from display and export requests", () => {
  const invalidSubjectState = {
    ...baseState,
    reportMode: "subject" as const,
    subjectSelectedId: "abc",
    includeMonthlyActuals: false,
    includeLastYearMonthlyActuals: false,
  };

  expect(buildExpenseBudgetExecutionReportRequest(invalidSubjectState).subjectId).toBe("");
  expect(buildExpenseBudgetExecutionExportRequest(invalidSubjectState).subjectId).toBeUndefined();
});
