import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, RefreshCw, Search, Upload, X } from "lucide-react";
import {
  apiGet,
  buildApiUrl,
  type ExpenseActualImportApplyResponseDto,
  type ExpenseActualImportBatchRowDto,
  type ExpenseActualImportPreviewResponseDto,
} from "@/lib/api";

type ImportMode = "append" | "overwrite";

export function ExpenseActualImportContent() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [preview, setPreview] = useState<ExpenseActualImportPreviewResponseDto | null>(null);
  const [batches, setBatches] = useState<ExpenseActualImportBatchRowDto[]>([]);
  const [mode, setMode] = useState<ImportMode>("append");
  const [batchSearch, setBatchSearch] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadBatches = async () => {
    const data = await apiGet<ExpenseActualImportBatchRowDto[]>("/api/expense-actual-import/batches");
    setBatches(data);
  };

  useEffect(() => {
    loadBatches().catch((e) => alert(`加载费用执行导入批次失败：${e.message}`));
  }, []);

  const resetFileState = () => {
    setSelectedFile(null);
    setPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileSelect = async (file: File) => {
    if (!file.name.match(/\.(xls|xlsx)$/i)) {
      alert("请选择 Excel 文件（.xls 或 .xlsx）");
      return;
    }
    setSelectedFile(file);
    setIsLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(buildApiUrl("/api/expense-actual-import/import-preview"), {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导入预览失败");
      setPreview((await resp.json()) as ExpenseActualImportPreviewResponseDto);
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
      const form = new FormData();
      form.append("file", selectedFile);
      const resp = await fetch(buildApiUrl(`/api/expense-actual-import/import-apply?mode=${mode}`), {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导入失败");
      const payload = (await resp.json()) as ExpenseActualImportApplyResponseDto;
      await loadBatches();
      alert(
        `导入完成：共 ${payload.row_count} 行，期间 ${payload.periods.join("、") || "未识别"}，未匹配 ${payload.unmatched_rows} 行。`
      );
      resetFileState();
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入失败");
    } finally {
      setIsLoading(false);
    }
  };

  const visibleBatches = batches.filter((batch) => {
    const keyword = batchSearch.trim().toLowerCase();
    if (!keyword) return true;
    const text = [
      batch.file_name,
      batch.import_mode,
      batch.periods.join(" "),
      batch.note ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(keyword);
  });

  return (
    <div className="p-4 h-full flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">费用执行明细导入</h3>
        <span className="text-[11px] text-gray-500">
          导入预算系统中的“部门费用执行.xls”，原始明细入库并保留未匹配预警，后续供系统加工调阅。
        </span>
      </div>

      <div className="border border-gray-300 rounded bg-white p-4">
        <div className="flex items-center gap-4 mb-3">
          <div className="text-xs text-gray-700 font-medium">导入模式</div>
          <label className="flex items-center gap-1 text-xs text-gray-700">
            <input type="radio" checked={mode === "append"} onChange={() => setMode("append")} />
            追加导入
          </label>
          <label className="flex items-center gap-1 text-xs text-gray-700">
            <input type="radio" checked={mode === "overwrite"} onChange={() => setMode("overwrite")} />
            按期间覆盖导入
          </label>
          <span className="text-[11px] text-gray-500">
            覆盖导入会先删除本次文件涉及期间的历史实际明细，再重新导入。
          </span>
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
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-gray-50"
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
              <FileSpreadsheet className="w-8 h-8 text-green-600" />
              <p className="text-xs text-gray-700 font-medium">{selectedFile.name}</p>
              <div className="flex items-center gap-2">
                <button
                  className="px-3 py-1 text-xs rounded bg-[#3498db] text-white hover:bg-[#2980b9]"
                  onClick={() => void handleApplyImport()}
                  disabled={isLoading}
                >
                  {isLoading ? "处理中..." : "执行导入"}
                </button>
                <button
                  className="px-3 py-1 text-xs rounded bg-gray-200 text-gray-700 hover:bg-gray-300"
                  onClick={resetFileState}
                  disabled={isLoading}
                >
                  清空文件
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload className="w-8 h-8 text-gray-400" />
              <p className="text-xs text-gray-700">拖拽或点击上传 `部门费用执行.xls/.xlsx`</p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-3 py-1 text-xs rounded bg-[#3498db] text-white hover:bg-[#2980b9]"
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
              <SummaryCard label="费用归属部门已匹配" value={String(preview.matched_owner_rows)} tone="green" />
              <SummaryCard label="预算科目已匹配" value={String(preview.matched_subject_rows)} tone="green" />
              <SummaryCard label="未匹配预警" value={String(preview.unmatched_rows)} tone={preview.unmatched_rows > 0 ? "amber" : "green"} />
            </div>

            <div className="rounded border border-gray-200 overflow-hidden">
              <div className="px-3 py-2 bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-700">
                导入预览
              </div>
              <div className="overflow-auto">
                <table className="min-w-full text-xs border-collapse">
                  <thead className="bg-gray-100">
                    <tr>
                      {["期间", "费用归属部门", "映射后费用归属部门", "预算科目", "映射后预算科目", "金额", "匹配状态", "说明"].map((header) => (
                        <th key={header} className="border border-gray-200 px-2 py-1 text-left font-medium text-gray-700 whitespace-nowrap">
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview_rows.map((row, idx) => (
                      <tr key={`${row.period_ym}-${row.owner_name_raw}-${row.budget_subject_raw}-${idx}`}>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.period_ym}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.owner_name_raw}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.owner_name_mapped || "-"}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.budget_subject_raw}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.budget_subject_mapped || "-"}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.match_status}</td>
                        <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{row.match_note || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {preview.unmatched_preview_rows.length > 0 && (
              <div className="rounded border border-amber-300 bg-amber-50 overflow-hidden">
                <div className="px-3 py-2 border-b border-amber-300 flex items-center gap-2 text-xs font-medium text-amber-900">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  未匹配预警预览
                </div>
                <div className="overflow-auto">
                  <table className="min-w-full text-xs border-collapse">
                    <thead className="bg-amber-100">
                      <tr>
                        {["期间", "费用归属部门", "预算科目", "金额", "说明"].map((header) => (
                          <th key={header} className="border border-amber-200 px-2 py-1 text-left font-medium text-amber-900 whitespace-nowrap">
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.unmatched_preview_rows.map((row, idx) => (
                        <tr key={`warn-${idx}-${row.period_ym}`}>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.period_ym}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.owner_name_raw}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.budget_subject_raw}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.match_note || "-"}</td>
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

      <div className="border border-gray-300 rounded bg-white flex-1 min-h-0 overflow-hidden">
        <div className="px-3 py-2 bg-gray-100 border-b border-gray-300 flex items-center gap-2">
          <span className="text-xs font-medium text-gray-700">最近导入批次</span>
          <div className="flex-1" />
          <div className="relative w-56">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={batchSearch}
              onChange={(e) => setBatchSearch(e.target.value)}
              placeholder="搜索文件名/期间..."
              className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full"
            />
            {batchSearch && (
              <button
                type="button"
                onClick={() => setBatchSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
              >
                <X className="w-3.5 h-3.5 text-gray-500" />
              </button>
            )}
          </div>
          <button
            className="px-3 py-1 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50 flex items-center gap-1"
            onClick={() => void loadBatches()}
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>
        <div className="overflow-auto h-full">
          <table className="min-w-full text-xs border-collapse">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                {["批次ID", "文件名", "导入模式", "期间", "总行数", "部门匹配", "科目匹配", "未匹配", "导入时间", "说明"].map((header) => (
                  <th key={header} className="border border-gray-200 px-2 py-1 text-left font-medium text-gray-700 whitespace-nowrap">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleBatches.length === 0 ? (
                <tr>
                  <td colSpan={10} className="border border-gray-200 px-2 py-8 text-center text-gray-500">
                    暂无导入批次记录。
                  </td>
                </tr>
              ) : (
                visibleBatches.map((batch) => (
                  <tr key={batch.id}>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.id}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.file_name}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.import_mode === "overwrite" ? "按期间覆盖" : "追加导入"}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.periods.join("、") || "-"}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.total_rows}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.matched_owner_rows}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.matched_subject_rows}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.unmatched_rows}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.created_at.replace("T", " ").replace("Z", "")}</td>
                    <td className="border border-gray-200 px-2 py-1 whitespace-nowrap">{batch.note || "-"}</td>
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
    <div className={`rounded border p-3 ${toneClass}`}>
      <div className="text-[11px] opacity-80 mb-1">{label}</div>
      <div className="text-sm font-medium break-all flex items-center gap-1">
        {tone === "green" && <CheckCircle2 className="w-3.5 h-3.5" />}
        {value}
      </div>
    </div>
  );
}
