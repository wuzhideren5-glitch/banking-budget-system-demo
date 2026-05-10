import { useState, useRef } from "react";
import { X, Upload, Download, FileSpreadsheet, CheckCircle, XCircle, AlertCircle } from "lucide-react";

interface FieldMapping {
  excelColumn: string;
  systemField: string;
  fieldName: string;
}

interface ImportRow {
  status: 'success' | 'error';
  errorMessage?: string;
  data: Record<string, string>;
}

interface ExcelUploadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  fields: { key: string; label: string; required?: boolean }[];
  templateData?: Record<string, string>[];
  onImport: (data: any[]) => void;
}

export function ExcelUploadDialog({
  isOpen,
  onClose,
  title,
  fields,
  templateData = [],
  onImport
}: ExcelUploadDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [excelData, setExcelData] = useState<any[]>([]);
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>([]);
  const [importResults, setImportResults] = useState<ImportRow[]>([]);
  const [showResults, setShowResults] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleFileSelect = (file: File) => {
    if (!file.name.match(/\.(xlsx|xls)$/)) {
      alert("请选择Excel文件（.xlsx 或 .xls）");
      return;
    }

    setSelectedFile(file);
    setUploadProgress(0);

    // 模拟文件读取和解析
    setTimeout(() => {
      setUploadProgress(30);
      setTimeout(() => {
        setUploadProgress(70);
        // 模拟解析Excel数据
        const mockData = [
          { "科目代码": "X2001", "科目名称": "负债类", "预算数计算公式": "SUM(X2002:X2003)", "实际数计算公式": "SUM(X2002:X2003)", "产品科目": "Z0001-个人住房贷款", "数值类型": "金额", "备注": "" },
          { "科目代码": "X2002", "科目名称": "流动负债", "预算数计算公式": "", "实际数计算公式": "", "产品科目": "Z0002-企业流动资金贷款", "数值类型": "金额", "备注": "短期负债" },
          { "科目代码": "X2003", "科目名称": "长期负债", "预算数计算公式": "", "实际数计算公式": "", "产品科目": "", "数值类型": "金额", "备注": "缺少产品科目" },
          { "科目代码": "", "科目名称": "所有者权益", "预算数计算公式": "", "实际数计算公式": "", "产品科目": "Z0003-结构性存款", "数值类型": "金额", "备注": "缺少科目代码" },
        ];
        setExcelData(mockData);

        // 自动映射字段
        const columns = Object.keys(mockData[0] || {});
        const mappings: FieldMapping[] = fields.map(field => ({
          excelColumn: columns.find(col => col.includes(field.label)) || columns[0] || "",
          systemField: field.key,
          fieldName: field.label
        }));
        setFieldMappings(mappings);

        setUploadProgress(100);
      }, 500);
    }, 500);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const handleDownloadTemplate = () => {
    // 模拟下载模板
    const templateContent = fields.map(f => f.label).join('\t') + '\n';
    const blob = new Blob([templateContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}_导入模板.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const validateRow = (row: any, index: number): ImportRow => {
    const errors: string[] = [];
    const rowData: Record<string, string> = {};

    // 验证必填字段
    fieldMappings.forEach(mapping => {
      const field = fields.find(f => f.key === mapping.systemField);
      const value = row[mapping.excelColumn] || "";
      rowData[mapping.systemField] = value;

      if (field?.required && !value) {
        errors.push(`${mapping.fieldName}不能为空`);
      }
    });

    return {
      status: errors.length > 0 ? 'error' : 'success',
      errorMessage: errors.join('; '),
      data: rowData
    };
  };

  const handleImport = () => {
    // 验证数据
    const results = excelData.map((row, index) => validateRow(row, index));
    setImportResults(results);
    setShowResults(true);

    // 统计结果
    const successCount = results.filter(r => r.status === 'success').length;
    const errorCount = results.filter(r => r.status === 'error').length;

    // 只导入成功的数据
    const successData = results
      .filter(r => r.status === 'success')
      .map(r => r.data);

    if (successData.length > 0) {
      onImport(successData);
    }
  };

  const handleFieldMappingChange = (systemField: string, excelColumn: string) => {
    setFieldMappings(prev =>
      prev.map(m => m.systemField === systemField ? { ...m, excelColumn } : m)
    );
  };

  const successCount = importResults.filter(r => r.status === 'success').length;
  const errorCount = importResults.filter(r => r.status === 'error').length;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[90vw] h-[85vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">{title} - Excel导入</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
          >
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-auto p-4">
          {/* 第一步：上传文件 */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-medium text-gray-700">第一步：上传Excel文件</h4>
              <button
                onClick={handleDownloadTemplate}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                <Download className="w-3 h-3" />
                下载模板
              </button>
            </div>

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
                className="hidden"
              />

              {selectedFile ? (
                <div className="flex flex-col items-center gap-2">
                  <FileSpreadsheet className="w-8 h-8 text-green-600" />
                  <p className="text-xs text-gray-700 font-medium">{selectedFile.name}</p>
                  {uploadProgress < 100 ? (
                    <div className="w-full max-w-xs">
                      <div className="bg-gray-200 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-blue-600 h-full transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1">上传中... {uploadProgress}%</p>
                    </div>
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
                  <p className="text-xs text-gray-600">拖拽Excel文件到此处，或
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

          {/* 第二步：字段映射 */}
          {excelData.length > 0 && uploadProgress === 100 && (
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
                    {fieldMappings.map((mapping, idx) => {
                      const field = fields.find(f => f.key === mapping.systemField);
                      return (
                        <tr key={idx} className="border-t border-gray-200">
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
                              {Object.keys(excelData[0] || {}).map(col => (
                                <option key={col} value={col}>{col}</option>
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

          {/* 第三步：数据预览 */}
          {excelData.length > 0 && uploadProgress === 100 && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-700 mb-2">第三步：数据预览（前5行）</h4>
              <div className="border border-gray-300 rounded overflow-auto max-h-48">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      {Object.keys(excelData[0] || {}).map((key, idx) => (
                        <th key={idx} className="px-3 py-2 text-left text-gray-700 border border-gray-300">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {excelData.slice(0, 5).map((row, rowIdx) => (
                      <tr key={rowIdx} className="border-t border-gray-200">
                        {Object.values(row).map((value: any, cellIdx) => (
                          <td key={cellIdx} className="px-3 py-2 border border-gray-300 text-gray-700">
                            {value || "-"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-500 mt-1">共 {excelData.length} 条数据</p>
            </div>
          )}

          {/* 导入结果列表 */}
          {showResults && importResults.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-medium text-gray-700">导入结果</h4>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1 text-green-700">
                    <CheckCircle className="w-3 h-3" />
                    成功：{successCount} 条
                  </span>
                  <span className="flex items-center gap-1 text-red-700">
                    <XCircle className="w-3 h-3" />
                    失败：{errorCount} 条
                  </span>
                </div>
              </div>

              <div className="border border-gray-300 rounded overflow-auto max-h-80">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-700 border border-gray-300 w-24">状态</th>
                      {fields.map((field, idx) => (
                        <th key={idx} className="px-3 py-2 text-left text-gray-700 border border-gray-300">
                          {field.label}
                        </th>
                      ))}
                      <th className="px-3 py-2 text-left text-gray-700 border border-gray-300">错误信息</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {importResults.map((result, rowIdx) => (
                      <tr
                        key={rowIdx}
                        className={`border-t border-gray-200 ${result.status === 'error' ? 'bg-red-50' : ''}`}
                      >
                        <td className="px-3 py-2 border border-gray-300">
                          {result.status === 'success' ? (
                            <span className="flex items-center gap-1 text-green-700">
                              <CheckCircle className="w-3 h-3" />
                              成功
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-red-700">
                              <XCircle className="w-3 h-3" />
                              失败
                            </span>
                          )}
                        </td>
                        {fields.map((field, cellIdx) => (
                          <td
                            key={cellIdx}
                            className={`px-3 py-2 border border-gray-300 ${result.status === 'error' ? 'text-red-700' : 'text-gray-700'}`}
                          >
                            {result.data[field.key] || "-"}
                          </td>
                        ))}
                        <td className="px-3 py-2 border border-gray-300 text-red-600 text-xs">
                          {result.errorMessage || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {showResults && (
              <span className="flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {successCount > 0 && `${successCount}条数据已成功导入`}
                {errorCount > 0 && `，${errorCount}条数据导入失败`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 transition-colors"
            >
              {showResults ? '关闭' : '取消'}
            </button>
            {excelData.length > 0 && uploadProgress === 100 && !showResults && (
              <button
                onClick={handleImport}
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                开始导入
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
