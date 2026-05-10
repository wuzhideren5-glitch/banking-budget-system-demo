import { useState, useEffect, useRef } from "react";
import { Download, Upload, ChevronRight, ChevronDown, TrendingUp, Calculator, AlertCircle, Save } from "lucide-react";
import {
  fetchDriverCategories,
  downloadDriverTemplate,
  importDriverExcel,
  importDriverJson,
  previewDriverExcel,
  type DriverCategoryDto,
  type DriverIndicatorDto,
  type DriverImportRequestDto,
  type DriverImportPreviewResponseDto,
  type DriverImportResponseDto,
} from "@/lib/api";

// ── Month labels ──
const MONTHS = [
  "M01", "M02", "M03", "M04", "M05", "M06",
  "M07", "M08", "M09", "M10", "M11", "M12",
];

const MONTH_LABELS = [
  "1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月",
];

// ── Inline types for form state ──
type ProductInput = {
  product_code: string;
  product_name: string;
  data_acct_code: string | null;
  data_acct_name: string;
  value_type: string;
  report_code: string | null;
  report_path: string[];
  actualMonthly: number[];
  monthly: (number | null)[]; // length 12, null means unchanged
};

function parseReportToken(token: string): { code: string; name: string } {
  const trimmed = token.trim();
  const m = trimmed.match(/^([A-Z]\d+)\s+(.+)$/);
  if (!m) return { code: "", name: trimmed };
  return { code: m[1], name: m[2] };
}

function formatReportPath(path: string[]): string {
  if (!path.length) return "未映射数据科目";
  return path
    .map((token) => {
      const parsed = parseReportToken(token);
      return parsed.name || parsed.code || token;
    })
    .join(" / ");
}

export function BudgetPredictionContent() {
  const [categories, setCategories] = useState<DriverCategoryDto[]>([]);
  const [selectedIndicator, setSelectedIndicator] = useState<DriverIndicatorDto | null>(null);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(["SCALE", "YIELD"]));
  const [expandedInds, setExpandedInds] = useState<Set<string>>(new Set());
  const [productInputs, setProductInputs] = useState<ProductInput[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<DriverImportResponseDto | null>(null);
  const [excelPreview, setExcelPreview] = useState<DriverImportPreviewResponseDto | null>(null);
  const [selectedExcelFileName, setSelectedExcelFileName] = useState("");
  const [importing, setImporting] = useState(false);
  const [currentMonth, setCurrentMonth] = useState(1);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load categories on mount
  useEffect(() => {
    loadCategories();
  }, []);

  const loadCategories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDriverCategories();
      setCategories(data);
      setCurrentMonth(data[0]?.current_month ?? 1);
    } catch (e: any) {
      setError(e.message || "Failed to load driver categories");
    } finally {
      setLoading(false);
    }
  };

  // When indicator changes, init product inputs
  useEffect(() => {
    if (!selectedIndicator) {
      setProductInputs([]);
      return;
    }
    const ind = selectedIndicator;
    if (ind.has_product_detail && ind.products.length > 0) {
      const rows = ind.products.flatMap((p) => {
        const accounts = p.data_accounts ?? [];
        if (accounts.length === 0) {
          return [{
            product_code: p.product_code,
            product_name: p.product_name || p.product_code,
            data_acct_code: null,
            data_acct_name: "未配置",
            value_type: ind.value_type,
            report_code: null,
            report_path: ["未映射数据科目"],
            actualMonthly: Array(12).fill(0),
            monthly: Array(12).fill(null),
          }];
        }
        return accounts.map((a) => ({
          product_code: p.product_code,
          product_name: p.product_name || p.product_code,
          data_acct_code: a.data_acct_code,
          data_acct_name: a.data_acct_name,
          value_type: a.value_type,
          report_code: a.report_code,
          report_path: a.report_path?.length ? a.report_path : ["未映射数据科目"],
          actualMonthly: a.actual_values?.length ? a.actual_values : Array(12).fill(0),
          monthly: Array(12).fill(null),
        }));
      });
      setProductInputs(rows);
    } else {
      // Single "全行" input
      setProductInputs([
        {
          product_code: "",
          product_name: "全行",
          data_acct_code: selectedIndicator.data_acct_code,
          data_acct_name: selectedIndicator.data_acct_code || "未配置",
          value_type: selectedIndicator.value_type,
          report_code: null,
          report_path: ["未映射数据科目"],
          actualMonthly: Array(12).fill(0),
          monthly: Array(12).fill(null),
        },
      ]);
    }
  }, [selectedIndicator]);

  const toggleCat = (code: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const toggleInd = (code: string) => {
    setExpandedInds((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const selectIndicator = (ind: DriverIndicatorDto) => {
    setSelectedIndicator(ind);
    setImportResult(null);
    setExcelPreview(null);
    setError(null);
  };

  const updateMonthlyValue = (prodIdx: number, monthIdx: number, raw: string) => {
    if (monthIdx + 1 < currentMonth) return;
    const text = raw.trim();
    const v = parseFloat(text.replace(/,/g, ""));
    setProductInputs((prev) => {
      const next = [...prev];
      const p = { ...next[prodIdx] };
      p.monthly = [...p.monthly];
      p.monthly[monthIdx] = text === "" || isNaN(v) ? null : v;
      next[prodIdx] = p;
      return next;
    });
  };

  const fillAllMonths = (prodIdx: number, raw: string) => {
    const v = parseFloat(raw.replace(/,/g, ""));
    const val = isNaN(v) ? 0 : v;
    setProductInputs((prev) => {
      const next = [...prev];
      const p = { ...next[prodIdx], monthly: next[prodIdx].monthly.map((oldValue, idx) => (
        idx + 1 < currentMonth ? oldValue : val
      )) };
      next[prodIdx] = p;
      return next;
    });
  };

  // Build import request from inputs
  const buildImportRequest = (): DriverImportRequestDto[] => {
    if (!selectedIndicator) return [];
    const requests: DriverImportRequestDto[] = [];

    for (const pi of productInputs) {
      if (selectedIndicator.has_monthly_detail) {
        // Monthly detail: build M01-M12 items
        const items = pi.monthly.flatMap((v, i) => (
          v === null || i + 1 < currentMonth ? [] : [{ month: MONTHS[i], value: v }]
        ));
        if (items.length === 0) continue;
        requests.push({
          indicator_code: selectedIndicator.indicator_code,
          product_code: pi.product_code || null,
          data_acct_code: pi.data_acct_code,
          monthly_values: items,
        });
      } else {
        // Single annual value: only M01 contains the value
        const annualVal = pi.monthly[0];
        if (annualVal === null || currentMonth > 1) continue;
        // For annual indicators, distribute: we store in M01
        requests.push({
          indicator_code: selectedIndicator.indicator_code,
          product_code: pi.product_code || null,
          data_acct_code: pi.data_acct_code,
          monthly_values: [{ month: "M01", value: annualVal }],
        });
      }
    }
    return requests;
  };

  const handleJsonImport = async (recalculate: boolean) => {
    const req = buildImportRequest();
    if (req.length === 0) {
      setError("No data to import");
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const result = await importDriverJson(req, { recalculate });
      setImportResult(result);
      setExcelPreview(null);
    } catch (e: any) {
      setError(e.message || "Save failed");
    } finally {
      setImporting(false);
    }
  };

  const handleExcelImport = async (file: File) => {
    setImporting(true);
    setError(null);
    try {
      setSelectedExcelFileName(file.name);
      const preview = await previewDriverExcel(file);
      setExcelPreview(preview);
      if (preview.ready_rows === 0) {
        setImportResult(null);
        setError(preview.errors[0] || "Excel 中没有可导入的数据");
        return;
      }
      if (preview.error_rows > 0) {
        setImportResult(null);
        setError(`检测到 ${preview.error_rows} 行异常，请先查看预览结果后再导入。`);
        return;
      }
      const result = await importDriverExcel(file);
      setImportResult(result);
    } catch (e: any) {
      setError(e.message || "Excel import failed");
    } finally {
      setImporting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleExcelImport(file);
    e.target.value = "";
  };

  const handleDownloadTemplate = async () => {
    try {
      await downloadDriverTemplate();
    } catch (e: any) {
      setError(e.message || "Download failed");
    }
  };

  // ── Render helpers ──
  const showMonthly = selectedIndicator?.has_monthly_detail === 1;
  const showProducts = selectedIndicator?.has_product_detail === 1;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-sm text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full flex bg-white">
      {/* ── Left sidebar: Category tree ── */}
      <div className="w-60 border-r border-gray-200 overflow-y-auto bg-[#fafbfc] flex-shrink-0">
        <div className="px-3 py-2 border-b border-gray-200">
          <h3 className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-blue-600" />
            驱动因素分类
          </h3>
        </div>
        {categories.length === 0 && !loading ? (
          <div className="p-4 text-xs text-gray-400">未加载到驱动数据</div>
        ) : (
          categories.map((cat) => {
            const isExpanded = expandedCats.has(cat.category_code);
            return (
              <div key={cat.category_code}>
                <div
                  className="flex items-center gap-1 px-2 py-1.5 cursor-pointer hover:bg-gray-100 text-xs font-medium text-gray-700"
                  onClick={() => toggleCat(cat.category_code)}
                >
                  {isExpanded ? (
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-gray-400" />
                  )}
                  {cat.category_name}
                </div>
                {isExpanded &&
                  cat.indicators.map((ind) => {
                    const isIndExpanded = expandedInds.has(ind.indicator_code);
                    const isSelected = selectedIndicator?.indicator_code === ind.indicator_code;
                    const hasProducts = ind.has_product_detail && ind.products.length > 0;
                    return (
                      <div key={ind.indicator_code}>
                        <div
                          className={`flex items-center gap-1 pl-5 pr-2 py-1 cursor-pointer text-xs ${
                            isSelected
                              ? "bg-blue-50 text-blue-700 font-medium"
                              : "text-gray-600 hover:bg-gray-100"
                          }`}
                          onClick={() => {
                            if (hasProducts) toggleInd(ind.indicator_code);
                            selectIndicator(ind);
                          }}
                        >
                          {hasProducts ? (
                            isIndExpanded ? (
                              <ChevronDown className="w-3 h-3 text-gray-400" />
                            ) : (
                              <ChevronRight className="w-3 h-3 text-gray-400" />
                            )
                          ) : (
                            <span className="w-3" />
                          )}
                          <span className="truncate">{ind.indicator_name}</span>
                          <span className="ml-auto text-[10px] text-gray-400">
                            {ind.value_type === "百分比" ? "%" : "¥"}
                          </span>
                        </div>
                        {isIndExpanded &&
                          ind.products.map((p) => (
                            <div
                              key={p.id}
                              className="flex items-center gap-1 pl-8 pr-2 py-1 text-[11px] text-gray-500 hover:bg-gray-100 cursor-pointer"
                              onClick={() => selectIndicator(ind)}
                            >
                              <span className="w-3" />
                              <span className="truncate">{p.product_name || p.product_code}</span>
                            </div>
                          ))}
                      </div>
                    );
                  })}
              </div>
            );
          })
        )}
      </div>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-gray-50">
          <span className="text-xs font-medium text-gray-600">预算预测驱动</span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={handleDownloadTemplate}
              className="flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-100 text-gray-700"
            >
              <Download className="w-3 h-3" />
              下载模板
            </button>
            <label className="flex items-center gap-1 px-3 py-1 text-xs border border-blue-300 rounded bg-blue-50 hover:bg-blue-100 text-blue-700 cursor-pointer">
              <Upload className="w-3 h-3" />
              上传Excel导入
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={handleFileChange}
              />
            </label>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="mx-4 mt-2 flex items-center gap-1.5 px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
            <AlertCircle className="w-3.5 h-3.5" />
            {error}
          </div>
        )}

        {excelPreview && (
          <div className="mx-4 mt-2 border border-amber-200 rounded bg-amber-50">
            <div className="px-3 py-2 border-b border-amber-200 flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold text-amber-800">Excel导入预检</div>
                <div className="text-[11px] text-amber-700 mt-0.5">{selectedExcelFileName || "已选择文件"}</div>
              </div>
              <div className="text-[11px] text-amber-700">
                共 {excelPreview.row_count} 行，可导入 {excelPreview.ready_rows} 行，异常 {excelPreview.error_rows} 行
              </div>
            </div>
            <div className="p-3 space-y-3">
              {excelPreview.errors.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-red-700 mb-1">异常</p>
                  {excelPreview.errors.map((msg, idx) => (
                    <p key={idx} className="text-xs text-red-600">- {msg}</p>
                  ))}
                </div>
              )}
              {excelPreview.warnings.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-amber-800 mb-1">提醒</p>
                  {excelPreview.warnings.map((msg, idx) => (
                    <p key={idx} className="text-xs text-amber-700">- {msg}</p>
                  ))}
                </div>
              )}
              {excelPreview.preview_rows.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="border-collapse text-xs min-w-full">
                    <thead>
                      <tr className="bg-amber-100">
                        {["工作表", "行号", "指标", "产品", "匹配结果", "数据科目", "月份数值", "状态"].map((header) => (
                          <th key={header} className="border border-amber-200 px-2 py-1 text-left font-medium text-amber-900 whitespace-nowrap">
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {excelPreview.preview_rows.map((row, idx) => (
                        <tr key={`${row.sheet_name}-${row.excel_row}-${idx}`} className="bg-white">
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.sheet_name}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.excel_row}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.indicator_text || "-"}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.product_text || "-"}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">
                            {row.matched_indicator_name ? `${row.matched_indicator_name}${row.matched_product_code ? ` / ${row.matched_product_code}` : ""}` : "-"}
                          </td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">
                            {row.resolved_data_acct_codes.length ? row.resolved_data_acct_codes.join(", ") : row.requested_data_acct_code || "-"}
                          </td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">{row.recognized_value_cells}</td>
                          <td className="border border-amber-200 px-2 py-1 whitespace-nowrap">
                            <span className={row.status === "ok" ? "text-green-700" : row.status === "warning" ? "text-amber-700" : "text-red-700"}>
                              {row.message || (row.status === "ok" ? "通过" : row.status)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 overflow-auto p-4">
          {!selectedIndicator ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center text-gray-400">
                <Calculator className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                <p className="text-sm">请从左侧选择一个底层数据科目</p>
                <p className="text-xs mt-1">选择后可按产品输入预算预测值并触发计算科目重算</p>
              </div>
            </div>
          ) : (
            <div>
              {/* Indicator header */}
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-800">
                  {selectedIndicator.indicator_name}
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  类型：{selectedIndicator.value_type}
                  {selectedIndicator.data_acct_code && ` | 科目：${selectedIndicator.data_acct_code}`}
                  {showProducts && ` | 产品级明细`}
                  {!showMonthly && ` | 全年度一次性输入`}
                </p>
              </div>

              {showProducts && (
                <div className="mb-3 border border-blue-100 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800">
                  当前驱动行来自“数据科目维护”的指标树绑定。新增、删除或调整产品对应关系，请在基础数据维护的数据科目表中维护。
                </div>
              )}

              {/* Input form */}
              <div className="overflow-x-auto">
                <table className="border-collapse text-xs">
                  <thead>
                    <tr className="bg-blue-50">
                      <th className="sticky left-0 bg-blue-50 border border-gray-300 px-3 py-1.5 text-left font-medium text-gray-700 min-w-[120px]">
                        报告科目
                      </th>
                      <th className="border border-gray-300 px-3 py-1.5 text-left font-medium text-gray-700 min-w-[240px]">
                        数据科目
                      </th>
                      <th className="border border-gray-300 px-3 py-1.5 text-left font-medium text-gray-700 min-w-[120px]">
                        {showProducts ? "产品" : "范围"}
                      </th>
                      <th className="border border-gray-300 px-3 py-1.5 text-left font-medium text-gray-700 min-w-[72px]">
                        数值类型
                      </th>
                      <th className="border border-gray-300 px-2 py-1.5 text-center font-medium text-gray-700 min-w-[80px]">
                        绑定来源
                      </th>
                      {showMonthly ? (
                        MONTH_LABELS.map((ml) => (
                          <th
                            key={ml}
                            colSpan={2}
                            className="border border-gray-300 px-2 py-1.5 text-center font-medium text-gray-700 min-w-[72px]"
                          >
                            {ml}
                          </th>
                        ))
                      ) : (
                        <th colSpan={2} className="border border-gray-300 px-2 py-1.5 text-center font-medium text-gray-700 min-w-[120px]">
                          年度值
                        </th>
                      )}
                      <th className="border border-gray-300 px-2 py-1.5 text-center font-medium text-gray-600 bg-blue-50 min-w-[60px]">
                        填充
                      </th>
                    </tr>
                    <tr className="bg-blue-50">
                      <th className="sticky left-0 bg-blue-50 border border-gray-300" />
                      <th className="border border-gray-300" />
                      <th className="border border-gray-300" />
                      <th className="border border-gray-300" />
                      <th className="border border-gray-300" />
                      {showMonthly ? (
                        MONTH_LABELS.flatMap((ml) => [
                          <th key={`${ml}-actual`} className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-500 bg-[#f5f7fb] min-w-[72px]">
                            实际
                          </th>,
                          <th key={`${ml}-budget`} className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700 min-w-[72px]">
                            预测
                          </th>,
                        ])
                      ) : (
                        <>
                          <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-500 bg-[#f5f7fb] min-w-[96px]">
                            实际
                          </th>
                          <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700 min-w-[96px]">
                            预测
                          </th>
                        </>
                      )}
                      <th className="border border-gray-300" />
                    </tr>
                  </thead>
                  <tbody>
                    {productInputs.map((pi, piIdx) => (
                      <tr key={piIdx} className="hover:bg-gray-50">
                        <td className="sticky left-0 bg-white border border-gray-300 px-3 py-1 text-gray-700">
                          <div className="max-w-[280px] whitespace-normal leading-5">
                            {formatReportPath(pi.report_path)}
                          </div>
                        </td>
                        <td className="border border-gray-300 px-3 py-1 text-gray-700">
                          {pi.data_acct_code ? (
                            <>
                              <span className="font-mono text-[11px] text-gray-500">{pi.data_acct_code}</span>
                              <span className="ml-1">{pi.data_acct_name}</span>
                            </>
                          ) : (
                            <span className="text-gray-400">未配置</span>
                          )}
                        </td>
                        <td className="border border-gray-300 px-3 py-1 font-medium text-gray-700">
                          <span className="font-mono text-[11px] text-gray-500">{pi.product_code}</span>
                          <span className="ml-1">{pi.product_name}</span>
                        </td>
                        <td className="border border-gray-300 px-3 py-1 text-gray-600">
                          {pi.value_type}
                        </td>
                        <td className="border border-gray-300 px-2 py-1 text-center text-[11px] text-gray-500">
                          数据科目表
                        </td>
                        {showMonthly
                          ? MONTHS.flatMap((_, mi) => {
                              const canEditForecast = mi + 1 >= currentMonth;
                              return [
                              <td key={`${mi}-actual`} className="border border-gray-300 px-2 py-1 text-right text-gray-500 bg-[#f5f7fb]">
                                {Number(pi.actualMonthly[mi] || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                              </td>,
                              <td key={`${mi}-budget`} className={canEditForecast ? "border border-gray-300 p-0" : "border border-gray-300 p-0 bg-gray-100"}>
                                <input
                                  type="text"
                                  className={`w-full px-2 py-1 text-xs text-right border-0 bg-transparent ${
                                    canEditForecast
                                      ? "focus:outline-none focus:ring-1 focus:ring-blue-400"
                                      : "text-gray-400 cursor-not-allowed"
                                  }`}
                                  value={pi.monthly[mi] ?? ""}
                                  onChange={(e) => updateMonthlyValue(piIdx, mi, e.target.value)}
                                  placeholder={canEditForecast ? "0" : "实际月"}
                                  disabled={!canEditForecast}
                                />
                              </td>,
                            ];
                            })
                          : (
                              <>
                                <td className="border border-gray-300 px-2 py-1 text-right text-gray-500 bg-[#f5f7fb]">
                                  {Number(pi.actualMonthly[0] || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                </td>
                                <td className={currentMonth <= 1 ? "border border-gray-300 p-0" : "border border-gray-300 p-0 bg-gray-100"}>
                                  <input
                                    type="text"
                                    className={`w-full px-2 py-1 text-xs text-right border-0 bg-transparent ${
                                      currentMonth <= 1
                                        ? "focus:outline-none focus:ring-1 focus:ring-blue-400"
                                        : "text-gray-400 cursor-not-allowed"
                                    }`}
                                    value={pi.monthly[0] ?? ""}
                                    onChange={(e) => {
                                      if (currentMonth > 1) return;
                                      const text = e.target.value.trim();
                                      const v = parseFloat(text.replace(/,/g, ""));
                                      setProductInputs((prev) => {
                                        const next = [...prev];
                                        const p = { ...next[piIdx] };
                                        p.monthly = [text === "" || isNaN(v) ? null : v, ...Array(11).fill(null)];
                                        next[piIdx] = p;
                                        return next;
                                      });
                                    }}
                                    placeholder={currentMonth <= 1 ? "0" : "实际月"}
                                    disabled={currentMonth > 1}
                                  />
                                </td>
                              </>
                            )}
                        <td className="border border-gray-300 p-0">
                          {showMonthly && (
                            <input
                              type="text"
                              className="w-full px-2 py-1 text-xs text-center border-0 focus:outline-none focus:ring-1 focus:ring-blue-400 bg-transparent text-gray-400"
                              onChange={(e) => fillAllMonths(piIdx, e.target.value)}
                              placeholder="..."
                              disabled={currentMonth > 12}
                            />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Submit button */}
              <div className="mt-4 flex items-center gap-3">
                <button
                  onClick={() => handleJsonImport(false)}
                  disabled={importing}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-xs rounded font-medium ${
                    importing
                      ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                      : "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <Save className="w-3.5 h-3.5" />
                  {importing ? "正在保存..." : "保存"}
                </button>
                <button
                  onClick={() => handleJsonImport(true)}
                  disabled={importing}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-xs rounded font-medium ${
                    importing
                      ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  <Calculator className="w-3.5 h-3.5" />
                  {importing ? "正在保存并重算..." : "保存并重算"}
                </button>
                <span className="text-xs text-gray-400">
                  保存后可在预算基础数据维护按产品查看；重算会同步刷新公式结果
                </span>
              </div>

              {/* Import result */}
              {importResult && (
                <div className="mt-4 border border-gray-200 rounded">
                  <div className="px-3 py-2 bg-gray-50 border-b border-gray-200">
                    <h4 className="text-xs font-semibold text-gray-700">导入结果</h4>
                  </div>
                  <div className="p-3 space-y-2">
                    <div className="flex gap-4 text-xs text-gray-600">
                      <span>版本ID: {importResult.version_id}</span>
                      <span>预算年度: {importResult.budget_year}</span>
                      <span>保存单元格: {importResult.saved_cells}</span>
                    </div>

                    {importResult.errors && importResult.errors.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-red-600 mb-1">错误:</p>
                        {importResult.errors.map((err, i) => (
                          <p key={i} className="text-xs text-red-500">- {err}</p>
                        ))}
                      </div>
                    )}

                    {importResult.warnings && importResult.warnings.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-amber-700 mb-1">提醒:</p>
                        {importResult.warnings.map((msg, i) => (
                          <p key={i} className="text-xs text-amber-600">- {msg}</p>
                        ))}
                      </div>
                    )}

                    {importResult.monthly && importResult.monthly.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-gray-700 mb-1">月度计算结果:</p>
                        <div className="overflow-x-auto">
                          <table className="border-collapse text-xs">
                            <thead>
                              <tr className="bg-gray-100">
                                <th className="border border-gray-300 px-2 py-1 text-left">月份</th>
                                {Object.keys(importResult.monthly[0] || {}).filter(k => k !== "month").map((k) => (
                                  <th key={k} className="border border-gray-300 px-2 py-1 text-right">{k}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {importResult.monthly.map((row: any, idx: number) => (
                                <tr key={idx} className="hover:bg-gray-50">
                                  <td className="border border-gray-300 px-2 py-1 font-medium">{row.month}</td>
                                  {Object.keys(row).filter(k => k !== "month").map((k) => (
                                    <td key={k} className="border border-gray-300 px-2 py-1 text-right">
                                      {typeof row[k] === "number" ? row[k].toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(row[k])}
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
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
