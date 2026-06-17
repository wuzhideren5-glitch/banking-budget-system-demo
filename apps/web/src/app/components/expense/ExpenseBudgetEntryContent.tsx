import { useEffect, useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, RefreshCw, Search, Trash2, Upload, X } from "lucide-react";
import {
  applyExpenseBudgetEntry,
  deleteExpenseBudgetEntryBatch,
  downloadExpenseBudgetEntryTemplate,
  exportExpenseBudgetEntryPreview,
  listExpenseBudgetEntryBatches,
  listExpenseBudgetEntryRows,
  previewExpenseBudgetEntry,
  updateExpenseBudgetEntryRow,
  type ExpenseBudgetEntryBatchRowDto,
  type ExpenseBudgetEntryPreviewResponseDto,
  type ExpenseBudgetEntryRowDto,
} from "@/lib/expense/expenseBudgetEntryApi";
import {
  EXPENSE_BUDGET_AMOUNT_UNITS,
  amountUnitLabel,
  formatDisplayAmount,
  formatDisplayAmountInput,
  toBaseAmount,
  type ExpenseBudgetAmountUnit,
} from "@/lib/expense/expenseBudgetEntryUnits";

type ImportMode = "append" | "overwrite";

const BUDGET_YEAR = 2026;

const previewHeaders = ["部门", "预算科目", "预算金额", "匹配部门", "匹配科目", "匹配状态", "说明"] as const;

function previewAmountHeader(unit: ExpenseBudgetAmountUnit): string {
  return `预算金额（${amountUnitLabel(unit)}）`;
}

function isMatchedSavedRow(row: ExpenseBudgetEntryRowDto): boolean {
  return row.match_status === "已匹配";
}

function SavedBudgetRowsTable({
  rows,
  displayUnit,
  emptyMessage,
  tone = "default",
  isLoading,
  isRefreshing,
  onUpdateRowAmount,
}: {
  rows: ExpenseBudgetEntryRowDto[];
  displayUnit: ExpenseBudgetAmountUnit;
  emptyMessage: string;
  tone?: "default" | "amber";
  isLoading: boolean;
  isRefreshing: boolean;
  onUpdateRowAmount: (rowId: number, field: "amount" | "adjustment_amount", value: number) => Promise<void>;
}) {
  const borderClass = tone === "amber" ? "border-amber-200" : "border-gray-200";
  const headClass = tone === "amber" ? "bg-amber-50" : "bg-gray-50";
  const rowClass = tone === "amber" ? "bg-amber-50/60" : "";

  return (
    <div className="overflow-auto max-h-[min(28rem,50vh)]">
      <table className={`min-w-[920px] w-full text-xs border ${borderClass}`}>
        <thead className={headClass}>
          <tr>
            <th className={`border ${borderClass} px-2 py-1.5`}>部门</th>
            <th className={`border ${borderClass} px-2 py-1.5`}>预算科目</th>
            <th className={`border ${borderClass} px-2 py-1.5 text-right`}>预算金额（{amountUnitLabel(displayUnit)}）</th>
            <th className={`border ${borderClass} px-2 py-1.5 text-right`}>预算调整金额（{amountUnitLabel(displayUnit)}）</th>
            <th className={`border ${borderClass} px-2 py-1.5 text-right`}>预算调整后金额（{amountUnitLabel(displayUnit)}）</th>
            <th className={`border ${borderClass} px-2 py-1.5`}>匹配状态</th>
            <th className={`border ${borderClass} px-2 py-1.5`}>说明</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={7} className={`border ${borderClass} px-2 py-4 text-center text-gray-500`}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id} className={rowClass}>
                <td className={`border ${borderClass} px-2 py-1`}>{row.owner_name_mapped ?? row.owner_name_raw}</td>
                <td className={`border ${borderClass} px-2 py-1`}>{row.budget_subject_mapped ?? row.budget_subject_raw}</td>
                <td className={`border ${borderClass} px-2 py-1 text-right`}>
                  <EditableAmountInput
                    value={row.amount}
                    unit={displayUnit}
                    disabled={isLoading || isRefreshing}
                    onCommit={(value) => onUpdateRowAmount(row.id, "amount", value)}
                  />
                </td>
                <td className={`border ${borderClass} px-2 py-1 text-right`}>
                  <EditableAmountInput
                    value={row.adjustment_amount}
                    unit={displayUnit}
                    disabled={isLoading || isRefreshing}
                    onCommit={(value) => onUpdateRowAmount(row.id, "adjustment_amount", value)}
                  />
                </td>
                <td className={`border ${borderClass} px-2 py-1 text-right font-medium`}>
                  {formatDisplayAmount(row.adjusted_amount ?? row.amount ?? 0, displayUnit)}
                </td>
                <td className={`border ${borderClass} px-2 py-1`}>{row.match_status}</td>
                <td className={`border ${borderClass} px-2 py-1`}>{row.match_note ?? "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function matchesSavedRowKeyword(row: ExpenseBudgetEntryRowDto, keyword: string): boolean {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) return true;
  const ownerText = (row.owner_name_mapped ?? row.owner_name_raw ?? "").toLowerCase();
  const subjectText = (row.budget_subject_mapped ?? row.budget_subject_raw ?? "").toLowerCase();
  return ownerText.includes(normalized) || subjectText.includes(normalized);
}

function parseAmountInput(raw: string): number | null {
  const normalized = raw.replace(/,/g, "").trim();
  if (!normalized) return 0;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

function EditableAmountInput({
  value,
  unit,
  disabled,
  onCommit,
}: {
  value: number;
  unit: ExpenseBudgetAmountUnit;
  disabled?: boolean;
  onCommit: (baseValue: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState(formatDisplayAmountInput(value, unit));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(formatDisplayAmountInput(value, unit));
  }, [value, unit]);

  const commit = async () => {
    const parsed = parseAmountInput(draft);
    if (parsed === null) {
      alert("请输入有效数字");
      setDraft(formatDisplayAmountInput(value, unit));
      return;
    }
    const baseValue = toBaseAmount(parsed, unit);
    if (baseValue === value) return;
    setSaving(true);
    try {
      await onCommit(baseValue);
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败");
      setDraft(formatDisplayAmountInput(value, unit));
    } finally {
      setSaving(false);
    }
  };

  return (
    <input
      className="bb-input w-28 text-right text-xs"
      value={draft}
      disabled={disabled || saving}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => void commit()}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
    />
  );
}

export function ExpenseBudgetEntryContent() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<ExpenseBudgetEntryPreviewResponseDto | null>(null);
  const [batches, setBatches] = useState<ExpenseBudgetEntryBatchRowDto[]>([]);
  const [savedRows, setSavedRows] = useState<ExpenseBudgetEntryRowDto[]>([]);
  const [mode, setMode] = useState<ImportMode>("append");
  const [importUnit, setImportUnit] = useState<ExpenseBudgetAmountUnit | "">("ten_thousand");
  const [displayUnit, setDisplayUnit] = useState<ExpenseBudgetAmountUnit>("yuan");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [savedRowsKeyword, setSavedRowsKeyword] = useState("");
  const [loadError, setLoadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileInputId = useId();

  const filteredMatchedSavedRows = useMemo(
    () => savedRows.filter((row) => isMatchedSavedRow(row) && matchesSavedRowKeyword(row, savedRowsKeyword)),
    [savedRows, savedRowsKeyword],
  );

  const filteredUnmatchedSavedRows = useMemo(
    () => savedRows.filter((row) => !isMatchedSavedRow(row) && matchesSavedRowKeyword(row, savedRowsKeyword)),
    [savedRows, savedRowsKeyword],
  );

  const matchedSavedCount = useMemo(() => savedRows.filter(isMatchedSavedRow).length, [savedRows]);
  const unmatchedSavedCount = useMemo(() => savedRows.filter((row) => !isMatchedSavedRow(row)).length, [savedRows]);

  const loadData = async () => {
    try {
      const batchData = await listExpenseBudgetEntryBatches(BUDGET_YEAR);
      setBatches(batchData);
      setSavedRows(await listExpenseBudgetEntryRows(BUDGET_YEAR));
      setLoadError("");
    } catch (e) {
      const message = e instanceof Error ? e.message : "未知错误";
      const detail =
        message.includes("Not Found") || message.includes("404")
          ? `${message}（后端可能未重启，请在项目根目录执行 bash stop.sh && bash start.sh 后等待约 30 秒再刷新）`
          : message;
      setLoadError(detail);
      throw new Error(detail);
    }
  };

  useEffect(() => {
    loadData().catch(() => {
      // loadError 已在 loadData 中设置，页面内展示即可
    });
  }, []);

  const resetFileState = () => {
    setSelectedFile(null);
    setPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileSelect = async (file: File) => {
    if (!importUnit) {
      alert("导入前请先选择金额单位。");
      return;
    }
    if (!file.name.match(/\.(xls|xlsx|xlsm)$/i)) {
      alert("请选择 Excel 文件（.xls、.xlsx 或 .xlsm）");
      return;
    }
    setSelectedFile(file);
    setIsLoading(true);
    try {
      setPreview(await previewExpenseBudgetEntry(file, BUDGET_YEAR, importUnit));
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入预览失败");
      resetFileState();
    } finally {
      setIsLoading(false);
    }
  };

  const handleImportUnitChange = async (nextUnit: ExpenseBudgetAmountUnit) => {
    setImportUnit(nextUnit);
    if (!selectedFile) return;
    setIsLoading(true);
    try {
      setPreview(await previewExpenseBudgetEntry(selectedFile, BUDGET_YEAR, nextUnit));
    } catch (e) {
      alert(e instanceof Error ? e.message : "切换单位后预览失败");
      setPreview(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplyImport = async () => {
    if (!importUnit) {
      alert("导入前请先选择金额单位。");
      return;
    }
    if (!selectedFile || !preview) {
      alert("请先选择导入文件并完成匹配预览。");
      return;
    }
    const actionText = mode === "overwrite" ? "覆盖录入" : "追加录入";
    if (preview.matched_rows === 0) {
      alert("没有可导入的已匹配预算行，请修正 Excel 中未匹配的部门或预算科目后再试。");
      return;
    }
    const summary = [
      `文件共 ${preview.row_count} 行，将导入已匹配 ${preview.matched_rows} 行。`,
      preview.unmatched_rows > 0 ? `未匹配的 ${preview.unmatched_rows} 行不会导入，请见下方列表。` : "",
      "",
      `是否确认${actionText}？`,
      "请选择「确定」执行录入，或「取消」放弃录入。",
    ]
      .filter(Boolean)
      .join("\n");
    if (!confirm(summary)) return;
    setIsLoading(true);
    try {
      const payload = await applyExpenseBudgetEntry(selectedFile, BUDGET_YEAR, mode, importUnit);
      await loadData();
      alert(
        `预算录入完成：已导入 ${payload.row_count} 行${
          payload.unmatched_rows > 0 ? `，未导入 ${payload.unmatched_rows} 行（未匹配）` : ""
        }。`
      );
      resetFileState();
    } catch (e) {
      alert(e instanceof Error ? e.message : "录入失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelImport = () => {
    resetFileState();
  };

  const handleExportPreview = async () => {
    if (!importUnit) {
      alert("导出前请先选择金额单位。");
      return;
    }
    if (!selectedFile || !preview) {
      alert("请先选择导入文件并完成匹配预览。");
      return;
    }
    setIsExporting(true);
    try {
      await exportExpenseBudgetEntryPreview(selectedFile, BUDGET_YEAR, importUnit);
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    } finally {
      setIsExporting(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await loadData();
    } catch (e) {
      alert(e instanceof Error ? e.message : "刷新失败");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleUpdateRowAmount = async (
    rowId: number,
    field: "amount" | "adjustment_amount",
    value: number,
  ) => {
    const updated = await updateExpenseBudgetEntryRow(rowId, { [field]: value });
    setSavedRows((rows) => rows.map((row) => (row.id === rowId ? updated : row)));
  };

  const handleDeleteBatch = async (batch: ExpenseBudgetEntryBatchRowDto) => {
    if (!confirm(`确认删除导入批次 ${batch.id}（${batch.file_name}）吗？`)) return;
    setIsLoading(true);
    try {
      await deleteExpenseBudgetEntryBatch(batch.id);
      await loadData();
      alert("导入批次已删除。");
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bb-page bb-page-scroll">
      <div className="bb-page-header flex flex-wrap items-start justify-between gap-3 shrink-0">
        <div className="min-w-0 flex-1">
          <h3 className="bb-page-title">预算录入</h3>
          <p className="bb-page-subtitle max-w-4xl">
            通过 Excel 导入部门费用预算（部门、预算科目、预算金额三列）。导入前请选择 Excel 金额单位；仅已匹配行会入库，未匹配行在预览区展示。录入后可手工修改预算金额与调整金额。
          </p>
        </div>
        <button
          type="button"
          className="bb-btn-secondary text-xs shrink-0"
          disabled={isLoading || isRefreshing}
          onClick={() => void handleRefresh()}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      {loadError && (
        <div className="bb-panel p-3 mt-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded">
          加载预算录入数据失败：{loadError}
        </div>
      )}

      <div className="bb-panel shrink-0">
        <div className="bb-panel-header">
          <div className="bb-panel-title">Excel 导入</div>
          <button
            type="button"
            className="bb-btn-secondary text-xs shrink-0"
            onClick={() => downloadExpenseBudgetEntryTemplate().catch((e) => alert(e.message))}
          >
            <Download className="w-3.5 h-3.5" />
            下载模板
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="bb-toolbar flex-col items-stretch gap-3 !items-start">
              <div className="text-xs font-medium text-[var(--bb-text-strong)]">导入模式</div>
              <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-1.5 text-xs text-[var(--bb-text)]">
                  <input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />
                  追加导入
                </label>
                <label className="flex items-center gap-1.5 text-xs text-[var(--bb-text)]">
                  <input type="radio" checked={mode === "overwrite"} onChange={() => setMode("overwrite")} />
                  覆盖导入
                </label>
              </div>
              <p className="text-[11px] leading-relaxed text-[var(--bb-text-muted)]">
                覆盖导入会清空当前年度已有预算录入后再写入。
              </p>
            </div>
            <div className="bb-toolbar flex-col items-stretch gap-3 !items-start">
              <div className="text-xs font-medium text-[var(--bb-text-strong)]">导入单位（必填）</div>
              <select
                className="bb-input text-xs w-full max-w-xs"
                value={importUnit}
                onChange={(e) => {
                  const value = e.target.value as ExpenseBudgetAmountUnit | "";
                  if (!value) {
                    setImportUnit("");
                    return;
                  }
                  void handleImportUnitChange(value);
                }}
              >
                <option value="">请选择单位</option>
                {EXPENSE_BUDGET_AMOUNT_UNITS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              {!importUnit && (
                <span className="text-[11px] text-amber-700">选择单位后才可上传 Excel。</span>
              )}
            </div>
          </div>

        <div
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            isDragging ? "border-blue-400 bg-blue-50" : "border-gray-300 bg-gray-50"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer.files[0];
            if (file) void handleFileSelect(file);
          }}
        >
          <FileSpreadsheet className="w-10 h-10 mx-auto text-gray-400 mb-3" />
          <p className="text-sm text-gray-600 mb-2">拖拽 Excel 文件到此处，或点击选择文件</p>
          <p className="text-xs text-gray-500 mb-4">模板列：部门、预算科目、预算金额</p>
          <input
            id={fileInputId}
            ref={fileInputRef}
            type="file"
            accept=".xls,.xlsx,.xlsm"
            className="sr-only"
            disabled={isLoading || !importUnit}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFileSelect(file);
              e.currentTarget.value = "";
            }}
          />
          <label
            htmlFor={isLoading || !importUnit ? undefined : fileInputId}
            className={`bb-btn-primary text-xs inline-flex items-center gap-1.5 ${
              isLoading || !importUnit ? "opacity-50 cursor-not-allowed pointer-events-none" : "cursor-pointer"
            }`}
          >
            <Upload className="w-3.5 h-3.5" />
            选择文件
          </label>
        </div>

        {selectedFile && !preview && isLoading && (
          <p className="mt-3 text-xs text-gray-500">正在解析文件并匹配部门、预算科目…</p>
        )}
        {selectedFile && preview && (
          <p className="text-xs text-gray-600">已选择：{selectedFile.name}</p>
        )}
        </div>
      </div>

      {preview && (
        <div className="bb-panel shrink-0">
          <div className="bb-panel-header">
            <div className="bb-panel-title">匹配预览</div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="bb-btn-secondary text-xs"
                disabled={isLoading || isExporting}
                onClick={() => void handleExportPreview()}
              >
                <Download className="w-3.5 h-3.5" />
                {isExporting ? "导出中…" : "匹配后导出"}
              </button>
              <button
                type="button"
                className="bb-btn-primary text-xs"
                disabled={isLoading || preview.matched_rows === 0}
                onClick={() => void handleApplyImport()}
              >
                {isLoading ? "录入中…" : "录入"}
              </button>
              <button
                type="button"
                className="bb-btn-secondary text-xs"
                disabled={isLoading}
                onClick={handleCancelImport}
              >
                取消录入
              </button>
            </div>
          </div>
          <div className="p-4 space-y-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
              <span className="font-medium">共 {preview.row_count} 行</span>
              <span className="text-green-700 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                已匹配 {preview.matched_rows} 行
              </span>
              <span className="text-amber-700 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                未匹配 {preview.unmatched_rows} 行（不导入）
              </span>
              <span className="text-[11px] text-[var(--bb-text-muted)]">
                导入模式：{mode === "overwrite" ? "覆盖录入" : "追加录入"}；导入单位：
                {amountUnitLabel(importUnit || (preview.amount_unit as ExpenseBudgetAmountUnit))}
              </span>
            </div>
            {preview.unmatched_rows > 0 && (
              <p className="text-[11px] text-amber-700">
                未匹配行不会导入，请修正 Excel 或在框架中维护映射后重新上传。
              </p>
            )}
            {preview.matched_rows === 0 && (
              <p className="text-[11px] text-red-700">当前文件没有可导入的已匹配行。</p>
            )}
            <div className="overflow-auto max-h-[min(24rem,45vh)]">
              <table className="min-w-[880px] w-full text-xs border border-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  {previewHeaders.map((header) => (
                    <th key={header} className="border border-gray-200 px-2 py-1.5 text-left whitespace-nowrap">
                      {header === "预算金额"
                        ? previewAmountHeader((importUnit || preview.amount_unit) as ExpenseBudgetAmountUnit)
                        : header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.preview_rows.length === 0 ? (
                  <tr>
                    <td colSpan={previewHeaders.length} className="border border-gray-200 px-2 py-4 text-center text-gray-500">
                      没有已匹配的预算行
                    </td>
                  </tr>
                ) : (
                  preview.preview_rows.map((row, idx) => (
                    <tr key={`${row.owner_name_raw}-${row.budget_subject_raw}-${idx}`}>
                      <td className="border border-gray-200 px-2 py-1">{row.owner_name_raw}</td>
                      <td className="border border-gray-200 px-2 py-1">{row.budget_subject_raw}</td>
                      <td className="border border-gray-200 px-2 py-1 text-right">
                        {formatDisplayAmount(row.amount, (importUnit || preview.amount_unit) as ExpenseBudgetAmountUnit)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1">{row.owner_name_mapped ?? "—"}</td>
                      <td className="border border-gray-200 px-2 py-1">{row.budget_subject_mapped ?? "—"}</td>
                      <td className="border border-gray-200 px-2 py-1">{row.match_status}</td>
                      <td className="border border-gray-200 px-2 py-1">{row.match_note ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {preview.unmatched_preview_rows.length > 0 && (
            <div>
              <h5 className="text-sm font-medium text-amber-800 mb-2 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                未导入的预算行（{preview.unmatched_rows} 行）
              </h5>
              <div className="overflow-auto max-h-[min(20rem,40vh)]">
                <table className="min-w-[880px] w-full text-xs border border-amber-200">
                  <thead className="bg-amber-50">
                    <tr>
                      {previewHeaders.map((header) => (
                        <th key={`unmatched-${header}`} className="border border-amber-200 px-2 py-1.5 text-left whitespace-nowrap">
                          {header === "预算金额"
                            ? previewAmountHeader((importUnit || preview.amount_unit) as ExpenseBudgetAmountUnit)
                            : header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.unmatched_preview_rows.map((row, idx) => (
                      <tr key={`unmatched-${row.owner_name_raw}-${row.budget_subject_raw}-${idx}`} className="bg-amber-50/60">
                        <td className="border border-amber-200 px-2 py-1">{row.owner_name_raw}</td>
                        <td className="border border-amber-200 px-2 py-1">{row.budget_subject_raw}</td>
                        <td className="border border-amber-200 px-2 py-1 text-right">
                          {formatDisplayAmount(row.amount, (importUnit || preview.amount_unit) as ExpenseBudgetAmountUnit)}
                        </td>
                        <td className="border border-amber-200 px-2 py-1">{row.owner_name_mapped ?? "—"}</td>
                        <td className="border border-amber-200 px-2 py-1">{row.budget_subject_mapped ?? "—"}</td>
                        <td className="border border-amber-200 px-2 py-1">{row.match_status}</td>
                        <td className="border border-amber-200 px-2 py-1">{row.match_note ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          </div>
        </div>
      )}

      <div className="bb-panel shrink-0">
        <div className="bb-panel-header">
          <div className="bb-panel-title">导入批次（{BUDGET_YEAR} 年）</div>
        </div>
        <div className="p-4 overflow-auto">
          <table className="min-w-[720px] w-full text-xs border border-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="border border-gray-200 px-2 py-1.5">批次</th>
                <th className="border border-gray-200 px-2 py-1.5">文件名</th>
                <th className="border border-gray-200 px-2 py-1.5">模式</th>
                <th className="border border-gray-200 px-2 py-1.5 text-right">总行数</th>
                <th className="border border-gray-200 px-2 py-1.5 text-right">已匹配</th>
                <th className="border border-gray-200 px-2 py-1.5">导入时间</th>
                <th className="border border-gray-200 px-2 py-1.5">操作</th>
              </tr>
            </thead>
            <tbody>
              {batches.length === 0 ? (
                <tr>
                  <td colSpan={7} className="border border-gray-200 px-2 py-4 text-center text-gray-500">
                    暂无导入批次
                  </td>
                </tr>
              ) : (
                batches.map((batch) => (
                  <tr key={batch.id}>
                    <td className="border border-gray-200 px-2 py-1">{batch.id}</td>
                    <td className="border border-gray-200 px-2 py-1">{batch.file_name}</td>
                    <td className="border border-gray-200 px-2 py-1">{batch.import_mode === "overwrite" ? "覆盖" : "追加"}</td>
                    <td className="border border-gray-200 px-2 py-1 text-right">{batch.total_rows}</td>
                    <td className="border border-gray-200 px-2 py-1 text-right">{batch.matched_rows}</td>
                    <td className="border border-gray-200 px-2 py-1">{batch.created_at}</td>
                    <td className="border border-gray-200 px-2 py-1">
                      <button type="button" className="text-red-600 hover:underline" onClick={() => void handleDeleteBatch(batch)}>
                        <Trash2 className="w-3.5 h-3.5 inline" />
                        删除
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bb-panel shrink-0">
        <div className="bb-panel-header">
          <div className="bb-panel-title">本年度已录入预算</div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-[var(--bb-text-strong)]">显示单位</span>
            <select
              className="bb-input text-xs"
              value={displayUnit}
              onChange={(e) => setDisplayUnit(e.target.value as ExpenseBudgetAmountUnit)}
            >
              {EXPENSE_BUDGET_AMOUNT_UNITS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <div className="relative w-52">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                className="bb-input w-full pl-8 pr-8 text-xs"
                value={savedRowsKeyword}
                onChange={(e) => setSavedRowsKeyword(e.target.value)}
                placeholder="搜索部门或预算科目"
              />
              {savedRowsKeyword && (
                <button
                  type="button"
                  className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 text-gray-500 hover:text-gray-700"
                  onClick={() => setSavedRowsKeyword("")}
                  aria-label="清空搜索"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>
        <div className="p-4 space-y-6">
          <h5 className="text-sm font-medium text-gray-800 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-700" />
            已匹配及导入预算表
            {savedRowsKeyword.trim()
              ? `（${filteredMatchedSavedRows.length} / ${matchedSavedCount} 条）`
              : `（${matchedSavedCount} 条）`}
          </h5>
          <SavedBudgetRowsTable
            rows={filteredMatchedSavedRows}
            displayUnit={displayUnit}
            emptyMessage={
              savedRows.length === 0
                ? "暂无已匹配及导入的预算数据"
                : savedRowsKeyword.trim()
                  ? "未找到匹配的部门或预算科目"
                  : "暂无已匹配及导入的预算数据"
            }
            isLoading={isLoading}
            isRefreshing={isRefreshing}
            onUpdateRowAmount={handleUpdateRowAmount}
          />
        </div>

        <div className="space-y-2">
          <h5 className="text-sm font-medium text-amber-800 flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5" />
            未匹配及未导入预算表
            {savedRowsKeyword.trim()
              ? `（${filteredUnmatchedSavedRows.length} / ${unmatchedSavedCount} 条）`
              : `（${unmatchedSavedCount} 条）`}
          </h5>
          <p className="text-[11px] text-amber-700">未匹配行不参与费用预算执行报表取数，可在此查看、编辑并留痕。</p>
          <SavedBudgetRowsTable
            rows={filteredUnmatchedSavedRows}
            displayUnit={displayUnit}
            tone="amber"
            emptyMessage={
              savedRows.length === 0
                ? "暂无未匹配及未导入的预算数据"
                : savedRowsKeyword.trim()
                  ? "未找到匹配的部门或预算科目"
                  : "暂无未匹配及未导入的预算数据"
            }
            isLoading={isLoading}
            isRefreshing={isRefreshing}
            onUpdateRowAmount={handleUpdateRowAmount}
          />
        </div>
      </div>
    </div>
  );
}
