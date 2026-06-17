import { expect, test } from "@playwright/test";
import {
  buildManageDeptOwnerBusinessGroups,
  filterBiAiSubjectMappings,
  shouldShowOtherOwnerDepartment,
  sortManageDepartments,
} from "../src/lib/biMappingViewModel";
import type { BiAiSubjectMappingDto, ManageDeptOwnerMappingDto } from "../src/lib/biMappingApi";
import type { DeptAccountDto } from "../src/lib/masterDataApi";

const subjectRows: BiAiSubjectMappingDto[] = [
  {
    id: 1,
    level2_name: "业务费用",
    level3_code: "BI-100",
    level3_name: "科技支出",
    level4_code: "L4-1",
    level4_name: "云资源",
    level5_code: "L5-1",
    level5_name: "对象存储",
    level6_code: "L6-1",
    level6_name: "存储桶",
    budget_release_caliber: "IT费用",
    fee_category: "科技",
    fee_major: "云服务",
    sort_order: 1,
    source_file: "BI科目匹配表.xlsx",
  },
  {
    id: 2,
    level2_name: "日常费用",
    level3_code: "BI-200",
    level3_name: "差旅",
    level4_code: "L4-2",
    level4_name: "国内差旅",
    level5_code: "L5-2",
    level5_name: "机票",
    level6_code: "L6-2",
    level6_name: "经济舱",
    budget_release_caliber: "日常费用",
    fee_category: "行政",
    fee_major: "差旅",
    sort_order: 2,
    source_file: "BI科目匹配表.xlsx",
  },
];

const deptRows: DeptAccountDto[] = [
  { dept_code: "Y1", dept_name: "个人金融事业群", entity_name: "微众银行", parent_code: null, level: 1, is_leaf: false },
  { dept_code: "Y101", dept_name: "零售产品部", entity_name: "微众银行", parent_code: "Y1", level: 2, is_leaf: true },
  { dept_code: "Y102", dept_name: "财富管理部", entity_name: "微众银行", parent_code: "Y1", level: 2, is_leaf: true },
  { dept_code: "Y2", dept_name: "科技及智能事业群", entity_name: "微众银行", parent_code: null, level: 1, is_leaf: false },
  { dept_code: "Y201", dept_name: "平台工程部", entity_name: "微众银行", parent_code: "Y2", level: 2, is_leaf: true },
];

const mappings: ManageDeptOwnerMappingDto[] = [
  { id: 1, owner_department: "平台工程部", manage_department: "技术管理部" },
  { id: 2, owner_department: "零售产品部", manage_department: "零售综合部" },
  { id: 3, owner_department: "其他", manage_department: "临时管理部门" },
];

test("filters BI-AI subject mappings by any visible column", () => {
  expect(filterBiAiSubjectMappings(subjectRows, "云服务").map((row) => row.id)).toEqual([1]);
  expect(filterBiAiSubjectMappings(subjectRows, "BI-200").map((row) => row.id)).toEqual([2]);
  expect(filterBiAiSubjectMappings(subjectRows, "不存在")).toEqual([]);
});

test("keeps BI department owner options and mapping groups stable", () => {
  expect(shouldShowOtherOwnerDepartment("")).toBe(true);
  expect(shouldShowOtherOwnerDepartment("其他")).toBe(true);
  expect(shouldShowOtherOwnerDepartment("平台")).toBe(false);
  expect(sortManageDepartments(["长期管理部门", "短部", "中等部门"])).toEqual(["短部", "中等部门", "长期管理部门"]);

  expect(buildManageDeptOwnerBusinessGroups(mappings, deptRows)).toEqual([
    {
      groupName: "个人金融事业群",
      departmentGroups: [{ department: "零售产品部", items: [mappings[1]] }],
    },
    {
      groupName: "科技及智能事业群",
      departmentGroups: [{ department: "平台工程部", items: [mappings[0]] }],
    },
    {
      groupName: "其他",
      departmentGroups: [{ department: "其他", items: [mappings[2]] }],
    },
  ]);
});
