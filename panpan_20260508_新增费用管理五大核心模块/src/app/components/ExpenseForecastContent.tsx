import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileUp,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  apiGet,
  apiPost,
  buildApiUrl,
  type ExpenseForecastCellUpsertRequestDto,
  type ExpenseForecastCellUpsertResponseDto,
  type ExpenseForecastImportApplyResponseDto,
  type ExpenseForecastImportPreviewResponseDto,
  type ExpenseForecastMetaResponseDto,
  type ExpenseForecastMonthCellDto,
  type ExpenseForecastOwnerGroupOptionDto,
  type ExpenseForecastRowDto,
  type ExpenseForecastScopeOptionDto,
  type ExpenseForecastViewResponseDto,
} from "@/lib/api";

type ScopeType = "entity" | "group" | "owner";
type ImportMode = "append" | "overwrite";

type EditingCell = {
  rowId: number;
  month: number;
};

type ContextMenuState = {
  x: number;
  y: number;
  rowId: number;
} | null;

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function parseNumberInput(raw: string): number {
  const parsed = Number.parseFloat(raw.replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function scopeLabel(scopeType: ScopeType): string {
  if (scopeType === "entity") return "主体";
  if (scopeType === "group") return "事业群";
  return "费用归属部门";
}

function suggestedScopeType(meta: ExpenseForecastMetaResponseDto | null): ScopeType {
  if (!meta) return "group";
  if (meta.group_options.length > 0) return "group";
  if (meta.entity_options.length > 0) return "entity";
  return "owner";
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function ExpenseForecastContent() {
  const [meta, setMeta] = useState<ExpenseForecastMetaResponseDto | null>(null);
  const [scopeType, setScopeType] = useState<ScopeType>("group");
  const [ownerGroupValue, setOwnerGroupValue] = useState("");
  const [scopeValue, setScopeValue] = useState("");
  const [year, setYear] = useState<number>(0);
  const [forecastVersion, setForecastVersion] = useState("");
  const [view, setView] = useState<ExpenseForecastViewResponseDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingCell, setSavingCell] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>("append");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importPreview, setImportPreview] = useState<ExpenseForecastImportPreviewResponseDto | null>(null);
  const [importResult, setImportResult] = useState<ExpenseForecastImportApplyResponseDto | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const loadMeta = async (targetYear?: number) => {
    const queryYear = targetYear ?? (year > 0 ? year : new Date().getFullYear());
    const resp = await apiGet<ExpenseForecastMetaResponseDto>(`/api/expense-forecast/meta?year=${queryYear}`);
    setMeta(resp);
    setYear(queryYear || resp.default_year);
    setForecastVersion((prev) => prev || resp.default_version);
    setScopeType((prev) => prev || suggestedScopeType(resp));
  };

  const scopeOptions = useMemo<ExpenseForecastScopeOptionDto[]>(() => {
    if (!meta) return [];
    if (scopeType === "entity") return meta.entity_options;
    if (scopeType === "group") return meta.group_options;
    const matchedGroup = (meta.owner_group_options ?? []).find((item) => item.group_value === ownerGroupValue);
    return matchedGroup?.owner_options ?? [];
  }, [meta, ownerGroupValue, scopeType]);

  const ownerGroupOptions = useMemo<ExpenseForecastOwnerGroupOptionDto[]>(() => {
    if (!meta || scopeType !== "owner") return [];
    return meta.owner_group_options ?? [];
  }, [meta, scopeType]);

  const currentScopeValueValid = useMemo(() => {
    if (!scopeValue) return false;
    return scopeOptions.some((item) => item.value === scopeValue);
  }, [scopeOptions, scopeValue]);
  const ownerEditableScope = scopeType === "owner";

  const rowMap = useMemo(() => {
    const map = new Map<number, ExpenseForecastRowDto>();
    for (const row of view?.rows ?? []) {
      map.set(row.id, row);
    }
    return map;
  }, [view]);

  const childrenByParent = useMemo(() => {
    const map = new Map<number | null, ExpenseForecastRowDto[]>();
    for (const row of view?.rows ?? []) {
      const parentId = row.parent_id ?? null;
      const list = map.get(parentId) ?? [];
      list.push(row);
      map.set(parentId, list);
    }
    return map;
  }, [view]);

  useEffect(() => {
    void (async () => {
      try {
        await loadMeta(new Date().getFullYear());
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载费用预测配置失败");
      }
    })();
  }, []);

  useEffect(() => {
    if (!meta) return;
    if (scopeType === "owner") {
      if (!ownerGroupOptions.length) {
        setOwnerGroupValue("");
        setScopeValue("");
        return;
      }
      if (!ownerGroupOptions.some((item) => item.group_value === ownerGroupValue)) {
        setOwnerGroupValue(ownerGroupOptions[0].group_value);
        return;
      }
    } else if (ownerGroupValue) {
      setOwnerGroupValue("");
    }

    const options =
      scopeType === "entity" ? meta.entity_options : scopeType === "group" ? meta.group_options : scopeOptions;
    if (!options.length) {
      setScopeValue("");
      return;
    }
    if (!options.some((item) => item.value === scopeValue)) {
      setScopeValue(options[0].value);
    }
  }, [meta, ownerGroupOptions, ownerGroupValue, scopeOptions, scopeType, scopeValue]);

  const loadView = async () => {
    if (!scopeValue || !currentScopeValueValid || !forecastVersion || !year) return;
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({
        year: String(year),
        forecast_version: forecastVersion,
        scope_type: scopeType,
        scope_value: scopeValue,
      });
      const resp = await apiGet<ExpenseForecastViewResponseDto>(`/api/expense-forecast/view?${query.toString()}`);
      setView(resp);
      setExpandedIds(new Set(resp.rows.map((row) => row.id)));
      if (!selectedRowId && resp.rows.length > 0) {
        setSelectedRowId(resp.rows[0].id);
      }
      setMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载费用预测表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!scopeValue || !currentScopeValueValid || !forecastVersion || !year) return;
    void loadView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeValue, scopeType, forecastVersion, year, currentScopeValueValid]);

  useEffect(() => {
    const closeMenu = () => setContextMenu(null);
    window.addEventListener("click", closeMenu);
    return () => window.removeEventListener("click", closeMenu);
  }, []);

  const matchedRowIds = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) return null;
    const matched = new Set<number>();
    for (const row of view?.rows ?? []) {
      if (row.subject_name.toLowerCase().includes(keyword)) {
        matched.add(row.id);
        let parentId = row.parent_id;
        while (parentId != null) {
          matched.add(parentId);
          parentId = rowMap.get(parentId)?.parent_id ?? null;
        }
      }
    }
    return matched;
  }, [searchText, view, rowMap]);

  const visibleRows = useMemo(() => {
    const result: ExpenseForecastRowDto[] = [];
    const walk = (parentId: number | null) => {
      for (const row of childrenByParent.get(parentId) ?? []) {
        const matched = matchedRowIds ? matchedRowIds.has(row.id) : true;
        if (matched) result.push(row);
        const shouldWalk = matchedRowIds ? matchedRowIds.has(row.id) : expandedIds.has(row.id);
        if (shouldWalk) {
          walk(row.id);
        }
      }
    };
    walk(null);
    return result;
  }, [childrenByParent, matchedRowIds, expandedIds]);

  const depthByRowId = useMemo(() => {
    const map = new Map<number, number>();
    const walk = (parentId: number | null, depth: number) => {
      for (const row of childrenByParent.get(parentId) ?? []) {
        map.set(row.id, depth);
        walk(row.id, depth + 1);
      }
    };
    walk(null, 0);
    return map;
  }, [childrenByParent]);

  const startEdit = (row: ExpenseForecastRowDto, cell: ExpenseForecastMonthCellDto) => {
    if (!cell.editable) return;
    setEditingCell({ rowId: row.id, month: cell.month });
    setDraftValue(String(cell.value || ""));
    setSelectedRowId(row.id);
  };

  const saveCell = async () => {
    if (!editingCell || !view) return;
    const row = rowMap.get(editingCell.rowId);
    if (!row) {
      setEditingCell(null);
      return;
    }
    const payload: ExpenseForecastCellUpsertRequestDto = {
      year,
      forecast_version: forecastVersion,
      scope_type: scopeType,
      scope_value: scopeValue,
      subject_id: row.id,
      month: editingCell.month,
      value: parseNumberInput(draftValue),
    };
    const savingKey = `${editingCell.rowId}:${editingCell.month}`;
    setSavingCell(savingKey);
    try {
      await apiPost<ExpenseForecastCellUpsertResponseDto>("/api/expense-forecast/cell", payload);
      setMessage(`已保存 ${row.subject_name} ${editingCell.month}月 预估值`);
      setError("");
      await loadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存预估失败");
    } finally {
      setSavingCell("");
      setEditingCell(null);
    }
  };

  const handleExport = async () => {
    try {
      setError("");
      const resp = await fetch(buildApiUrl("/api/expense-forecast/export"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          year,
          forecast_version: forecastVersion,
          scope_type: scopeType,
          scope_value: scopeValue,
        }),
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const disposition = resp.headers.get("Content-Disposition") ?? "";
      const match = /filename=\"?([^\";]+)\"?/i.exec(disposition);
      const fileName = match?.[1] ?? `费用预测表_${year}_${forecastVersion}.xlsx`;
      triggerDownload(await resp.blob(), fileName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  };

  const runImportPreview = async () => {
    if (!importFile) {
      setError("请先选择导入文件");
      return;
    }
    setImportLoading(true);
    setError("");
    setImportResult(null);
    try {
      const form = new FormData();
      form.append("file", importFile);
      const query = new URLSearchParams({
        year: String(year),
        forecast_version: forecastVersion,
        scope_type: scopeType,
        scope_value: scopeValue,
        mode: importMode,
      });
      const resp = await fetch(buildApiUrl(`/api/expense-forecast/import-preview?${query.toString()}`), {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导入预览失败");
      setImportPreview((await resp.json()) as ExpenseForecastImportPreviewResponseDto);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入预览失败");
    } finally {
      setImportLoading(false);
    }
  };

  const applyImport = async () => {
    if (!importFile) return;
    setImportLoading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", importFile);
      const query = new URLSearchParams({
        year: String(year),
        forecast_version: forecastVersion,
        scope_type: scopeType,
        scope_value: scopeValue,
        mode: importMode,
      });
      const resp = await fetch(buildApiUrl(`/api/expense-forecast/import-apply?${query.toString()}`), {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导入失败");
      const payload = (await resp.json()) as ExpenseForecastImportApplyResponseDto;
      setImportResult(payload);
      setMessage(`导入完成：新增 ${payload.inserted_cells}，覆盖 ${payload.updated_cells}，跳过 ${payload.skipped_cells}`);
      await loadMeta(year);
      await loadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setImportLoading(false);
    }
  };

  const currentContextRow = contextMenu ? rowMap.get(contextMenu.rowId) ?? null : null;

  return (
    <div className="h-full flex flex-col bg-white text-xs text-gray-700">
      <div className="border-b border-gray-200 px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">年份</span>
            <input
              className="h-8 w-24 rounded border border-gray-300 px-2"
              type="number"
              value={year || ""}
              onChange={(e) => setYear(Number.parseInt(e.target.value || "0", 10) || 0)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">版本</span>
            <input
              className="h-8 w-36 rounded border border-gray-300 px-2"
              value={forecastVersion}
              list="expense-forecast-versions"
              onChange={(e) => setForecastVersion(e.target.value)}
            />
            <datalist id="expense-forecast-versions">
              {(meta?.version_suggestions ?? []).map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">编制口径</span>
            <select
              className="h-8 w-32 rounded border border-gray-300 px-2"
              value={scopeType}
              onChange={(e) => setScopeType(e.target.value as ScopeType)}
            >
              <option value="entity">主体</option>
              <option value="group">事业群</option>
              <option value="owner">费用归属部门</option>
            </select>
          </label>
          {scopeType === "owner" ? (
            <label className="flex flex-col gap-1">
              <span className="text-gray-500">事业群</span>
              <select
                className="h-8 min-w-[180px] rounded border border-gray-300 px-2"
                value={ownerGroupValue}
                onChange={(e) => setOwnerGroupValue(e.target.value)}
              >
                {ownerGroupOptions.map((option) => (
                  <option key={option.group_value} value={option.group_value}>
                    {option.group_label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">{scopeLabel(scopeType)}</span>
            <select
              className="h-8 min-w-[220px] rounded border border-gray-300 px-2"
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
            >
              {scopeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">搜索预算科目</span>
            <div className="relative">
              <Search className="absolute left-2 top-2 h-4 w-4 text-gray-400" />
              <input
                className="h-8 w-52 rounded border border-gray-300 pl-8 pr-2"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </div>
          </label>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50"
            onClick={() => void loadView()}
            type="button"
          >
            <RefreshCw className={`mr-1 inline h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => setShowImportDialog(true)}
            type="button"
            disabled={!ownerEditableScope}
            title={ownerEditableScope ? "导入预估" : "仅费用归属部门口径支持导入预估"}
          >
            <FileUp className="mr-1 inline h-3.5 w-3.5" />
            导入预估
          </button>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50"
            onClick={() => void handleExport()}
            type="button"
          >
            <Download className="mr-1 inline h-3.5 w-3.5" />
            导出 Excel
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-gray-500">
          <span>当前口径：{scopeLabel(scopeType)}</span>
          <span>当前对象：{scopeValue || "-"}</span>
          <span>实际数据截至：{view?.actual_cutoff_month ?? 0}月</span>
          <span>
            说明：
            {ownerEditableScope
              ? "已有实际的月份显示实际，后续月份显示预估并支持编辑"
              : "当前口径仅作汇总展示，不支持录入预估"}
          </span>
        </div>
        {message ? <div className="text-emerald-600">{message}</div> : null}
        {error ? <div className="text-red-600">{error}</div> : null}
      </div>

      <div className="flex-1 overflow-auto">
        <table className="min-w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-[#f8fafc]">
            <tr>
              <th className="sticky left-0 z-20 min-w-[360px] border-b border-r border-gray-200 bg-[#f8fafc] px-3 py-2 text-left font-medium">
                预算科目
              </th>
              {Array.from({ length: 12 }, (_, idx) => idx + 1).map((month) => (
                <th key={month} className="min-w-[90px] border-b border-r border-gray-200 px-2 py-2 text-right font-medium">
                  {month}月
                </th>
              ))}
              <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">全年预测</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const depth = depthByRowId.get(row.id) ?? 0;
              const hasChildren = (childrenByParent.get(row.id)?.length ?? 0) > 0;
              const isExpanded = expandedIds.has(row.id);
              const isSelected = selectedRowId === row.id;
              return (
                <tr
                  key={row.id}
                  className={`${isSelected ? "bg-blue-50" : "odd:bg-white even:bg-gray-50"}`}
                  onClick={() => setSelectedRowId(row.id)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setSelectedRowId(row.id);
                    setContextMenu({ x: e.clientX, y: e.clientY, rowId: row.id });
                  }}
                >
                  <td className="sticky left-0 z-[1] border-b border-r border-gray-200 bg-inherit px-3 py-1.5">
                    <div className="flex items-center gap-1" style={{ paddingLeft: `${depth * 18}px` }}>
                      {hasChildren ? (
                        <button
                          type="button"
                          className="rounded p-0.5 hover:bg-gray-200"
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedIds((prev) => {
                              const next = new Set(prev);
                              if (next.has(row.id)) next.delete(row.id);
                              else next.add(row.id);
                              return next;
                            });
                          }}
                        >
                          {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        </button>
                      ) : (
                        <span className="inline-block w-4" />
                      )}
                      <span className={row.is_leaf ? "" : "font-medium text-gray-800"}>{row.subject_name}</span>
                      {row.formula_text ? <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-700">公式</span> : null}
                    </div>
                  </td>
                  {row.months.map((cell) => {
                    const isEditing = editingCell?.rowId === row.id && editingCell?.month === cell.month;
                    const cellKey = `${row.id}:${cell.month}`;
                    const readOnlyCell = cell.source === "actual" || !cell.editable;
                    return (
                      <td
                        key={cell.month}
                        className={`border-b border-r border-gray-200 px-2 py-1.5 text-right ${
                          readOnlyCell ? "bg-gray-100 text-gray-600" : "bg-white"
                        }`}
                        title={cell.source === "actual" ? "来源：实际，只读" : cell.editable ? "来源：预估，可编辑" : "汇总单元格，只读"}
                        onDoubleClick={() => startEdit(row, cell)}
                      >
                        {isEditing ? (
                          <input
                            autoFocus
                            className="h-7 w-full rounded border border-blue-300 px-1 text-right"
                            value={draftValue}
                            onChange={(e) => setDraftValue(e.target.value)}
                            onBlur={() => void saveCell()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                void saveCell();
                              }
                              if (e.key === "Escape") {
                                setEditingCell(null);
                              }
                            }}
                          />
                        ) : (
                          <button
                            type="button"
                            className={`w-full text-right ${cell.editable ? "hover:text-blue-600" : ""}`}
                            onClick={() => startEdit(row, cell)}
                            disabled={!cell.editable}
                          >
                            {savingCell === cellKey ? "保存中..." : formatNumber(cell.value)}
                          </button>
                        )}
                      </td>
                    );
                  })}
                  <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">{formatNumber(row.total_value)}</td>
                </tr>
              );
            })}
            {!loading && visibleRows.length === 0 ? (
              <tr>
                <td colSpan={14} className="px-3 py-10 text-center text-gray-400">
                  当前没有可展示的数据
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {contextMenu && currentContextRow ? (
        <div
          className="fixed z-50 min-w-[160px] rounded border border-gray-200 bg-white py-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds((prev) => new Set(prev).add(currentContextRow.id));
              setContextMenu(null);
            }}
          >
            展开下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds((prev) => {
                const next = new Set(prev);
                next.delete(currentContextRow.id);
                return next;
              });
              setContextMenu(null);
            }}
          >
            收起本级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds(new Set(view?.rows.map((row) => row.id) ?? []));
              setContextMenu(null);
            }}
          >
            展开全部下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds(new Set());
              setContextMenu(null);
            }}
          >
            收起全部下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setSelectedRowId(currentContextRow.id);
              setContextMenu(null);
            }}
          >
            定位当前科目
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              void loadView();
              setContextMenu(null);
            }}
          >
            刷新当前视图
          </button>
        </div>
      ) : null}

      {showImportDialog ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/25 px-4">
          <div className="flex h-[80vh] w-[920px] flex-col overflow-hidden rounded bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-gray-800">导入费用预测预估</div>
                <div className="mt-1 text-[11px] text-gray-500">
                  当前口径：{scopeLabel(scopeType)} / {scopeValue} / 版本 {forecastVersion}
                </div>
              </div>
              <button type="button" className="rounded p-1 hover:bg-gray-100" onClick={() => setShowImportDialog(false)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-4 overflow-auto px-4 py-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">导入模式</span>
                  <select
                    className="h-8 w-32 rounded border border-gray-300 px-2"
                    value={importMode}
                    onChange={(e) => setImportMode(e.target.value as ImportMode)}
                  >
                    <option value="append">追加</option>
                    <option value="overwrite">覆盖</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">导入文件</span>
                  <input
                    ref={fileInputRef}
                    className="block h-8 rounded border border-gray-300 px-2 py-1"
                    type="file"
                    accept=".xlsx"
                    onChange={(e) => {
                      setImportFile(e.target.files?.[0] ?? null);
                      setImportPreview(null);
                      setImportResult(null);
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50"
                  disabled={importLoading}
                  onClick={() => void runImportPreview()}
                >
                  {importLoading ? "解析中..." : "预览导入"}
                </button>
                <button
                  type="button"
                  className="h-8 rounded border border-blue-500 bg-blue-500 px-3 text-white hover:bg-blue-600 disabled:opacity-60"
                  disabled={importLoading || !importPreview}
                  onClick={() => void applyImport()}
                >
                  应用导入
                </button>
              </div>
              {!ownerEditableScope ? (
                <div className="rounded border border-amber-200 bg-amber-50 p-3 text-amber-700">
                  当前为{scopeLabel(scopeType)}口径，仅支持汇总展示；费用预估仅可在“费用归属部门”口径下录入或导入。
                </div>
              ) : null}

              {importPreview ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-4 gap-3">
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <div className="text-gray-500">可新增</div>
                      <div className="mt-1 text-sm font-medium">{importPreview.insertable_cells}</div>
                    </div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <div className="text-gray-500">可覆盖</div>
                      <div className="mt-1 text-sm font-medium">{importPreview.updatable_cells}</div>
                    </div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <div className="text-gray-500">跳过</div>
                      <div className="mt-1 text-sm font-medium">{importPreview.skipped_cells}</div>
                    </div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <div className="text-gray-500">错误</div>
                      <div className="mt-1 text-sm font-medium">{importPreview.error_cells}</div>
                    </div>
                  </div>
                  <div className="max-h-[380px] overflow-auto rounded border border-gray-200">
                    <table className="min-w-full border-collapse">
                      <thead className="sticky top-0 bg-gray-50">
                        <tr>
                          <th className="border-b border-r border-gray-200 px-2 py-2 text-left">行号</th>
                          <th className="border-b border-r border-gray-200 px-2 py-2 text-left">预算科目</th>
                          <th className="border-b border-r border-gray-200 px-2 py-2 text-left">月份</th>
                          <th className="border-b border-r border-gray-200 px-2 py-2 text-right">值</th>
                          <th className="border-b border-r border-gray-200 px-2 py-2 text-left">动作</th>
                          <th className="border-b border-gray-200 px-2 py-2 text-left">说明</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importPreview.items.map((item, idx) => (
                          <tr key={`${item.row_number}-${item.budget_subject}-${item.month}-${idx}`} className="odd:bg-white even:bg-gray-50">
                            <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.row_number}</td>
                            <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.budget_subject}</td>
                            <td className="border-b border-r border-gray-200 px-2 py-1.5">M{item.month}</td>
                            <td className="border-b border-r border-gray-200 px-2 py-1.5 text-right">{formatNumber(item.value)}</td>
                            <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.action}</td>
                            <td className="border-b border-gray-200 px-2 py-1.5">{item.message ?? "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {importResult ? (
                <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-emerald-700">
                  导入完成：新增 {importResult.inserted_cells}，覆盖 {importResult.updated_cells}，跳过 {importResult.skipped_cells}，错误{" "}
                  {importResult.error_cells}。
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
