import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Pencil, Plus, RefreshCw, Search, Trash2, Wand2 } from "lucide-react";
import {
  autoGenerateManageDeptOwnerMappings,
  createManageDeptOwnerMapping,
  deleteManageDeptOwnerMapping,
  getManageDeptOwnerReferenceData,
  listManageDeptOwnerMappings,
  updateManageDeptOwnerMapping,
  type AutoGenerateResultDto,
  type ManageDeptOwnerMappingDto,
  type ManageDeptOwnerReferenceDataDto,
} from "@/lib/business/biMappingApi";
import {
  buildDeptEntityGroups,
  buildManageDeptOwnerBusinessGroups,
  filterDeptEntityGroups,
  OTHER_MANAGE_DEPARTMENT_OPTION,
  OTHER_OWNER_DEPARTMENT_LABEL,
  shouldShowOtherOwnerDepartment,
  sortManageDepartments,
} from "@/lib/business/biMappingViewModel";
import { listDeptAccounts, type DeptAccountDto } from "@/lib/expense/masterDataApi";

export function ManageDeptOwnerMappingTab() {
  const [mappings, setMappings] = useState<ManageDeptOwnerMappingDto[]>([]);
  const [refData, setRefData] = useState<ManageDeptOwnerReferenceDataDto | null>(null);
  const [deptRows, setDeptRows] = useState<DeptAccountDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ manage_department: "", owner_department: "" });
  const [useCustomManageDepartment, setUseCustomManageDepartment] = useState(false);
  const [customManageDepartment, setCustomManageDepartment] = useState("");
  const [useCustomOwnerDepartment, setUseCustomOwnerDepartment] = useState(false);
  const [customOwnerDepartment, setCustomOwnerDepartment] = useState("");
  const [autoResult, setAutoResult] = useState<AutoGenerateResultDto | null>(null);
  const [ownerDeptSearch, setOwnerDeptSearch] = useState("");
  const [ownerDeptDropdownOpen, setOwnerDeptDropdownOpen] = useState(false);
  const ownerDeptDropdownRef = useRef<HTMLDivElement>(null);

  const loadMappings = useCallback(async () => {
    setLoading(true);
    try {
      setMappings(await listManageDeptOwnerMappings());
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRefData = useCallback(async () => {
    const [referenceRows, departmentRows] = await Promise.all([
      getManageDeptOwnerReferenceData(),
      listDeptAccounts(),
    ]);
    setRefData(referenceRows);
    setDeptRows(departmentRows);
  }, []);

  useEffect(() => {
    void loadMappings();
    void loadRefData();
  }, [loadMappings, loadRefData]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ownerDeptDropdownRef.current && !ownerDeptDropdownRef.current.contains(event.target as Node)) setOwnerDeptDropdownOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredOwnerDeptGroups = useMemo(() => filterDeptEntityGroups(buildDeptEntityGroups(deptRows), ownerDeptSearch), [deptRows, ownerDeptSearch]);
  const showOtherOwnerDepartment = useMemo(() => shouldShowOtherOwnerDepartment(ownerDeptSearch), [ownerDeptSearch]);
  const sortedManageDepartments = useMemo(() => sortManageDepartments(refData?.manage_departments ?? []), [refData]);
  const businessGrouped = useMemo(() => buildManageDeptOwnerBusinessGroups(mappings, deptRows), [mappings, deptRows]);

  const resetDialog = () => {
    setShowDialog(false);
    setEditingId(null);
    setForm({ manage_department: "", owner_department: "" });
    setUseCustomManageDepartment(false);
    setCustomManageDepartment("");
    setUseCustomOwnerDepartment(false);
    setCustomOwnerDepartment("");
    setOwnerDeptSearch("");
    setOwnerDeptDropdownOpen(false);
  };

  const openCreateDialog = () => {
    resetDialog();
    setShowDialog(true);
  };

  const openEditDialog = (mapping: ManageDeptOwnerMappingDto) => {
    setEditingId(mapping.id);
    setForm({ manage_department: mapping.manage_department, owner_department: mapping.owner_department });
    setUseCustomManageDepartment(false);
    setCustomManageDepartment("");
    setUseCustomOwnerDepartment(false);
    setCustomOwnerDepartment("");
    setShowDialog(true);
  };

  const handleSave = async () => {
    const manageDepartment = useCustomManageDepartment ? customManageDepartment.trim() : form.manage_department;
    const ownerDepartment = useCustomOwnerDepartment ? customOwnerDepartment.trim() : form.owner_department;
    if (!manageDepartment || !ownerDepartment) return;
    if (editingId === null) {
      await createManageDeptOwnerMapping({ manage_department: manageDepartment, owner_department: ownerDepartment });
    } else {
      await updateManageDeptOwnerMapping(editingId, { owner_department: ownerDepartment });
    }
    resetDialog();
    await loadMappings();
  };

  const handleDelete = async (id: number) => {
    await deleteManageDeptOwnerMapping(id);
    await loadMappings();
  };

  const handleAutoGenerate = async () => {
    const result = await autoGenerateManageDeptOwnerMappings();
    setAutoResult(result);
    await loadMappings();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button onClick={handleAutoGenerate} className="flex items-center gap-1.5 rounded bg-purple-600 px-3 py-1.5 text-xs text-white hover:bg-purple-700">
          <Wand2 className="h-3.5 w-3.5" />
          从已有数据自动生成
        </button>
        <button onClick={openCreateDialog} className="flex items-center gap-1.5 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700">
          <Plus className="h-3.5 w-3.5" />
          新增映射
        </button>
        <button
          onClick={() => {
            void loadMappings();
            void loadRefData();
            setAutoResult(null);
          }}
          className="flex items-center gap-1.5 rounded bg-gray-500 px-3 py-1.5 text-xs text-white hover:bg-gray-600"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          刷新
        </button>
      </div>

      {autoResult ? <div className="rounded border border-purple-200 bg-purple-50 px-3 py-2 text-xs text-purple-700">自动生成完成：新增 {autoResult.generated} 条映射，跳过 {autoResult.skipped} 条（已存在）</div> : null}

      <div className="rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-xs text-gray-500">
        <strong>说明：</strong>费用执行明细导入时，若“费用归属部门”列无法直接匹配到部门科目，系统将根据“归口管理部门”查 BI部门维护确定费用归属部门。
        多个归口管理部门可映射到同一个费用归属部门。此映射仅用于费用执行明细导入，不影响费用预算执行报表和费用预测表。
      </div>

      {loading ? (
        <div className="py-8 text-center text-gray-400">加载中...</div>
      ) : mappings.length === 0 ? (
        <div className="py-8 text-center text-gray-400">暂无BI部门维护规则，请点击“从已有数据自动生成”或“新增映射”</div>
      ) : (
        <table className="w-full border-collapse text-xs">
          <thead className="bg-gray-100">
            <tr className="text-left text-gray-700">
              <th className="border border-gray-200 px-3 py-2">事业群</th>
              <th className="border border-gray-200 px-3 py-2">费用归属部门</th>
              <th className="border border-gray-200 px-3 py-2">归口部门</th>
              <th className="w-[80px] border border-gray-200 px-3 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {businessGrouped.map(({ groupName, departmentGroups }) => {
              const totalRows = departmentGroups.reduce((sum, departmentGroup) => sum + departmentGroup.items.length, 0);
              return (
                <Fragment key={groupName}>
                  {departmentGroups.map(({ department, items }, departmentIndex) => (
                    <Fragment key={department}>
                      {items.map((mapping, mappingIndex) => (
                        <tr key={mapping.id} className={mappingIndex === 0 && departmentIndex === 0 ? "bg-blue-50/50" : "hover:bg-gray-50"}>
                          {departmentIndex === 0 && mappingIndex === 0 ? (
                            <td className="border border-gray-200 px-3 py-1.5 font-bold text-blue-800" rowSpan={totalRows}>
                              {groupName}
                            </td>
                          ) : null}
                          <td className="border border-gray-200 px-3 py-1.5 text-gray-700">{mapping.manage_department}</td>
                          {mappingIndex === 0 ? (
                            <td className="border border-gray-200 px-3 py-1.5 font-medium text-gray-800" rowSpan={items.length}>
                              {department}
                            </td>
                          ) : null}
                          <td className="border border-gray-200 px-3 py-1.5">
                            <div className="flex items-center gap-1">
                              <button onClick={() => openEditDialog(mapping)} className="p-1 text-gray-400 hover:text-blue-600" title="编辑">
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                              <button onClick={() => void handleDelete(mapping.id)} className="p-1 text-gray-400 hover:text-red-600" title="删除">
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      {showDialog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[480px] rounded-lg bg-white p-5 shadow-xl">
            <h3 className="mb-4 text-sm font-semibold text-gray-800">{editingId !== null ? "编辑BI部门维护规则" : "新增BI部门维护规则"}</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-gray-600">费用归属部门</label>
                {editingId !== null ? (
                  <input className="w-full rounded border border-gray-300 bg-gray-100 px-2 py-1.5 text-xs" value={form.manage_department} disabled />
                ) : (
                  <div className="space-y-2">
                    <select
                      className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs"
                      value={useCustomManageDepartment ? OTHER_MANAGE_DEPARTMENT_OPTION : form.manage_department}
                      onChange={(e) => {
                        if (e.target.value === OTHER_MANAGE_DEPARTMENT_OPTION) {
                          setUseCustomManageDepartment(true);
                          setForm((prev) => ({ ...prev, manage_department: "" }));
                        } else {
                          setUseCustomManageDepartment(false);
                          setCustomManageDepartment("");
                          setForm((prev) => ({ ...prev, manage_department: e.target.value }));
                        }
                      }}
                    >
                      <option value="">-- 请选择费用归属部门 --</option>
                      {sortedManageDepartments.map((department) => (
                        <option key={department} value={department}>
                          {department}
                        </option>
                      ))}
                      <option value={OTHER_MANAGE_DEPARTMENT_OPTION}>其他（手动输入）</option>
                    </select>
                    {useCustomManageDepartment ? (
                      <input
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs"
                        value={customManageDepartment}
                        onChange={(e) => setCustomManageDepartment(e.target.value)}
                        placeholder="请输入其他费用归属部门"
                      />
                    ) : null}
                  </div>
                )}
              </div>
              <div ref={ownerDeptDropdownRef}>
                <label className="mb-1 block text-xs text-gray-600">归口部门</label>
                <button
                  type="button"
                  onClick={() => setOwnerDeptDropdownOpen((prev) => !prev)}
                  className="flex w-full items-center justify-between rounded border border-gray-300 bg-white px-2 py-1.5 text-left text-xs hover:bg-gray-50"
                >
                  <span className={`truncate ${form.owner_department || customOwnerDepartment ? "text-gray-800" : "text-gray-500"}`}>
                    {useCustomOwnerDepartment ? customOwnerDepartment || "其他（请填写）" : form.owner_department || "-- 请选择归口部门 --"}
                  </span>
                  <ChevronDown className={`h-3.5 w-3.5 text-gray-400 transition-transform ${ownerDeptDropdownOpen ? "rotate-180" : ""}`} />
                </button>
                <div className="mt-1 text-[11px] text-gray-500">按主体-事业群-归口部门展示，支持模糊查询。</div>
                {ownerDeptDropdownOpen ? (
                  <div className="mt-2 max-h-[320px] overflow-y-auto rounded border border-gray-300 bg-white shadow-sm">
                    <div className="sticky top-0 border-b bg-white px-2 py-2">
                      <div className="relative">
                        <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-gray-400" />
                        <input className="w-full rounded border border-gray-200 py-1 pl-7 pr-2 text-xs" placeholder="搜索主体/事业群/归口部门" value={ownerDeptSearch} onChange={(e) => setOwnerDeptSearch(e.target.value)} />
                      </div>
                    </div>
                    {showOtherOwnerDepartment ? (
                      <div>
                        <div className="bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">其他</div>
                        <button
                          type="button"
                          className={`flex w-full items-center gap-2 py-1 pl-6 pr-2 text-left text-xs hover:bg-blue-50 ${
                            useCustomOwnerDepartment ? "bg-blue-50 text-blue-700" : "text-gray-600"
                          }`}
                          onClick={() => {
                            setUseCustomOwnerDepartment(true);
                            setForm((prev) => ({ ...prev, owner_department: "" }));
                            setOwnerDeptDropdownOpen(false);
                            setOwnerDeptSearch("");
                          }}
                        >
                          <span className="truncate">{OTHER_OWNER_DEPARTMENT_LABEL}</span>
                          {useCustomOwnerDepartment ? <Check className="ml-auto h-3.5 w-3.5 shrink-0 text-blue-600" /> : null}
                        </button>
                      </div>
                    ) : null}
                    {filteredOwnerDeptGroups.map((entity) => (
                      <div key={entity.entity_name}>
                        <div className="bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{entity.entity_name}</div>
                        {entity.groups.map((group) => (
                          <div key={`${entity.entity_name}-${group.group_name}`}>
                            <div className="bg-gray-50 px-2 py-1 text-xs font-medium text-gray-700">{group.group_name}</div>
                            {group.departments.map((department) => {
                              const selected = department === form.owner_department;
                              return (
                                <button
                                  key={department}
                                  type="button"
                                  className={`flex w-full items-center gap-2 py-1 pl-6 pr-2 text-left text-xs hover:bg-blue-50 ${selected ? "bg-blue-50 text-blue-700" : "text-gray-600"}`}
                                  onClick={() => {
                                    setUseCustomOwnerDepartment(false);
                                    setCustomOwnerDepartment("");
                                    setForm((prev) => ({ ...prev, owner_department: department }));
                                    setOwnerDeptDropdownOpen(false);
                                    setOwnerDeptSearch("");
                                  }}
                                >
                                  <span className="truncate">{department}</span>
                                  {selected ? <Check className="ml-auto h-3.5 w-3.5 shrink-0 text-blue-600" /> : null}
                                </button>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    ))}
                    {filteredOwnerDeptGroups.length === 0 && !showOtherOwnerDepartment ? <div className="px-3 py-4 text-xs text-gray-400">未找到匹配的归口部门</div> : null}
                  </div>
                ) : null}
                {useCustomOwnerDepartment ? (
                  <input
                    className="mt-2 w-full rounded border border-gray-300 px-2 py-1.5 text-xs"
                    value={customOwnerDepartment}
                    onChange={(e) => setCustomOwnerDepartment(e.target.value)}
                    placeholder="请输入其他归口部门"
                  />
                ) : null}
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={resetDialog} className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50">
                取消
              </button>
              <button onClick={() => void handleSave()} className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700">
                {editingId !== null ? "保存" : "创建"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
