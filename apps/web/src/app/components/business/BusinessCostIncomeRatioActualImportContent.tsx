import { useEffect, useMemo, useRef, useState } from "react";
import { Download, FileSpreadsheet, Upload } from "lucide-react";
import {
  applyBusinessCostIncomeImport,
  downloadBusinessCostIncomeImportTemplate,
  previewBusinessCostIncomeImport,
  type BusinessCostIncomeActualImportApplyResponse,
  type BusinessCostIncomeActualImportPreviewResponse,
} from "@/lib/business/businessCostIncomeApi";
import { listOrgProductRuntimeProducts, type OrgProductRuntimeProductDto } from "@/lib/expense/masterDataApi";

const IMPORT_YEAR = 2026;

function compareProduct(a: OrgProductRuntimeProductDto, b: OrgProductRuntimeProductDto): number {
  const groupA = a.parent_code === "CORP" ? a.product_code : a.parent_code ?? a.product_code;
  const groupB = b.parent_code === "CORP" ? b.product_code : b.parent_code ?? b.product_code;
  if (groupA !== groupB) return groupA.localeCompare(groupB, "zh-CN");
  return a.level - b.level || a.product_code.localeCompare(b.product_code, "zh-CN");
}

function selectedMonthsFromState(selectedMonths: boolean[]): number[] {
  return selectedMonths.map((checked, idx) => (checked ? idx + 1 : 0)).filter((month) => month > 0);
}

export function BusinessCostIncomeRatioActualImportContent() {
  const [products, setProducts] = useState<OrgProductRuntimeProductDto[]>([]);
  const [selectedProductCodes, setSelectedProductCodes] = useState<string[]>([]);
  const [selectedMonths, setSelectedMonths] = useState<boolean[]>(Array.from({ length: 12 }, () => true));
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BusinessCostIncomeActualImportPreviewResponse | null>(null);
  const [applyResult, setApplyResult] = useState<BusinessCostIncomeActualImportApplyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const availableProducts = useMemo(() => {
    const parentSet = new Set(products.map((item) => item.parent_code).filter(Boolean));
    return products
      .filter((item) => item.product_code !== "CORP" && item.level !== 2 && !parentSet.has(item.product_code))
      .sort(compareProduct);
  }, [products]);

  const groupedProducts = useMemo(() => {
    const nameByCode = new Map(products.map((item) => [item.product_code, item.product_name]));
    const lineMap = new Map<string, { lineCode: string; lineName: string; items: OrgProductRuntimeProductDto[] }>();
    for (const product of availableProducts) {
      const lineCode = product.parent_code || "";
      if (!lineMap.has(lineCode)) {
        lineMap.set(lineCode, {
          lineCode,
          lineName: nameByCode.get(lineCode) || lineCode,
          items: [],
        });
      }
      lineMap.get(lineCode)!.items.push(product);
    }
    const preferredOrder = ["A", "B", "C", "D", "E", "F"];
    return [
      ...preferredOrder.map((code) => lineMap.get(code)).filter((item): item is NonNullable<typeof item> => Boolean(item)),
      ...Array.from(lineMap.values()).filter((group) => !preferredOrder.includes(group.lineCode)),
    ];
  }, [availableProducts, products]);

  useEffect(() => {
    void (async () => {
      try {
        const rows = await listOrgProductRuntimeProducts();
        setProducts(rows);
        const parentSet = new Set(rows.map((item) => item.parent_code).filter(Boolean));
        const options = rows
          .filter((item) => item.product_code !== "CORP" && item.level !== 2 && !parentSet.has(item.product_code))
          .sort(compareProduct);
        const preferred = options.find((item) => item.product_code === "A04") ?? options[0];
        if (preferred) setSelectedProductCodes([preferred.product_code]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载产品列表失败");
      }
    })();
  }, []);

  const toggleMonth = (month: number) => {
    setSelectedMonths((prev) => {
      const next = [...prev];
      next[month - 1] = !next[month - 1];
      return next;
    });
  };

  const toggleProductCode = (code: string) => {
    setSelectedProductCodes((prev) =>
      prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]
    );
  };

  const resetFile = () => {
    setSelectedFile(null);
    setPreview(null);
    setApplyResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDownloadTemplate = async () => {
    const months = selectedMonthsFromState(selectedMonths);
    if (selectedProductCodes.length === 0) {
      setError("请至少选择一个产品。");
      return;
    }
    if (months.length === 0) {
      setError("请至少选择一个导入月份。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await downloadBusinessCostIncomeImportTemplate({
        year: IMPORT_YEAR,
        productCodes: selectedProductCodes,
        months,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "模板下载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleFile = async (file: File) => {
    if (!file.name.match(/\.(xlsx|xlsm)$/i)) {
      setError("请选择 Excel 文件（.xlsx 或 .xlsm）。");
      return;
    }
    const months = selectedMonthsFromState(selectedMonths);
    setSelectedFile(file);
    setApplyResult(null);
    setLoading(true);
    setError("");
    try {
      setPreview(await previewBusinessCostIncomeImport(file, IMPORT_YEAR, months));
    } catch (e) {
      resetFile();
      setError(e instanceof Error ? e.message : "导入预览失败");
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!selectedFile) return;
    const months = selectedMonthsFromState(selectedMonths);
    if (months.length === 0) {
      setError("请至少选择一个导入月份。");
      return;
    }
    if (preview?.error_cells) {
      setError("当前预览存在错误，请修正 Excel 后重新上传。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await applyBusinessCostIncomeImport(selectedFile, IMPORT_YEAR, months);
      setApplyResult(result);
      resetFile();
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败");
    } finally {
      setLoading(false);
    }
  };

  const allMonthsSelected = selectedMonths.every(Boolean);
  const readyRows = preview?.items.filter((item) => item.action === "ready") ?? [];
  const errorRows = preview?.items.filter((item) => item.action === "error") ?? [];

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">业务支出成本收入比实际导入</h3>
          <p className="bb-page-subtitle">
            先按产品和月份下载模板，再上传填好的实际数、预算数、预测数。导入只写入当前年度库的
            `business_cost_income_value`，不创建第二套 BCIR 数据库。
          </p>
        </div>
      </div>

      <div className="bb-panel p-4 space-y-4">
        {error && (
          <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
        )}
        {applyResult && (
          <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
            导入完成：写入 {applyResult.saved_cells} 个单元格，跳过 {applyResult.skipped_cells}，错误 {applyResult.error_cells}。
          </div>
        )}

        <section className="space-y-2">
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs text-gray-600 mr-1">导入月份：</span>
            <button
              type="button"
              onClick={() => setSelectedMonths(Array.from({ length: 12 }, () => !allMonthsSelected))}
              className="bb-btn bb-btn-secondary text-[11px] py-0.5 px-1.5 mr-1"
            >
              {allMonthsSelected ? "取消全选" : "全选"}
            </button>
            {Array.from({ length: 12 }, (_, idx) => idx + 1).map((month) => (
              <label key={month} className="flex items-center gap-0.5 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={selectedMonths[month - 1]}
                  onChange={() => toggleMonth(month)}
                  className="w-3 h-3"
                />
                {month}月
              </label>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-gray-600">
              模板产品（已选 {selectedProductCodes.length} / {availableProducts.length}）
            </span>
            <div className="flex items-center gap-2">
              <button type="button" className="bb-btn bb-btn-secondary text-[11px] py-1" onClick={() => setSelectedProductCodes(availableProducts.map((item) => item.product_code))}>
                全选
              </button>
              <button type="button" className="bb-btn bb-btn-secondary text-[11px] py-1" onClick={() => setSelectedProductCodes([])}>
                清空
              </button>
              <button type="button" className="bb-btn bb-btn-secondary" onClick={() => void handleDownloadTemplate()} disabled={loading || selectedProductCodes.length === 0}>
                <Download className="w-3.5 h-3.5" />
                下载模板
              </button>
            </div>
          </div>

          <div className="max-h-64 overflow-auto rounded border border-gray-200 bg-white p-2 space-y-1">
            {groupedProducts.map((group) => (
              <div key={group.lineCode}>
                <div className="sticky top-0 mb-0.5 rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-[var(--bb-text-strong)]">
                  {group.lineName} ({group.lineCode}线)
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-0.5 pl-1">
                  {group.items.map((item) => (
                    <label key={item.product_code} className="flex items-center gap-1.5 rounded px-1 py-0.5 text-xs hover:bg-slate-50">
                      <input
                        type="checkbox"
                        checked={selectedProductCodes.includes(item.product_code)}
                        onChange={() => toggleProductCode(item.product_code)}
                      />
                      <span className="truncate">{item.product_code}-{item.product_name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded border border-dashed border-[var(--bb-border)] bg-[var(--bb-bg-subtle)] p-6 text-center">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(event) => event.target.files?.[0] && void handleFile(event.target.files[0])}
          />
          <FileSpreadsheet className="mx-auto mb-2 h-8 w-8 text-[var(--bb-primary)]" />
          <p className="mb-3 text-xs text-[var(--bb-text)]">
            {selectedFile ? selectedFile.name : "请选择由本页面下载模板填写后的 Excel 文件。"}
          </p>
          <div className="flex justify-center gap-2">
            <button type="button" className="bb-btn bb-btn-primary" onClick={() => fileInputRef.current?.click()} disabled={loading}>
              <Upload className="w-3.5 h-3.5" />
              选择并预览
            </button>
            {selectedFile && (
              <button type="button" className="bb-btn bb-btn-secondary" onClick={resetFile} disabled={loading}>
                清空
              </button>
            )}
          </div>
        </section>

        {preview && (
          <section className="rounded border border-gray-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-slate-50 px-4 py-2 text-xs">
              <div>
                <span className="font-semibold text-slate-700">预览结果</span>
                <span className="ml-2 text-gray-500">
                  可写入 {preview.insertable_cells}，跳过 {preview.skipped_cells}，错误 {preview.error_cells}
                </span>
              </div>
              <button
                type="button"
                className="bb-btn bb-btn-primary"
                onClick={() => void handleApply()}
                disabled={loading || readyRows.length === 0 || errorRows.length > 0}
              >
                确认写入
              </button>
            </div>
            <div className="max-h-[420px] overflow-auto">
              <table className="min-w-[1100px] w-full border-collapse text-xs">
                <thead className="bg-gray-100">
                  <tr className="text-left text-gray-700">
                    <th className="border border-gray-200 px-2 py-2">状态</th>
                    <th className="border border-gray-200 px-2 py-2">工作表</th>
                    <th className="border border-gray-200 px-2 py-2">行号</th>
                    <th className="border border-gray-200 px-2 py-2">产品</th>
                    <th className="border border-gray-200 px-2 py-2">细项</th>
                    <th className="border border-gray-200 px-2 py-2">字段</th>
                    <th className="border border-gray-200 px-2 py-2">月份</th>
                    <th className="border border-gray-200 px-2 py-2 text-right">值</th>
                    <th className="border border-gray-200 px-2 py-2">说明</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.slice(0, 300).map((row, idx) => (
                    <tr key={`${row.sheet_name}-${row.row_number}-${row.month ?? "row"}-${idx}`} className={row.action === "error" ? "bg-red-50" : "hover:bg-gray-50"}>
                      <td className="border border-gray-200 px-2 py-1.5">{row.action === "error" ? "错误" : "可写入"}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.sheet_name}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.row_number}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.product_code}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.item_name}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.field_label}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.month ? `${row.month}月` : "-"}</td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right">{row.value_text || "-"}</td>
                      <td className="border border-gray-200 px-2 py-1.5">{row.message || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
