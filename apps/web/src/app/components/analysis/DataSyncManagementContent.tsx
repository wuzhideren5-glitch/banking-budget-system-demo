import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Eye, RefreshCw, Upload } from "lucide-react";
import {
  ExpenseBudgetExecutionStatusDto,
  getExpenseBudgetExecutionStatus,
  previewExpenseFramework,
  syncExpenseFramework,
} from "@/lib/expense/expenseDataSyncApi";

function formatStatusText(item: ExpenseBudgetExecutionStatusDto["framework_import"]): string {
  if (!item) return "尚未同步";
  return `已同步，时间 ${item.synced_at}`;
}

export function DataSyncManagementContent() {
  const [status, setStatus] = useState<ExpenseBudgetExecutionStatusDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncingFramework, setSyncingFramework] = useState(false);
  const [frameworkFile, setFrameworkFile] = useState<File | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getExpenseBudgetExecutionStatus();
      setStatus(result);
    } catch (e) {
      alert(e instanceof Error ? `加载同步状态失败：${e.message}` : "加载同步状态失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const frameworkSummary = useMemo(() => {
    if (!status?.framework_import) return "尚未执行初始化框架导入。日常维护以系统主数据为准。";
    return status.framework_import.note || `最近初始化导入时间 ${status.framework_import.synced_at}`;
  }, [status]);

  const handlePreviewFramework = async () => {
    if (!frameworkFile) {
      alert("请先选择初始化框架文件。");
      return;
    }
    try {
      const preview = await previewExpenseFramework(frameworkFile);
      const lines = [
        "初始化框架导入预览：",
        `框架来源：${preview.source_file}`,
        `预算部门：${preview.framework.budget_department_count} 行`,
        `部门预算科目：${preview.framework.subject_count} 行`,
        `主数据部门：${preview.master_preview.dept_rows} 行`,
        `新增科目：${preview.master_preview.new_subjects} 个`,
        `未匹配现有科目：${preview.master_preview.unmatched_existing_subjects} 个`,
      ];
      alert(lines.join("\n"));
    } catch (e) {
      alert(e instanceof Error ? `读取预览失败：${e.message}` : "读取预览失败");
    }
  };

  const handleSyncFramework = async () => {
    setSyncingFramework(true);
    try {
      if (!frameworkFile) {
        alert("请先选择初始化框架文件。");
        return;
      }
      const preview = await previewExpenseFramework(frameworkFile);
      const confirmText = [
        "即将执行初始化框架导入并更新部门主数据：",
        `框架来源：${preview.source_file}`,
        `预算部门 ${preview.framework.budget_department_count} 行 / 部门预算科目 ${preview.framework.subject_count} 行`,
        `将重建部门 ${preview.master_preview.dept_rows} 行，机构及产品指标已匹配 ${preview.master_preview.matched_subjects} 项`,
      ].join("\n");
      if (!window.confirm(confirmText)) return;
      const result = await syncExpenseFramework(frameworkFile, true);
      alert(
        [
          "初始化框架导入完成。",
          `预算部门 ${result.framework_rows.budget_departments} 行，部门预算科目 ${result.framework_rows.subjects} 行`,
          result.master_apply
            ? `部门主数据更新：部门 ${result.master_apply.dept_rows} 行，机构及产品指标匹配 ${result.master_apply.matched_metric_subjects} 项`
            : "本次未更新部门主数据。",
        ].join("\n"),
      );
      await loadStatus();
    } catch (e) {
      alert(e instanceof Error ? `初始化框架导入失败：${e.message}` : "初始化框架导入失败");
    } finally {
      setSyncingFramework(false);
    }
  };

  const onFrameworkFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setFrameworkFile(file);
  };

  return (
    <div className="bb-page overflow-auto">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">数据同步管理</h3>
          <p className="bb-page-subtitle">统一管理初始化框架导入与底层同步状态查看。费用执行实际请通过“费用执行明细导入”进入费用闭环。</p>
        </div>
      </div>

      <div className="bb-toolbar">
        <button
          type="button"
          onClick={() => void loadStatus()}
          disabled={loading}
          className="bb-btn bb-btn-secondary"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新状态
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3">
        <div className="bb-panel p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-[var(--bb-text-strong)]">初始化框架导入</div>
              <div className="mt-1 text-xs text-[var(--bb-text-muted)]">{frameworkSummary}</div>
              <div className="mt-2 text-xs text-[var(--bb-text)]">
                状态：{formatStatusText(status?.framework_import)}
              </div>
              <div className="mt-1 text-xs text-[var(--bb-text)]">
                部门主数据应用：{formatStatusText(status?.master_apply)}
              </div>
              <div className="mt-1 text-xs text-[var(--bb-text)]">
                内部表：预算部门 {status?.counts.expense_framework_budget_department ?? 0} / 部门预算科目{" "}
                {status?.counts.expense_framework_subject ?? 0}
              </div>
              <div className="mt-1 text-xs text-[var(--bb-warning)]">仅用于历史初始化或批量导入，当前业务运行不依赖该文件。</div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".xlsx,.xls,.xlsm"
                onChange={onFrameworkFileChange}
                className="bb-input py-1 text-xs"
              />
              <button
                type="button"
                onClick={() => void handlePreviewFramework()}
                disabled={!frameworkFile}
                className="bb-btn bb-btn-secondary"
              >
                <Eye className="w-3.5 h-3.5" />
                预览导入结果
              </button>
              <button
                type="button"
                onClick={() => void handleSyncFramework()}
                disabled={syncingFramework || !frameworkFile}
                className="bb-btn bb-btn-primary"
              >
                <Upload className="w-3.5 h-3.5" />
                {syncingFramework ? "导入中..." : "导入初始化框架"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
