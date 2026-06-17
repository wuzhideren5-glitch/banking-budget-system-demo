import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { Pencil, Plus, RefreshCw, Search } from "lucide-react";
import {
  createBiAiSubjectMapping,
  getBiAiSubjectMappingReferenceData,
  listBiAiSubjectMappings,
  reloadBiAiSubjectMappings,
  updateBiAiSubjectMappingManageDepartments,
  type BiAiSubjectMappingCreateDto,
  type BiAiSubjectMappingDto,
} from "@/lib/business/biMappingApi";
import { BI_AI_SUBJECT_COLUMNS, filterBiAiSubjectMappings } from "@/lib/business/biMappingViewModel";

type ManageDepartmentEditorState = {
  rowId: number;
  selected: string[];
  anchorRect: DOMRect;
};

function ManageDepartmentCell({
  row,
  expenseDepartments,
  onUpdated,
}: {
  row: BiAiSubjectMappingDto;
  expenseDepartments: string[];
  onUpdated: (updated: BiAiSubjectMappingDto) => void;
}) {
  const [editor, setEditor] = useState<ManageDepartmentEditorState | null>(null);
  const [saving, setSaving] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const openEditor = (event: ReactMouseEvent<HTMLButtonElement>) => {
    setEditor({
      rowId: row.id,
      selected: [...(row.manage_departments ?? [])],
      anchorRect: event.currentTarget.getBoundingClientRect(),
    });
  };

  useEffect(() => {
    if (!editor) return;
    const onOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setEditor(null);
      }
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [editor]);

  const saveSelection = async (manageDepartments: string[] | null) => {
    setSaving(true);
    try {
      const updated = await updateBiAiSubjectMappingManageDepartments(row.id, manageDepartments);
      onUpdated(updated);
      setEditor(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存归口部门失败");
    } finally {
      setSaving(false);
    }
  };

  const sourceHint =
    row.manage_department_source === "override"
      ? "手动"
      : row.manage_department_source === "auto"
        ? "自动"
        : "默认全部";

  const panelStyle = editor
    ? {
        top: Math.min(editor.anchorRect.bottom + 4, window.innerHeight - 320),
        left: Math.min(editor.anchorRect.left, window.innerWidth - 280),
      }
    : undefined;

  return (
    <>
      <button
        type="button"
        className="group flex w-full items-start gap-1 text-left hover:text-blue-700"
        title={`${row.manage_department || "-"}（${sourceHint}，点击编辑）`}
        onClick={openEditor}
      >
        <span className="min-w-0 flex-1 break-words">{row.manage_department || "-"}</span>
        <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-gray-400 group-hover:text-blue-600" />
      </button>
      {editor && editor.rowId === row.id ? (
        <div
          ref={panelRef}
          className="fixed z-50 w-72 rounded border border-gray-300 bg-white p-2 shadow-lg"
          style={panelStyle}
        >
          <div className="mb-2 text-[11px] font-medium text-gray-700">选择归口部门（多选）</div>
          <div className="mb-2 flex flex-wrap gap-1">
            <button
              type="button"
              className="rounded border border-gray-300 px-1.5 py-0.5 text-[10px] hover:bg-gray-50"
              onClick={() => setEditor((prev) => (prev ? { ...prev, selected: [...expenseDepartments] } : prev))}
            >
              全选
            </button>
            <button
              type="button"
              className="rounded border border-gray-300 px-1.5 py-0.5 text-[10px] hover:bg-gray-50"
              onClick={() => setEditor((prev) => (prev ? { ...prev, selected: [] } : prev))}
            >
              清空
            </button>
            <button
              type="button"
              className="rounded border border-gray-300 px-1.5 py-0.5 text-[10px] hover:bg-gray-50"
              disabled={saving}
              onClick={() => void saveSelection(null)}
            >
              恢复默认
            </button>
          </div>
          <div className="max-h-48 space-y-1 overflow-y-auto border border-gray-100 p-1">
            {expenseDepartments.map((department) => {
              const checked = editor.selected.includes(department);
              return (
                <label key={department} className="flex items-center gap-1.5 text-[11px] text-gray-700">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      setEditor((prev) => {
                        if (!prev) return prev;
                        const next = event.target.checked
                          ? [...prev.selected, department]
                          : prev.selected.filter((item) => item !== department);
                        return { ...prev, selected: next };
                      });
                    }}
                  />
                  <span className="break-words">{department}</span>
                </label>
              );
            })}
            {expenseDepartments.length === 0 ? (
              <div className="py-2 text-center text-[11px] text-gray-400">部门科目维护暂无费用归属部门</div>
            ) : null}
          </div>
          <div className="mt-2 flex justify-end gap-1">
            <button
              type="button"
              className="rounded border border-gray-300 px-2 py-0.5 text-[11px] hover:bg-gray-50"
              onClick={() => setEditor(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded bg-blue-600 px-2 py-0.5 text-[11px] text-white hover:bg-blue-700 disabled:opacity-60"
              disabled={saving}
              onClick={() => void saveSelection(editor.selected)}
            >
              保存
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}

const emptyCreateForm: BiAiSubjectMappingCreateDto = {
  level5_code: "",
  level5_name: "",
  level6_code: "",
  level6_name: "",
  budget_release_caliber: "",
  fee_category: "",
  fee_major: "",
  manage_departments: null,
};

function CreateMappingDialog({
  expenseDepartments,
  onCancel,
  onCreated,
}: {
  expenseDepartments: string[];
  onCancel: () => void;
  onCreated: (row: BiAiSubjectMappingDto) => void;
}) {
  const [form, setForm] = useState<BiAiSubjectMappingCreateDto>(emptyCreateForm);
  const [selectedDepartments, setSelectedDepartments] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const updateField = (key: keyof Omit<BiAiSubjectMappingCreateDto, "manage_departments">, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    try {
      const created = await createBiAiSubjectMapping({
        ...form,
        manage_departments: selectedDepartments.length > 0 ? selectedDepartments : null,
      });
      onCreated(created);
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增BI-AI科目映射失败");
    } finally {
      setSaving(false);
    }
  };

  const fields: { key: keyof Omit<BiAiSubjectMappingCreateDto, "manage_departments">; label: string; required?: boolean }[] = [
    { key: "level5_code", label: "五级编码", required: true },
    { key: "level5_name", label: "五级名称", required: true },
    { key: "level6_code", label: "六级编码", required: true },
    { key: "level6_name", label: "六级名称", required: true },
    { key: "budget_release_caliber", label: "预算发布口径（二级）", required: true },
    { key: "fee_category", label: "费用类别（一级）" },
    { key: "fee_major", label: "费用大类" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-3xl rounded border border-gray-200 bg-white shadow-xl">
        <div className="border-b border-gray-200 px-4 py-3">
          <div className="text-sm font-semibold text-gray-900">新增BI-AI科目映射</div>
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-2">
          {fields.map((field) => (
            <label key={field.key} className="space-y-1 text-xs text-gray-700">
              <span>
                {field.label}
                {field.required ? <span className="text-red-500">*</span> : null}
              </span>
              <input
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs"
                value={form[field.key]}
                onChange={(event) => updateField(field.key, event.target.value)}
              />
            </label>
          ))}
          <div className="space-y-2 md:col-span-2">
            <div className="text-xs font-medium text-gray-700">归口部门</div>
            <div className="max-h-40 overflow-y-auto rounded border border-gray-200 p-2">
              {expenseDepartments.length === 0 ? (
                <div className="py-3 text-center text-xs text-gray-400">暂无费用归属部门</div>
              ) : (
                <div className="grid gap-1 md:grid-cols-3">
                  {expenseDepartments.map((department) => {
                    const checked = selectedDepartments.includes(department);
                    return (
                      <label key={department} className="flex items-center gap-1.5 text-xs text-gray-700">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => {
                            setSelectedDepartments((prev) =>
                              event.target.checked
                                ? [...prev, department]
                                : prev.filter((item) => item !== department)
                            );
                          }}
                        />
                        <span className="break-words">{department}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-gray-200 px-4 py-3">
          <button
            type="button"
            className="rounded border border-gray-300 px-3 py-1.5 text-xs hover:bg-gray-50"
            onClick={onCancel}
            disabled={saving}
          >
            取消
          </button>
          <button
            type="button"
            className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-60"
            onClick={() => void save()}
            disabled={saving}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

export function BiAiSubjectMappingTab() {
  const [rows, setRows] = useState<BiAiSubjectMappingDto[]>([]);
  const [expenseDepartments, setExpenseDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [keyword, setKeyword] = useState("");

  const loadRows = useCallback(async () => {
    setLoading(true);
    try {
      const [mappingRows, referenceData] = await Promise.all([
        listBiAiSubjectMappings(),
        getBiAiSubjectMappingReferenceData(),
      ]);
      setRows(mappingRows);
      setExpenseDepartments(referenceData.expense_departments);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRows().catch((e) => alert(`加载BI-AI科目映射失败：${e.message}`));
  }, [loadRows]);

  const filteredRows = useMemo(() => filterBiAiSubjectMappings(rows, keyword), [keyword, rows]);

  const handleRowUpdated = (updated: BiAiSubjectMappingDto) => {
    setRows((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
  };

  const handleRowCreated = (created: BiAiSubjectMappingDto) => {
    setRows((prev) => [...prev, created]);
    setCreateOpen(false);
  };

  const handleReload = async () => {
    setReloading(true);
    try {
      const result = await reloadBiAiSubjectMappings();
      await loadRows();
      alert(`已按 ${result.source_file} 重建BI-AI科目映射表，共 ${result.row_count} 条。`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "重建BI-AI科目映射失败");
    } finally {
      setReloading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-xs text-gray-600">
        <strong>说明：</strong>BI-AI科目映射表按 <span className="font-mono">BI科目匹配表.xlsx</span> 或
        <span className="font-mono"> BI科目mapping.xlsx</span> 重建。归口部门优先读取手动选择；否则按预算发布口径关联部门预算科目维护自动带出；仍为空时默认全部费用归属部门。
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-gray-400" />
          <input
            className="w-72 rounded border border-gray-300 py-1.5 pl-7 pr-2 text-xs"
            placeholder="搜索编码、名称、预算发布口径、归口部门"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>
        <button
          onClick={() => void loadRows().catch((e) => alert(e instanceof Error ? e.message : "刷新失败"))}
          className="flex items-center gap-1.5 rounded bg-gray-500 px-3 py-1.5 text-xs text-white hover:bg-gray-600"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700"
        >
          <Plus className="h-3.5 w-3.5" />
          新增
        </button>
        <button
          onClick={() => void handleReload()}
          disabled={reloading}
          className="flex items-center gap-1.5 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-60"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${reloading ? "animate-spin" : ""}`} />
          按Excel重建
        </button>
        <span className="text-xs text-gray-500">共 {rows.length} 条，当前显示 {filteredRows.length} 条</span>
      </div>

      {loading ? (
        <div className="py-8 text-center text-gray-400">加载中...</div>
      ) : (
        <div className="overflow-auto rounded border border-gray-200">
          <table className="min-w-[960px] w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-gray-100">
              <tr className="text-center text-gray-800">
                <th className="border border-gray-200 bg-blue-50 px-3 py-2 font-semibold" colSpan={4}>
                  BI原始科目
                </th>
                <th className="border border-gray-200 bg-green-50 px-3 py-2 font-semibold" colSpan={4}>
                  BI映射科目
                </th>
              </tr>
              <tr className="text-left text-gray-700">
                {BI_AI_SUBJECT_COLUMNS.map((column) => (
                  <th key={column.key} className="whitespace-nowrap border border-gray-200 px-3 py-2">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => (
                <tr key={row.id} className="hover:bg-gray-50">
                  {BI_AI_SUBJECT_COLUMNS.map((column) => (
                    <td key={column.key} className="whitespace-nowrap border border-gray-200 px-3 py-1.5 text-gray-700">
                      {column.key === "manage_department" ? (
                        <ManageDepartmentCell
                          row={row}
                          expenseDepartments={expenseDepartments}
                          onUpdated={handleRowUpdated}
                        />
                      ) : (
                        String(row[column.key] || "-")
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {filteredRows.length === 0 ? (
                <tr>
                  <td className="border border-gray-200 px-3 py-8 text-center text-gray-400" colSpan={BI_AI_SUBJECT_COLUMNS.length}>
                    暂无BI-AI科目映射数据
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}
      {createOpen ? (
        <CreateMappingDialog
          expenseDepartments={expenseDepartments}
          onCancel={() => setCreateOpen(false)}
          onCreated={handleRowCreated}
        />
      ) : null}
    </div>
  );
}
