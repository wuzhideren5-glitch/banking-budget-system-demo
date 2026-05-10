import { useMemo, useRef, useState } from "react";
import { X, Upload, Download, FileSpreadsheet, CheckCircle, AlertCircle } from "lucide-react";
import { buildApiUrl } from "@/lib/api";

interface FieldMapping {
  excelColumn: string;
  systemField: string;
  fieldName: string;
}

interface ExcelUploadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  fields: { key: string; label: string; required?: boolean }[];
  templateName?: string;
  previewEndpoint?: string;
  importEndpoint?: string;
  onImportComplete?: () => void;
}

type PreviewResponse = {
  columns: string[];
  preview_rows: Record<string, string>[];
  row_count: number;
};

export function ExcelUploadDialog({
  isOpen,
  onClose,
  title,
  fields,
  templateName,
  previewEndpoint = "/api/data-accounts/import-preview",
  importEndpoint = "/api/data-accounts/import-apply",
  onImportComplete,
}: ExcelUploadDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [excelData, setExcelData] = useState<Record<string, string>[]>([]);
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>([]);
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const systemFieldDefaults = useMemo(
    () => ({
      code: "数据科目代码",
      name: "数据科目名称",
      budgetFormula: "预算数计算公式",
      actualFormula: "实际数计算公式",
      product: "产品科目代码",
      valueType: "数值类型",
      remark: "备注",
      level1Code: "第1级报告科目代码",
      level1Name: "第1级报告科目名称",
      level2Code: "第2级报告科目代码",
      level2Name: "第2级报告科目名称",
      level3Code: "第3级报告科目代码",
      level3Name: "第3级报告科目名称",
      level4Code: "第4级报告科目代码",
      level4Name: "第4级报告科目名称",
      level5Code: "第5级报告科目代码",
      level5Name: "第5级报告科目名称",
      dataCode: "数据科目代码",
      dataName: "数据科目名称",
      isSummary: "是否汇总",
      isMinus: "是否减项",
      productCode: "产品科目代码",
      productName: "产品科目名称",
    }),
    []
  );

  if (!isOpen) return null;

  const handleClose = () => {
    resetDialog();
    onClose();
  };

  const handleDownloadTemplate = async () => {
    if (!templateName) {
      alert("未配置模板名称，无法下载。");
      return;
    }
    const proceed = confirm(
      "即将下载模板文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n如果你在浏览器中配置了其它下载路径，将保存到你配置的位置。\n\n是否继续下载？"
    );
    if (!proceed) return;
    try {
      const response = await fetch(buildApiUrl(`/api/templates/${encodeURIComponent(templateName)}`));
      if (!response.ok) throw new Error((await response.text()) || "模板下载失败");
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") ?? "";
      const nameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      const fileName = nameMatch?.[1] || `${templateName}.xlsx`;
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

  const autoMapFields = (columns: string[]) => {
    const mapped = fields.map((field) => {
      const preferred = systemFieldDefaults[field.key as keyof typeof systemFieldDefaults] ?? field.label;
      const exact = columns.find((c) => c.trim() === preferred);
      const fuzzy = columns.find((c) => c.includes(preferred) || preferred.includes(c));
      return {
        excelColumn: exact ?? fuzzy ?? "",
        systemField: field.key,
        fieldName: field.label,
      };
    });
    setFieldMappings(mapped);
  };

  const resetDialog = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setExcelData([]);
    setFieldMappings([]);
    setImportSummary(null);
    setIsLoading(false);
  };

  const handleFileSelect = async (file: File) => {
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      alert("请选择Excel文件（.xlsx 或 .xls）");
      return;
    }
    setIsLoading(true);
    setSelectedFile(file);
    setImportSummary(null);
    setUploadProgress(20);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(buildApiUrl(previewEndpoint), { method: "POST", body: form });
      if (!resp.ok) {
        const msg = (await resp.text()) || "上传文件解析失败";
        throw new Error(msg);
      }
      const payload = (await resp.json()) as PreviewResponse;
      setUploadProgress(100);
      setExcelData(payload.preview_rows);
      autoMapFields(payload.columns);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "上传文件解析失败";
      alert(msg);
      resetDialog();
      if (msg.includes("缺失“数据模版”工作表")) {
        handleClose();
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;
    const mappingObj = fieldMappings.reduce<Record<string, string>>((acc, m) => {
      if (m.excelColumn) acc[m.systemField] = m.excelColumn;
      return acc;
    }, {});
    const requiredMissing = fields.filter((f) => f.required && !mappingObj[f.key]).map((f) => f.label);
    if (requiredMissing.length > 0) {
      alert(`请先完成必填字段映射：${requiredMissing.join("、")}`);
      return;
    }

    setIsLoading(true);
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("mappings_json", JSON.stringify(mappingObj));
      const resp = await fetch(buildApiUrl(importEndpoint), {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        throw new Error((await resp.text()) || "导入失败");
      }
      const total = Number(resp.headers.get("X-Import-Total") ?? "0");
      const success = Number(resp.headers.get("X-Import-Success") ?? "0");
      const overwrite = Number(resp.headers.get("X-Import-Overwrite") ?? "0");
      const failed = Number(resp.headers.get("X-Import-Failed") ?? "0");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "data_account_import_result.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);

      const summary = `本次共处理 ${total} 条，成功上传 ${success} 条，其中覆盖原记录 ${overwrite} 条，失败 ${failed} 条。\n结果文件中：红色行为未上传（最右侧“失败原因”列可查看原因），蓝色行为覆盖上传，绿色行为新增成功上传。`;
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

  const handleFieldMappingChange = (systemField: string, excelColumn: string) => {
    setFieldMappings((prev) =>
      prev.map((m) => (m.systemField === systemField ? { ...m, excelColumn } : m))
    );
  };

  const columns = Object.keys(excelData[0] || {});

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[90vw] h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">{title} - Excel导入</h3>
          <button onClick={handleClose} className="p-1 hover:bg-gray-200 rounded transition-colors">
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-medium text-gray-700">第一步：上传Excel文件</h4>
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
                accept=".xlsx,.xls"
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
                  <p className="text-xs text-gray-400">支持 .xlsx 和 .xls 格式</p>
                </div>
              )}
            </div>
          </div>

          {excelData.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-700 mb-2">第二步：字段映射</h4>
              <div className="border border-gray-300 rounded overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-700 border-r border-gray-300">系统字段</th>
                      <th className="px-3 py-2 text-left text-gray-700">Excel列名</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {fieldMappings.map((mapping) => {
                      const field = fields.find((f) => f.key === mapping.systemField);
                      return (
                        <tr key={mapping.systemField} className="border-t border-gray-200">
                          <td className="px-3 py-2 border-r border-gray-200">
                            <span className="text-gray-700">{mapping.fieldName}</span>
                            {field?.required && <span className="text-red-500 ml-1">*</span>}
                          </td>
                          <td className="px-3 py-2">
                            <select
                              value={mapping.excelColumn}
                              onChange={(e) => handleFieldMappingChange(mapping.systemField, e.target.value)}
                              className="w-full px-2 py-1 border border-gray-300 rounded text-xs"
                            >
                              <option value="">-- 请选择 --</option>
                              {columns.map((col) => (
                                <option key={col} value={col}>
                                  {col}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {excelData.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-700 mb-2">第三步：数据预览（前20行）</h4>
              <div className="border border-gray-300 rounded overflow-auto max-h-56">
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
                {isLoading ? "导入中..." : "开始导入"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
