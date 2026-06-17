import type { ExpenseForecastOwnerGroupOptionDto } from "@/lib/expense/expenseForecastApi";
import { ALL_FIELD_KEYS, EXPORT_FIELDS } from "@/lib/expense/expenseForecastViewModel";

type ExportMode = "normal" | "group";

type ExpenseForecastExportFieldsDialogProps = {
  exportMode: ExportMode;
  exportGroupName: string;
  ownerGroups: ExpenseForecastOwnerGroupOptionDto[];
  selectedFields: Set<string>;
  onGroupNameChange: (value: string) => void;
  onSelectedFieldsChange: (value: Set<string>) => void;
  onClose: () => void;
  onExport: (excludeFields: string[]) => void;
};

export function ExpenseForecastExportFieldsDialog({
  exportMode,
  exportGroupName,
  ownerGroups,
  selectedFields,
  onGroupNameChange,
  onSelectedFieldsChange,
  onClose,
  onExport,
}: ExpenseForecastExportFieldsDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-[520px] max-h-[80vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <h3 className="mb-4 text-lg font-semibold">导出Excel设置</h3>

        {exportMode === "group" && (
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">选择事业群</label>
            <select
              className="w-full rounded border border-gray-300 px-3 py-2"
              value={exportGroupName}
              onChange={(event) => onGroupNameChange(event.target.value)}
            >
              <option value="">请选择事业群</option>
              {ownerGroups.map((group) => (
                <option key={group.group_value} value={group.group_value}>
                  {group.group_label}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="mb-4">
          <div className="mb-2 flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">导出字段</label>
            <button
              type="button"
              className="text-xs text-blue-600 hover:underline"
              onClick={() => {
                if (selectedFields.size === ALL_FIELD_KEYS.length) {
                  onSelectedFieldsChange(new Set());
                } else {
                  onSelectedFieldsChange(new Set(ALL_FIELD_KEYS));
                }
              }}
            >
              {selectedFields.size === ALL_FIELD_KEYS.length ? "取消全选" : "全选"}
            </button>
          </div>
          {["月度", "汇总", "报送"].map((group) => (
            <div key={group} className="mb-2">
              <div className="mb-1 text-xs font-medium text-gray-500">{group}</div>
              <div className="flex flex-wrap gap-2">
                {EXPORT_FIELDS.filter((field) => field.group === group).map((field) => (
                  <label key={field.key} className="flex items-center gap-1 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedFields.has(field.key)}
                      onChange={(event) => {
                        const next = new Set(selectedFields);
                        if (event.target.checked) next.add(field.key);
                        else next.delete(field.key);
                        onSelectedFieldsChange(next);
                      }}
                    />
                    {field.label}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button type="button" className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            disabled={selectedFields.size === 0 || (exportMode === "group" && !exportGroupName)}
            onClick={() => {
              const excludeFields = ALL_FIELD_KEYS.filter((key) => !selectedFields.has(key));
              onExport(excludeFields);
            }}
          >
            导出
          </button>
        </div>
      </div>
    </div>
  );
}
