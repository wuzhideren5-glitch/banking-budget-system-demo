import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Eye, RefreshCw, Upload } from "lucide-react";
import { apiGet, apiPostForm } from "@/lib/api";

type ExpenseBudgetExecutionStatusDto = {
  framework_import?: {
    source_file: string;
    source_mtime: string | null;
    synced_at: string;
    row_count: number;
    note: string | null;
  } | null;
  master_apply?: {
    source_file: string;
    source_mtime: string | null;
    synced_at: string;
    row_count: number;
    note: string | null;
  } | null;
  actual_import?: {
    source_file: string;
    source_mtime: string | null;
    synced_at: string;
    row_count: number;
    note: string | null;
  } | null;
  counts: Record<string, number>;
};

type ExpenseFrameworkPreviewDto = {
  source_file: string;
  framework: {
    group_count: number;
    owner_count: number;
    budget_department_count: number;
    product_department_count: number;
    subject_count: number;
  };
  master_preview: {
    dept_rows: number;
    dept_product_mapping_rows: number;
    matched_subjects: number;
    new_subjects: number;
    legacy_subjects: number;
    unmatched_products: number;
    sample_new_subjects: string[];
    sample_legacy_subjects: string[];
    sample_unmatched_products: string[];
  };
};

type ExpenseFrameworkSyncResultDto = {
  source_file: string;
  framework_rows: {
    budget_departments: number;
    product_departments: number;
    subjects: number;
  };
  master_applied: boolean;
  master_apply?: {
    backup_file: string;
    dept_rows: number;
    dept_product_mapping_rows: number;
    data_account_upserts: number;
    matched_subjects: number;
    new_subjects: number;
    legacy_subjects: number;
    unmatched_products: number;
    sample_new_subjects: string[];
    sample_legacy_subjects: string[];
    sample_unmatched_products: string[];
  };
};

type ExpenseActualSyncResultDto = {
  source_file: string;
  detail_rows: number;
  monthly_subject_rows: number;
  saved_cells: number;
};

function formatStatusText(item: ExpenseBudgetExecutionStatusDto["framework_import"]): string {
  if (!item) return "尚未同步";
  return `已同步，时间 ${item.synced_at}`;
}

export function DataSyncManagementContent() {
  const [status, setStatus] = useState<ExpenseBudgetExecutionStatusDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncingFramework, setSyncingFramework] = useState(false);
  const [syncingActual, setSyncingActual] = useState(false);
  const [frameworkFile, setFrameworkFile] = useState<File | null>(null);
  const [actualFile, setActualFile] = useState<File | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiGet<ExpenseBudgetExecutionStatusDto>("/api/expense-budget-execution/status");
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
    if (!status?.framework_import) return "尚未同步费用整体框架。";
    return status.framework_import.note || `最近同步时间 ${status.framework_import.synced_at}`;
  }, [status]);

  const actualSummary = useMemo(() => {
    if (!status?.actual_import) return "尚未同步费用执行实际。";
    return status.actual_import.note || `最近同步时间 ${status.actual_import.synced_at}`;
  }, [status]);

  const handlePreviewFramework = async () => {
    if (!frameworkFile) {
      alert("请先选择费用整体框架文件。");
      return;
    }
    try {
      const fd = new FormData();
      fd.append("file", frameworkFile);
      const preview = await apiPostForm<ExpenseFrameworkPreviewDto>(
        "/api/expense-budget-execution/admin/framework-preview",
        fd,
      );
      const lines = [
        "费用整体框架同步预览：",
        `框架来源：${preview.source_file}`,
        `预算部门：${preview.framework.budget_department_count} 行`,
        `产品部门：${preview.framework.product_department_count} 行`,
        `部门预算科目：${preview.framework.subject_count} 行`,
        `主数据部门：${preview.master_preview.dept_rows} 行`,
        `部门产品映射：${preview.master_preview.dept_product_mapping_rows} 行`,
        `新增科目：${preview.master_preview.new_subjects} 个`,
        `遗留科目：${preview.master_preview.legacy_subjects} 个`,
        `未匹配产品：${preview.master_preview.unmatched_products} 个`,
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
        alert("请先选择费用整体框架文件。");
        return;
      }
      const previewFd = new FormData();
      previewFd.append("file", frameworkFile);
      const preview = await apiPostForm<ExpenseFrameworkPreviewDto>(
        "/api/expense-budget-execution/admin/framework-preview",
        previewFd,
      );
      const confirmText = [
        "即将同步费用整体框架并更新主数据：",
        `框架来源：${preview.source_file}`,
        `预算部门 ${preview.framework.budget_department_count} 行 / 产品部门 ${preview.framework.product_department_count} 行 / 部门预算科目 ${preview.framework.subject_count} 行`,
        `将重建主数据部门 ${preview.master_preview.dept_rows} 行、部门产品映射 ${preview.master_preview.dept_product_mapping_rows} 行`,
      ].join("\n");
      if (!window.confirm(confirmText)) return;
      const syncFd = new FormData();
      syncFd.append("file", frameworkFile);
      syncFd.append("apply_to_master_data", "true");
      const result = await apiPostForm<ExpenseFrameworkSyncResultDto>(
        "/api/expense-budget-execution/admin/framework-sync",
        syncFd,
      );
      alert(
        [
          "费用整体框架同步完成。",
          `预算部门 ${result.framework_rows.budget_departments} 行，产品部门 ${result.framework_rows.product_departments} 行，部门预算科目 ${result.framework_rows.subjects} 行`,
          result.master_apply
            ? `主数据更新：部门 ${result.master_apply.dept_rows} 行，部门产品映射 ${result.master_apply.dept_product_mapping_rows} 行`
            : "本次未更新主数据。",
        ].join("\n"),
      );
      await loadStatus();
    } catch (e) {
      alert(e instanceof Error ? `同步框架失败：${e.message}` : "同步框架失败");
    } finally {
      setSyncingFramework(false);
    }
  };

  const handleSyncActual = async () => {
    if (!actualFile) {
      alert("请先选择“部门费用执行”文件。");
      return;
    }
    setSyncingActual(true);
    try {
      if (!window.confirm("将按上传文件覆盖系统内部月度实际汇总，是否继续？")) return;
      const fd = new FormData();
      fd.append("file", actualFile);
      const result = await apiPostForm<ExpenseActualSyncResultDto>("/api/expense-budget-execution/admin/actual-sync", fd);
      alert(
        [
          "费用执行实际同步完成。",
          `源文件：${result.source_file}`,
          `源明细 ${result.detail_rows} 行`,
          `汇总维度 ${result.monthly_subject_rows} 组`,
          `写入 ${result.saved_cells} 个非零月度单元格`,
        ].join("\n"),
      );
      await loadStatus();
    } catch (e) {
      alert(e instanceof Error ? `同步费用执行失败：${e.message}` : "同步费用执行失败");
    } finally {
      setSyncingActual(false);
    }
  };

  const onFrameworkFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setFrameworkFile(file);
  };

  const onActualFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setActualFile(file);
  };

  return (
    <div className="h-full overflow-auto bg-white p-4">
      <div className="mb-4">
        <h3 className="text-sm font-medium text-gray-800">数据同步管理</h3>
        <p className="mt-1 text-xs text-gray-500">统一管理费用整体框架、费用执行实际等底层数据的同步与状态查看。</p>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void loadStatus()}
          disabled={loading}
          className="px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 disabled:opacity-60 inline-flex items-center gap-1"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新状态
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <div className="border border-gray-200 rounded-lg p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-gray-800">费用整体框架</div>
              <div className="mt-1 text-xs text-gray-500">{frameworkSummary}</div>
              <div className="mt-2 text-xs text-gray-600">
                状态：{formatStatusText(status?.framework_import)}
              </div>
              <div className="mt-1 text-xs text-gray-600">
                主数据应用：{formatStatusText(status?.master_apply)}
              </div>
              <div className="mt-1 text-xs text-gray-600">
                内部表：预算部门 {status?.counts.expense_framework_budget_department ?? 0} / 产品部门{" "}
                {status?.counts.expense_framework_product_department ?? 0} / 部门预算科目{" "}
                {status?.counts.expense_framework_subject ?? 0}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".xlsx,.xls,.xlsm"
                onChange={onFrameworkFileChange}
                className="text-xs text-gray-500"
              />
              <button
                type="button"
                onClick={() => void handlePreviewFramework()}
                disabled={!frameworkFile}
                className="px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
              >
                <Eye className="w-3.5 h-3.5" />
                预览同步结果
              </button>
              <button
                type="button"
                onClick={() => void handleSyncFramework()}
                disabled={syncingFramework || !frameworkFile}
                className="px-3 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 inline-flex items-center gap-1"
              >
                <Upload className="w-3.5 h-3.5" />
                {syncingFramework ? "同步中..." : "同步框架并更新主数据"}
              </button>
            </div>
          </div>
        </div>

        <div className="border border-gray-200 rounded-lg p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-gray-800">费用执行实际</div>
              <div className="mt-1 text-xs text-gray-500">{actualSummary}</div>
              <div className="mt-2 text-xs text-gray-600">
                状态：{formatStatusText(status?.actual_import)}
              </div>
              <div className="mt-1 text-xs text-gray-600">
                内部表：月度执行 {status?.counts.expense_execution_monthly ?? 0}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".xlsx,.xls,.xlsm"
                onChange={onActualFileChange}
                className="text-xs text-gray-500"
              />
              <button
                type="button"
                onClick={() => void handleSyncActual()}
                disabled={syncingActual || !actualFile}
                className="px-3 py-1.5 text-xs rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60 inline-flex items-center gap-1"
              >
                <Upload className="w-3.5 h-3.5" />
                {syncingActual ? "同步中..." : "同步费用执行"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
