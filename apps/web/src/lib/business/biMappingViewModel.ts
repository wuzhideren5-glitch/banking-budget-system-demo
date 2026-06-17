import type { DeptAccountDto } from "@/lib/expense/masterDataApi";
import type { BiAiSubjectMappingDto, ManageDeptOwnerMappingDto } from "@/lib/business/biMappingApi";
import { buildDeptTree, sortDeptEntityNames, type DeptTreeNode } from "@/lib/business/deptCatalogViewModel";

export type { DeptTreeNode };
export type DeptEntityGroup = { entity_name: string; groups: { group_name: string; departments: string[] }[] };
export type BiAiSubjectColumn = { key: keyof BiAiSubjectMappingDto; label: string; editable?: boolean };
export type ManageDeptOwnerDepartmentGroup = { department: string; items: ManageDeptOwnerMappingDto[] };
export type ManageDeptOwnerBusinessGroup = {
  groupName: string;
  departmentGroups: ManageDeptOwnerDepartmentGroup[];
};

export const OTHER_MANAGE_DEPARTMENT_OPTION = "__OTHER_MANAGE_DEPARTMENT__";
export const OTHER_OWNER_DEPARTMENT_LABEL = "其他";

export const BI_AI_SUBJECT_COLUMNS: BiAiSubjectColumn[] = [
  { key: "level5_code", label: "五级编码" },
  { key: "level5_name", label: "五级名称" },
  { key: "level6_code", label: "六级编码" },
  { key: "level6_name", label: "六级名称" },
  { key: "budget_release_caliber", label: "预算发布口径（二级）" },
  { key: "fee_category", label: "费用类别（一级）" },
  { key: "fee_major", label: "费用大类" },
  { key: "manage_department", label: "归口部门", editable: true },
];

export function filterBiAiSubjectMappings(
  rows: BiAiSubjectMappingDto[],
  rawKeyword: string,
): BiAiSubjectMappingDto[] {
  const keyword = rawKeyword.trim().toLowerCase();
  if (!keyword) return rows;
  return rows.filter((row) => {
    const values = [
      ...BI_AI_SUBJECT_COLUMNS.map((column) => row[column.key]),
      ...Object.values(row as Record<string, unknown>),
    ];
    return values.some((value) => {
      if (Array.isArray(value)) {
        return value.some((item) => String(item).toLowerCase().includes(keyword));
      }
      return String(value ?? "").toLowerCase().includes(keyword);
    });
  });
}

export function buildDeptEntityGroups(rows: DeptAccountDto[]): DeptEntityGroup[] {
  const groupsByEntity = new Map<string, DeptTreeNode[]>();
  buildDeptTree(rows).forEach((node) => {
    const entityName = node.entity_name || "微众银行";
    groupsByEntity.set(entityName, [...(groupsByEntity.get(entityName) ?? []), node]);
  });
  return sortDeptEntityNames(groupsByEntity.keys()).map((entityName) => ({
    entity_name: entityName,
    groups: (groupsByEntity.get(entityName) ?? []).map((group) => ({
      group_name: group.dept_name,
      departments: group.children.map((child) => child.dept_name),
    })),
  }));
}

export function filterDeptEntityGroups(entityGroups: DeptEntityGroup[], rawKeyword: string): DeptEntityGroup[] {
  const keyword = rawKeyword.trim().toLowerCase();
  if (!keyword) return entityGroups;
  return entityGroups
    .map((entity) => ({
      entity_name: entity.entity_name,
      groups: entity.groups
        .filter((group) => {
          if (entity.entity_name.toLowerCase().includes(keyword)) return true;
          if (group.group_name.toLowerCase().includes(keyword)) return true;
          return group.departments.some((dept) => dept.toLowerCase().includes(keyword));
        })
        .map((group) => ({
          group_name: group.group_name,
          departments:
            entity.entity_name.toLowerCase().includes(keyword) || group.group_name.toLowerCase().includes(keyword)
              ? group.departments
              : group.departments.filter((dept) => dept.toLowerCase().includes(keyword)),
        }))
        .filter((group) => group.departments.length > 0),
    }))
    .filter((entity) => entity.groups.length > 0);
}

export function shouldShowOtherOwnerDepartment(rawKeyword: string): boolean {
  const keyword = rawKeyword.trim().toLowerCase();
  return !keyword || OTHER_OWNER_DEPARTMENT_LABEL.toLowerCase().includes(keyword);
}

export function sortManageDepartments(departments: string[]): string[] {
  return [...departments].sort((a, b) => a.length - b.length || a.localeCompare(b, "zh-CN"));
}

export function buildOwnerDepartmentGroupIndex(rows: DeptAccountDto[]): Map<string, string> {
  const map = new Map<string, string>();
  buildDeptEntityGroups(rows).forEach((entity) =>
    entity.groups.forEach((group) =>
      group.departments.forEach((department) => map.set(department, group.group_name))
    )
  );
  map.set(OTHER_OWNER_DEPARTMENT_LABEL, OTHER_OWNER_DEPARTMENT_LABEL);
  return map;
}

export function buildManageDeptOwnerBusinessGroups(
  mappings: ManageDeptOwnerMappingDto[],
  rows: DeptAccountDto[],
): ManageDeptOwnerBusinessGroup[] {
  const ownerToGroup = buildOwnerDepartmentGroupIndex(rows);
  const groupMap = new Map<string, Map<string, ManageDeptOwnerMappingDto[]>>();
  mappings.forEach((mapping) => {
    const groupName = ownerToGroup.get(mapping.owner_department) || "未分组";
    if (!groupMap.has(groupName)) groupMap.set(groupName, new Map());
    const departmentMap = groupMap.get(groupName)!;
    const department = mapping.owner_department || "未分类";
    departmentMap.set(department, [...(departmentMap.get(department) ?? []), mapping]);
  });
  return Array.from(groupMap.keys())
    .sort((a, b) => a.localeCompare(b, "zh-CN"))
    .map((groupName) => ({
      groupName,
      departmentGroups: Array.from(groupMap.get(groupName)!.entries())
        .map(([department, items]) => ({ department, items }))
        .sort((a, b) => a.department.length - b.department.length),
    }));
}
