import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, RefreshCw, Search, Trash2, Upload, X } from "lucide-react";
import {
  applyExpenseActualImport,
  deleteExpenseActualImportBatch,
  exportExpenseActualImportBatch,
  listExpenseActualImportBatches,
  previewExpenseActualImport,
  type ExpenseActualImportBatchRowDto,
  type ExpenseActualImportKind,
  type ExpenseActualImportPreviewResponseDto,
} from "@/lib/expense/expenseActualImportApi";
import {
  expenseActualImportKindLabel,
  expenseActualImportKindOptions,
  expenseActualPreviewColumns,
  expenseActualUnmatchedPreviewColumns,
  formatExpenseActualPreviewCell,
} from "@/lib/expense/expenseActualImportViewModel";

type ImportMode = "append" | "overwrite";

type ExpenseActualImportContentProps = {
  fixedImportKind?: ExpenseActualImportKind;
  pageTitle?: string;
  pageSubtitle?: string;
};

export function ExpenseActualImportContent({
  fixedImportKind,
  pageTitle = "费用执行明细导入",
  pageSubtitle,
}: ExpenseActualImportContentProps = {}) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<ExpenseActualImportPreviewResponseDto | null>(null);
  const [batches, setBatches] = useState<ExpenseActualImportBatchRowDto[]>([]);
  const [activeImportKind, setActiveImportKind] = useState<ExpenseActualImportKind>(fixedImportKind ?? "current_year_actual");
  const [mode, setMode] = useState<ImportMode>("append");
  const [batchSearch, setBatchSearch] = useState("");
  const [exportBatchId, setExportBatchId] = useState<number | "">("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const showImportKindSwitcher = !fixedImportKind;

  const loadBatches = async () => {
    const data = await listExpenseActualImportBatches(activeImportKind);
    setBatches(data);
    setExportBatchId((current) => {
      if (current && data.some((batch) => batch.id === current)) return current;
      return data[0]?.id ?? "";
    });
  };

  useEffect(() => {
    loadBatches().catch((e) => alert(`加载费用执行导入批次失败：${e.message}`));
  }, [activeImportKind]);

  const resetFileState = () => {
    setSelectedFile(null);
    setPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleImportKindChange = (importKind: ExpenseActualImportKind) => {
    if (fixedImportKind) return;
    if (importKind === activeImportKind) return;
    setActiveImportKind(importKind);
    setBatchSearch("");
    setExportBatchId("");
    resetFileState();
  };

  const handleFileSelect = async (file: File) => {
    if (!file.name.match(/\.(xls|xlsx)$/i)) {
      alert("请选择 Excel 文件（.xls 或 .xlsx）");
      return;
    }
    setSelectedFile(file);
    setIsLoading(true);
    try {
      setPreview(await previewExpenseActualImport(file, activeImportKind));
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入预览失败");
      resetFileState();
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplyImport = async () => {
    if (!selectedFile) {
      alert("请先选择导入文件。");
      return;
    }
    const actionText = mode === "overwrite" ? "按期间覆盖导入" : "追加导入";
    if (!confirm(`确认执行“${actionText}”吗？`)) return;
    setIsLoading(true);
    try {
      const payload = await applyExpenseActualImport(selectedFile, mode, activeImportKind);
      await loadBatches();
      const warningText =
        payload.manage_department_warnings?.length > 0
          ? `\n\n归口部门校验预警 ${payload.manage_department_warnings.length} 条：\n${payload.manage_department_warnings
              .slice(0, 5)
              .map((warning) => warning.message)
              .join("\n")}${payload.manage_department_warnings.length > 5 ? "\n..." : ""}`
          : "";
      alert(
        `${expenseActualImportKindLabel(activeImportKind)}完成：共 ${payload.row_count} 行，期间 ${payload.periods.join("、") || "未识别"}，校验预警 ${payload.unmatched_rows} 行。${warningText}`
      );
      resetFileState();
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteBatch = async (batch: ExpenseActualImportBatchRowDto) => {
    if (!confirm(`确认删除导入批次 ${batch.id}（${batch.file_name}）吗？该批次的导入明细会一并删除。`)) return;
    setIsLoading(true);
    try {
      await deleteExpenseActualImportBatch(batch.id);
      await loadBatches();
      alert("导入批次已删除。");
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除导入批次失败");
    } finally {
      setIsLoading(false);
    }
  };

  const visibleBatches = batches.filter((batch) => {
    const keyword = batchSearch.trim().toLowerCase();
    if (!keyword) return true;
    const text = [
      batch.file_name,
      expenseActualImportKindLabel(batch.import_kind),
      batch.import_mode,
      batch.periods.join(" "),
      batch.note ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(keyword);
  });

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">{pageTitle}</h3>
          <p className="bb-page-subtitle">
            {pageSubtitle ?? expenseActualImportKindOptions.find((option) => option.key === activeImportKind)?.description}
          </p>
        </div>
      </div>

      {showImportKindSwitcher ? (
        <div className="bb-panel p-2">
          <div className="flex flex-wrap gap-2">
            {expenseActualImportKindOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeImportKind === option.key ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
                onClick={() => handleImportKindChange(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="bb-panel p-4">
        <div className="flex items-center gap-4 mb-3">
          <div className="text-xs font-semibold text-[var(--bb-text-strong)]">{expenseActualImportKindLabel(activeImportKind)}</div>
          <div className="text-xs font-medium text-[var(--bb-text-strong)]">导入模式</div>
          <label className="flex items-center gap-1 text-xs text-[var(--bb-text)]">
            <input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />
            追加导入
          </label>
          <label className="flex items-center gap-1 text-xs text-[var(--bb-text)]">
            <input type="radio" checked={mode === "overwrite"} onChange={() => setMode("overwrite")} />
            按期间覆盖导入
          </label>
          <span className="text-[11px] text-[var(--bb-text-muted)]">
            覆盖导入会先删除当前模块中本次文件涉及期间的历史明细，再重新导入。
          </span>
          <div className="ml-auto flex items-center gap-2">
            <select
              className="bb-input min-w-64"
              value={exportBatchId}
              onChange={(e) => setExportBatchId(e.target.value ? Number(e.target.value) : "")}
              disabled={isLoading || batches.length === 0}
            >
              {batches.length === 0 ? (
                <option value="">当前模块暂无可导出的导入批次</option>
              ) : (
                batches.map((batch) => (
                  <option key={batch.id} value={batch.id}>
                    批次{batch.id} - {batch.file_name}
                  </option>
                ))
              )}
            </select>
            <button
              className="bb-btn bb-btn-secondary"
              onClick={() => {
                if (!exportBatchId) {
                  alert("请选择要导出的导入批次");
                  return;
                }
                void exportExpenseActualImportBatch(exportBatchId).catch((e) => alert(e instanceof Error ? e.message : "导出失败"));
              }}
              disabled={isLoading || !exportBatchId}
            >
              <Download className="w-3 h-3" />
              导出{expenseActualImportKindLabel(activeImportKind)}匹配文件
            </button>
          </div>
        </div>

        <div
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
          className={`rounded border border-dashed p-6 text-center transition-colors ${
            isDragging ? "border-[var(--bb-primary)] bg-[var(--bb-primary-soft)]" : "border-[var(--bb-border)] bg-[var(--bb-bg-subtle)]"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".xls,.xlsx"
            onChange={(e) => e.target.files?.[0] && void handleFileSelect(e.target.files[0])}
            className="hidden"
          />
          {selectedFile ? (
            <div className="flex flex-col items-center gap-2">
              <FileSpreadsheet className="w-8 h-8 text-[var(--bb-success)]" />
              <p className="text-xs font-medium text-[var(--bb-text-strong)]">{selectedFile.name}</p>
              <div className="flex items-center gap-2">
                <button
                  className="bb-btn bb-btn-primary"
                  onClick={() => void handleApplyImport()}
                  disabled={isLoading}
                >
                  {isLoading ? "处理中..." : "执行导入"}
                </button>
                <button
                  className="bb-btn bb-btn-secondary"
                  onClick={resetFileState}
                  disabled={isLoading}
                >
                  清空文件
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload className="w-8 h-8 text-[var(--bb-text-muted)]" />
              <p className="text-xs text-[var(--bb-text)]">拖拽或点击上传 `{expenseActualImportKindLabel(activeImportKind)}` Excel 文件（.xls/.xlsx）</p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="bb-btn bb-btn-primary"
              >
                选择文件
              </button>
            </div>
          )}
        </div>

        {preview && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-5 gap-3 text-xs">
              <SummaryCard label="明细行数" value={String(preview.row_count)} tone="blue" />
              <SummaryCard label="涉及期间" value={preview.periods.join("、") || "-"} tone="slate" />
              <SummaryCard label="归口管理部门已匹配" value={String(preview.matched_owner_rows)} tone="green" />
              <SummaryCard label="预算科目已匹配" value={String(preview.matched_subject_rows)} tone="green" />
              <SummaryCard label="校验预警" value={String(preview.unmatched_rows)} tone={preview.unmatched_rows > 0 ? "amber" : "green"} />
            </div>

            {preview.manage_department_warnings?.length > 0 && (
              <div className="bb-status-banner bb-status-banner-warning overflow-hidden p-0">
                <div className="px-3 py-2 border-b border-[#f0c36a] flex items-center gap-2 text-xs font-medium">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  归口部门校验预警（{preview.manage_department_warnings.length} 条）
                </div>
                <div className="overflow-auto">
                  <table className="bb-table bb-table-dense min-w-full">
                    <thead>
                      <tr>
                        {["期间", "导入归口部门", "预算发布口径", "BI映射归口部门", "说明"].map((header) => (
                          <th key={header}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.manage_department_warnings.slice(0, 20).map((warning, idx) => (
                        <tr key={`manage-warning-${idx}-${warning.period_ym}`}>
                          <td>{warning.period_ym || "-"}</td>
                          <td>{warning.import_manage_department || warning.owner_name_raw || "-"}</td>
                          <td>{warning.budget_release_caliber_mapped || warning.budget_subject_mapped || "-"}</td>
                          <td>{warning.mapping_manage_department || "-"}</td>
                          <td>{warning.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="bb-table-wrap">
              <div className="bb-panel-header">
                <span className="bb-panel-title">
                导入预览
                </span>
              </div>
              <div className="overflow-auto">
                <table className="bb-table bb-table-dense min-w-full">
                  <thead>
                    <tr>
                      {expenseActualPreviewColumns.map((column) => (
                        <th key={column.key}>
                          {column.header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview_rows.map((row, idx) => (
                      <tr key={`${row.period_ym}-${row.owner_name_raw}-${row.budget_subject_raw}-${idx}`}>
                        {expenseActualPreviewColumns.map((column) => (
                          <td key={column.key} className={column.numeric ? "bb-cell-number" : undefined}>
                            {formatExpenseActualPreviewCell(row, column)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {preview.unmatched_preview_rows.length > 0 && (
              <div className="bb-status-banner bb-status-banner-warning overflow-hidden p-0">
                <div className="px-3 py-2 border-b border-[#f0c36a] flex items-center gap-2 text-xs font-medium">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  未匹配预警预览
                </div>
                <div className="overflow-auto">
                  <table className="bb-table bb-table-dense min-w-full">
                    <thead>
                      <tr>
                        {expenseActualUnmatchedPreviewColumns.map((column) => (
                          <th key={column.key}>
                            {column.header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.unmatched_preview_rows.map((row, idx) => (
                        <tr key={`warn-${idx}-${row.period_ym}`}>
                          {expenseActualUnmatchedPreviewColumns.map((column) => (
                            <td key={column.key} className={column.numeric ? "bb-cell-number" : undefined}>
                              {formatExpenseActualPreviewCell(row, column)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="bb-panel flex-1 min-h-0 overflow-hidden">
        <div className="bb-panel-header">
          <span className="bb-panel-title">{expenseActualImportKindLabel(activeImportKind)}最近导入批次</span>
          <div className="flex-1" />
          <div className="relative w-56">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={batchSearch}
              onChange={(e) => setBatchSearch(e.target.value)}
              placeholder="搜索文件名/期间..."
                className="bb-input w-full pl-8 pr-8"
            />
            {batchSearch && (
              <button
                type="button"
                onClick={() => setBatchSearch("")}
                className="bb-icon-btn absolute right-1 top-1/2 -translate-y-1/2"
              >
                <X className="w-3.5 h-3.5 text-gray-500" />
              </button>
            )}
          </div>
          <button
            className="bb-btn bb-btn-secondary"
            onClick={() => void loadBatches()}
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>
        <div className="overflow-auto h-full">
          <table className="bb-table bb-table-dense min-w-full">
            <thead>
              <tr>
                {["批次ID", "文件名", "导入类型", "导入模式", "期间", "总行数", "部门匹配", "科目匹配", "未匹配", "导入时间", "说明", "操作"].map((header) => (
                  <th key={header}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleBatches.length === 0 ? (
                <tr>
                  <td colSpan={12} className="py-8 text-center text-[var(--bb-text-muted)]">
                    暂无导入批次记录。
                  </td>
                </tr>
              ) : (
                visibleBatches.map((batch) => (
                  <tr key={batch.id}>
                    <td>{batch.id}</td>
                    <td>{batch.file_name}</td>
                    <td>{expenseActualImportKindLabel(batch.import_kind)}</td>
                    <td>{batch.import_mode === "overwrite" ? "按期间覆盖" : "追加导入"}</td>
                    <td>{batch.periods.join("、") || "-"}</td>
                    <td className="bb-cell-number">{batch.total_rows}</td>
                    <td className="bb-cell-number">{batch.matched_owner_rows}</td>
                    <td className="bb-cell-number">{batch.matched_subject_rows}</td>
                    <td className="bb-cell-number">{batch.unmatched_rows}</td>
                    <td>{batch.created_at.replace("T", " ").replace("Z", "")}</td>
                    <td>{batch.note || "-"}</td>
                    <td>
                      <div className="flex items-center gap-1">
                        <button
                          className="bb-icon-btn"
                          title="导出匹配结果"
                          onClick={() => void exportExpenseActualImportBatch(batch.id).catch((e) => alert(e instanceof Error ? e.message : "导出失败"))}
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        <button
                          className="bb-icon-btn"
                          title="删除批次"
                          onClick={() => void handleDeleteBatch(batch)}
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "blue" | "green" | "amber" | "slate";
}) {
  const toneClass =
    tone === "green"
      ? "border-green-200 bg-green-50 text-green-900"
      : tone === "amber"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : tone === "blue"
          ? "border-blue-200 bg-blue-50 text-blue-900"
          : "border-slate-200 bg-slate-50 text-slate-800";
  return (
    <div className={`bb-stat-card ${toneClass}`}>
      <div className="text-[11px] opacity-80 mb-1">{label}</div>
      <div className="text-sm font-medium break-all flex items-center gap-1">
        {tone === "green" && <CheckCircle2 className="w-3.5 h-3.5" />}
        {value}
      </div>
    </div>
  );
}
