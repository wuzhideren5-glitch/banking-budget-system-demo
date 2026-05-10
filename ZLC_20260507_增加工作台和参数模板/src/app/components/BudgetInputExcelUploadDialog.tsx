import { useRef, useState } from "react";
import { AlertCircle, CheckCircle, Download, FileSpreadsheet, Upload, X } from "lucide-react";
import { buildApiUrl } from "@/lib/api";

type PreviewResponse = {
  columns: string[];
  preview_rows: Record<string, string>[];
  row_count: number;
};

interface BudgetInputExcelUploadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  versionId: number | null;
  onImportComplete?: () => void;
}

export function BudgetInputExcelUploadDialog({
  isOpen,
  onClose,
  versionId,
  onImportComplete,
}: BudgetInputExcelUploadDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [excelData, setExcelData] = useState<Record<string, string>[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const resetDialog = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setExcelData([]);
    setIsLoading(false);
    setImportSummary(null);
  };

  const handleClose = () => {
    resetDialog();
    onClose();
  };

  const handleDownloadTemplate = async () => {
    const proceed = confirm(
      "即将下载模板文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n是否继续下载？"
    );
    if (!proceed) return;
    try {
      const response = await fetch(buildApiUrl("/api/templates/budget_data_temp"));
      if (!response.ok) throw new Error((await response.text()) || "模板下载失败");
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") ?? "";
      const nameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      const fileName = nameMatch?.[1] || "budget_data_temp.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "模板下载失败");
    }
  };

  const handleFileSelect = async (file: File) => {
    if (!file.name.match(/\.(xlsx|xlsm)$/i)) {
      alert("请选择Excel文件（.xlsx 或 .xlsm）");
      return;
    }
    setIsLoading(true);
    setSelectedFile(file);
    setImportSummary(null);
    setUploadProgress(20);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(buildApiUrl("/api/budget-input/import-preview"), { method: "POST", body: form });
      if (!resp.ok) throw new Error((await resp.text()) || "上传文件解析失败");
      const payload = (await resp.json()) as PreviewResponse;
      setUploadProgress(100);
      setExcelData(payload.preview_rows);
    } catch (e) {
      alert(e instanceof Error ? e.message : "上传文件解析失败");
      resetDialog();
    } finally {
      setIsLoading(false);
    }
  };

  const handleImport = async () => {
    if (!selectedFile || !versionId) {
      alert("当前编辑版本无效，请先确认系统设定中的编辑版本。");
      return;
    }
    setIsLoading(true);
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      const resp = await fetch(
        buildApiUrl(`/api/budget-input/import-apply?version_id=${encodeURIComponent(String(versionId))}`),
        {
          method: "POST",
          body: form,
        }
      );
      if (!resp.ok) throw new Error((await resp.text()) || "导入失败");

      const total = Number(resp.headers.get("X-Import-Total") ?? "0");
      const success = Number(resp.headers.get("X-Import-Success") ?? "0");
      const overwrite = Number(resp.headers.get("X-Import-Overwrite") ?? "0");
      const failed = Number(resp.headers.get("X-Import-Failed") ?? "0");

      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "budget_input_import_result.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);

      const summary = `本次共处理 ${total} 个有值单元格，成功上传 ${success} 个，其中覆盖原记录 ${overwrite} 个，失败 ${failed} 个。\n结果文件中：红色为未上传，蓝色为覆盖上传，绿色为新增上传。`;
      setImportSummary(summary);
      alert(summary);
      await onImportComplete?.();
      handleClose();
    } catch (e) {
      alert(e instanceof Error ? e.message : "导入失败");
    } finally {
      setIsLoading(false);
    }
  };

  const columns = Object.keys(excelData[0] || {});

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[90vw] h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">预算基础数据输入 - Excel导入</h3>
          <button onClick={handleClose} className="p-1 hover:bg-gray-200 rounded transition-colors">
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-medium text-gray-700">第一步：下载模板并上传Excel文件</h4>
              <button
                onClick={() => void handleDownloadTemplate()}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                <Download className="w-3 h-3" />
                下载模板
              </button>
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
                accept=".xlsx,.xlsm"
                onChange={(e) => e.target.files?.[0] && void handleFileSelect(e.target.files[0])}
                className="hidden"
              />
              {selectedFile ? (
                <div className="flex flex-col items-center gap-2">
                  <FileSpreadsheet className="w-8 h-8 text-green-600" />
                  <p className="text-xs text-gray-700 font-medium">{selectedFile.name}</p>
                  {uploadProgress < 100 ? (
                    <p className="text-xs text-gray-500">解析中... {uploadProgress}%</p>
                  ) : (
                    <p className="text-xs text-green-600 flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" />
                      上传完成
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="w-8 h-8 text-gray-400" />
                  <p className="text-xs text-gray-600">
                    拖拽Excel文件到此处，或
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-blue-600 hover:underline ml-1"
                    >
                      点击选择文件
                    </button>
                  </p>
                  <p className="text-xs text-gray-400">支持 .xlsx 和 .xlsm 格式</p>
                </div>
              )}
            </div>
          </div>

          {excelData.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-700 mb-2">第二步：上传前预览（前20行）</h4>
              <div className="border border-gray-300 rounded overflow-auto max-h-72">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      {columns.map((key) => (
                        <th key={key} className="px-3 py-2 text-left text-gray-700 border border-gray-300">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {excelData.map((row, idx) => (
                      <tr key={idx} className="border-t border-gray-200">
                        {columns.map((col) => (
                          <td key={`${idx}-${col}`} className="px-3 py-2 border border-gray-300 text-gray-700">
                            {row[col] || "-"}
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

        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {importSummary && (
              <span className="flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {importSummary}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClose}
              className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 transition-colors"
            >
              关闭
            </button>
            {excelData.length > 0 && (
              <button
                onClick={() => void handleImport()}
                disabled={isLoading}
                className={`px-3 py-1.5 text-xs text-white rounded transition-colors ${
                  isLoading ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                {isLoading ? "导入中..." : "开始导入并下载结果"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
