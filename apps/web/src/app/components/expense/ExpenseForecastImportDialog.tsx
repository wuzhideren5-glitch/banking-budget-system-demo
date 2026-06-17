import { X } from "lucide-react";
import type {
  ExpenseForecastImportApplyResponseDto,
  ExpenseForecastImportPreviewResponseDto,
} from "@/lib/expense/expenseForecastApi";
import { formatNumber, scopeLabel, type ImportMode, type ScopeType } from "@/lib/expense/expenseForecastViewModel";

type ExpenseForecastImportDialogProps = {
  scopeType: ScopeType;
  scopeValue: string;
  forecastVersion: string;
  ownerEditableScope: boolean;
  importMode: ImportMode;
  importFile: File | null;
  importLoading: boolean;
  importPreview: ExpenseForecastImportPreviewResponseDto | null;
  importResult: ExpenseForecastImportApplyResponseDto | null;
  amountDivisor: number;
  error: string;
  message: string;
  onClose: () => void;
  onModeChange: (mode: ImportMode) => void;
  onFileChange: (file: File | null) => void;
  onPreview: () => void;
  onApply: () => void;
};

export function ExpenseForecastImportDialog({
  scopeType,
  scopeValue,
  forecastVersion,
  ownerEditableScope,
  importMode,
  importFile,
  importLoading,
  importPreview,
  importResult,
  amountDivisor,
  error,
  message,
  onClose,
  onModeChange,
  onFileChange,
  onPreview,
  onApply,
}: ExpenseForecastImportDialogProps) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/25 px-4">
      <div className="flex h-[80vh] w-[920px] flex-col overflow-hidden rounded bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <div>
            <div className="text-sm font-medium text-gray-800">导入Excel</div>
            <div className="mt-1 text-[11px] text-gray-500">
              当前口径：{scopeLabel(scopeType)} / {scopeValue} / 版本 {forecastVersion}
            </div>
          </div>
          <button type="button" className="rounded p-1 hover:bg-gray-100" onClick={onClose}>
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
                onChange={(event) => onModeChange(event.target.value as ImportMode)}
              >
                <option value="append">追加</option>
                <option value="overwrite">覆盖</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-gray-500">导入文件</span>
              <input
                className="block h-8 rounded border border-gray-300 px-2 py-1"
                type="file"
                accept=".xlsx"
                onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
              />
            </label>
            <button
              type="button"
              className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50"
              disabled={importLoading}
              onClick={onPreview}
            >
              {importLoading ? "解析中..." : "预览导入"}
            </button>
            <button
              type="button"
              className="h-8 rounded border border-blue-500 bg-blue-500 px-3 text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={importLoading || !importFile}
              onClick={onApply}
            >
              {importLoading ? "处理中..." : "应用导入"}
            </button>
          </div>
          {!ownerEditableScope ? (
            <div className="rounded border border-amber-200 bg-amber-50 p-3 text-amber-700">
              当前为{scopeLabel(scopeType)}口径，仅支持汇总展示；费用预估、业务报送、资划建议仅可在"费用归属部门"口径下录入或导入。
            </div>
          ) : null}
          {ownerEditableScope ? (
            <div className="rounded border border-blue-100 bg-blue-50 p-3 text-blue-700">
              导入模板支持 `M1~M12/1月~12月`、`业务报送`、`资划建议` 列；资划建议未录入时默认显示年度预算。
            </div>
          ) : null}
          {error ? <div className="rounded border border-red-200 bg-red-50 p-3 text-red-700">{error}</div> : null}
          {message && importResult ? (
            <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-emerald-700">{message}</div>
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
                      <th className="border-b border-r border-gray-200 px-2 py-2 text-left">费用归属部门</th>
                      <th className="border-b border-r border-gray-200 px-2 py-2 text-left">预算科目</th>
                      <th className="border-b border-r border-gray-200 px-2 py-2 text-left">字段</th>
                      <th className="border-b border-r border-gray-200 px-2 py-2 text-right">值</th>
                      <th className="border-b border-r border-gray-200 px-2 py-2 text-left">动作</th>
                      <th className="border-b border-gray-200 px-2 py-2 text-left">说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importPreview.items.map((item, idx) => (
                      <tr
                        key={`${item.row_number}-${item.budget_subject}-${item.field_name}-${item.month ?? "annual"}-${idx}`}
                        className="odd:bg-white even:bg-gray-50"
                      >
                        <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.row_number}</td>
                        <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.owner_name ?? "-"}</td>
                        <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.budget_subject}</td>
                        <td className="border-b border-r border-gray-200 px-2 py-1.5">{item.field_label}</td>
                        <td className="border-b border-r border-gray-200 px-2 py-1.5 text-right">
                          {formatNumber(item.value, amountDivisor)}
                        </td>
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
              导入完成：新增 {importResult.inserted_cells}，覆盖 {importResult.updated_cells}，跳过 {importResult.skipped_cells}
              ，错误 {importResult.error_cells}。
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
