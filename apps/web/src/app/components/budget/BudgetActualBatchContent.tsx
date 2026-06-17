import { useEffect, useMemo, useState } from "react";
import { Calculator, Eye, Play, RefreshCw } from "lucide-react";
import {
  type BudgetActualBatchHistoryItemDto,
  type BudgetActualBatchRequestDto,
  type BudgetActualBatchResponseDto,
  type BudgetActualBatchVersionOptionDto,
  fetchBudgetActualBatchHistory,
  fetchBudgetActualBatchVersions,
  previewBudgetActualBatch,
  runBudgetActualBatch,
} from "@/lib/budget/budgetActualBatchApi";
import { getSession } from "@/lib/system/systemApi";
import { listOrgProductRuntimeProducts, type OrgProductRuntimeProductDto } from "@/lib/expense/masterDataApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

type OrgProductMetricNodeDto = {
  code?: string;
  name?: string;
  children?: OrgProductMetricNodeDto[];
};

type OrgProductMetricSnapshotDto = {
  entities: Array<{
    entity_code: string;
    entity_name?: string;
    tables: Array<{
      table_name: string;
      metrics: OrgProductMetricNodeDto[];
    }>;
  }>;
};

type OrgProductMetricRef = {
  sourceRef: string;
  metricCode: string;
  metricName: string;
  dataAcctCode: string;
};

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function productLabel(product: OrgProductRuntimeProductDto): string {
  return `${product.product_code} ${product.product_name}`;
}

function formatTime(value: string): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 16).replace("T", " ");
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function budgetActualLabel(values: number[]): string {
  const labels = values
    .map((value) => (value === 0 ? "预算数" : value === 1 ? "实际数" : ""))
    .filter(Boolean);
  return labels.length > 0 ? labels.join("、") : "-";
}

function rollupMethodLabel(value: string): string {
  if (value === "SUM") return "加总";
  if (value === "FORMULA") return "公式";
  return value || "-";
}

function sourceCodesLabel(codes: string[]): string {
  if (codes.length === 0) return "-";
  if (codes.length <= 3) return codes.join("、");
  return `${codes.slice(0, 3).join("、")} 等 ${codes.length} 个`;
}

function metricCodeFromSourceRef(sourceRef: string): string {
  const parts = sourceRef.split(":");
  return parts.length >= 3 ? parts[2] : sourceRef;
}

function metricCodesLabel(codes: string[], refsByCode: Map<string, OrgProductMetricRef[]>): string {
  const labels = codes.map((code) => refsByCode.get(normalizeCode(code))?.[0]?.metricCode ?? code);
  return sourceCodesLabel(labels);
}

function normalizeCode(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

export function BudgetActualBatchContent() {
  const [versionOptions, setVersionOptions] = useState<BudgetActualBatchVersionOptionDto[]>([]);
  const [products, setProducts] = useState<OrgProductRuntimeProductDto[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [budgetYear, setBudgetYear] = useState<number | null>(null);
  const [productCode, setProductCode] = useState("ALL");
  const [includeBudget, setIncludeBudget] = useState(true);
  const [includeActual, setIncludeActual] = useState(true);
  const [loadingAction, setLoadingAction] = useState<"init" | "preview" | "run" | null>("init");
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<BudgetActualBatchResponseDto | null>(null);
  const [result, setResult] = useState<BudgetActualBatchResponseDto | null>(null);
  const [history, setHistory] = useState<BudgetActualBatchHistoryItemDto[]>([]);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const rows = await fetchBudgetActualBatchHistory(30);
      setHistory(rows);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadOrgProductMetricSnapshot = async () => {
    const snapshot = await (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>).catch(() => ({ entities: [] }));
    setOrgProductMetricSnapshot(snapshot);
  };

  useEffect(() => {
    void (async () => {
      try {
        setLoadingAction("init");
        const [session, versions, productRows] = await Promise.all([
          getSession(),
          fetchBudgetActualBatchVersions(),
          listOrgProductRuntimeProducts(),
          loadOrgProductMetricSnapshot(),
        ]);
        await loadHistory();
        setBudgetYear(session.budget_year);
        setVersionOptions(versions);
        setVersionId((prev) => {
          if (prev && versions.some((row) => row.version_id === prev)) return prev;
          if (versions.some((row) => row.version_id === session.version_id)) return session.version_id;
          return versions[0]?.version_id ?? null;
        });
        setProducts(productRows);
      } catch (e) {
        setError(e instanceof Error ? e.message : "初始化跑批页面失败");
      } finally {
        setLoadingAction(null);
      }
    })();
  }, []);

  const selectedVersion = useMemo(
    () => versionOptions.find((row) => row.version_id === versionId) ?? null,
    [versionId, versionOptions]
  );

  const selectableProducts = useMemo(
    () => [...products].sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN")),
    [products]
  );

  const buildPayload = (): BudgetActualBatchRequestDto => {
    const budgetActuals = [
      includeBudget ? 0 : null,
      includeActual ? 1 : null,
    ].filter((value): value is number => value !== null);
    return {
      product_code: productCode,
      version_id: versionId,
      budget_actuals: budgetActuals,
      run_formula: true,
      rebuild_summary: true,
      sync_compare: true,
      rebuild_aggregate: true,
    };
  };

  const runPreview = async () => {
    setError(null);
    setResult(null);
    try {
      setLoadingAction("preview");
      const response = await previewBudgetActualBatch(buildPayload());
      setPreview(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : "预览失败");
    } finally {
      setLoadingAction(null);
    }
  };

  const runBatch = async () => {
    setError(null);
    try {
      setLoadingAction("run");
      const response = await runBudgetActualBatch(buildPayload());
      setResult(response);
      setPreview(response);
      await loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "跑批失败");
    } finally {
      setLoadingAction(null);
    }
  };

  const activeStats = result ?? preview;
  const actionDisabled = loadingAction !== null || !versionId || (!includeBudget && !includeActual);
  const orgProductRefsByDataAcctCode = useMemo(() => {
    const refsByCode = new Map<string, OrgProductMetricRef[]>();
    const seen = new Set<string>();
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = normalizeCode(entity.entity_code);
      for (const table of entity.tables ?? []) {
        const walk = (metrics: OrgProductMetricNodeDto[]) => {
          for (const metric of metrics) {
            const metricCode = normalizeCode(metric.code);
            const dataAcctCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            if (metricCode && dataAcctCode) {
              const sourceRef = `${entityCode}:${table.table_name}:${metricCode}`;
              const key = `${sourceRef}:${dataAcctCode}`;
              if (!seen.has(key)) {
                seen.add(key);
                const current = refsByCode.get(dataAcctCode) ?? [];
                current.push({
                  sourceRef,
                  metricCode: metricCodeFromSourceRef(sourceRef),
                  metricName: String(metric.name || dataAcctCode),
                  dataAcctCode,
                });
                refsByCode.set(dataAcctCode, current);
              }
            }
            if (metric.children?.length) walk(metric.children);
          }
        };
        walk(table.metrics ?? []);
      }
    }
    for (const refs of refsByCode.values()) {
      refs.sort((a, b) => a.sourceRef.localeCompare(b.sourceRef, "zh-CN"));
    }
    return refsByCode;
  }, [orgProductMetricSnapshot]);

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">
            <Calculator className="w-4 h-4" />
            预算事实刷新跑批
            {budgetYear ? `（${budgetYear}）` : ""}
          </h3>
          <div className="mt-0.5 text-[11px] text-gray-500">
            本页只刷新公式、指标父节点、汇总和对比读模型；人工预算事实统一从“机构及产品数据录入”进入。
          </div>
        </div>
        {selectedVersion ? (
          <span className="bb-grid-chip">
            版本 {selectedVersion.version_id} · {selectedVersion.version_name}
          </span>
        ) : null}
      </div>

      <div className="bb-toolbar flex-nowrap overflow-x-auto">
        <label className="flex shrink-0 items-center gap-1 text-xs text-[var(--bb-text-muted)]">
          版本
          <select
            value={versionId ?? ""}
            onChange={(e) => {
              setVersionId(e.target.value ? Number(e.target.value) : null);
              setPreview(null);
              setResult(null);
            }}
            className="bb-select min-w-56"
          >
            {versionOptions.length === 0 ? (
              <option value="">暂无版本</option>
            ) : (
              versionOptions.map((version) => (
                <option key={version.version_id} value={version.version_id}>
                  {version.version_id} - {version.version_name}（当前月 {version.current_month}）
                </option>
              ))
            )}
          </select>
        </label>
        <label className="flex shrink-0 items-center gap-1 text-xs text-[var(--bb-text-muted)]">
          产品范围
          <select
            value={productCode}
            onChange={(e) => {
              setProductCode(e.target.value);
              setPreview(null);
              setResult(null);
            }}
            className="bb-select min-w-56"
          >
            <option value="ALL">全部明细产品</option>
            {selectableProducts.map((product) => (
              <option key={product.product_code} value={product.product_code}>
                {" ".repeat(Math.max(0, product.level - 1) * 2)}
                {productLabel(product)}
              </option>
            ))}
          </select>
        </label>
        <label className="bb-grid-chip shrink-0">
          <input
            type="checkbox"
            checked={includeBudget}
            onChange={(e) => setIncludeBudget(e.target.checked)}
          />
          预算数
        </label>
        <label className="bb-grid-chip shrink-0">
          <input
            type="checkbox"
            checked={includeActual}
            onChange={(e) => setIncludeActual(e.target.checked)}
          />
          实际数
        </label>
        <div className="flex-1" />
        <button
          type="button"
          disabled={actionDisabled}
          onClick={() => void runPreview()}
          className="bb-btn bb-btn-secondary shrink-0"
        >
          {loadingAction === "preview" ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
          预览
        </button>
        <button
          type="button"
          disabled={actionDisabled}
          onClick={() => void runBatch()}
          className="bb-btn bb-btn-primary shrink-0"
        >
          {loadingAction === "run" ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          执行跑批
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <section className="bb-panel flex min-h-0 flex-[1.2] flex-col overflow-hidden">
          <div className="bb-panel-header">
            <div className="bb-panel-title">跑批结果</div>
            {activeStats ? <span className="bb-grid-chip">{activeStats.mode === "run" ? "已执行" : "已预览"}</span> : null}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {error ? (
              <div className="mb-3 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
            ) : null}
            {loadingAction === "init" ? (
              <div className="text-xs text-[var(--bb-text-muted)]">正在加载...</div>
            ) : activeStats ? (
              <>
                <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">明细产品</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.product_count)}
                    </div>
                  </div>
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">指标数</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.metric_count ?? activeStats.data_account_count)}
                    </div>
                  </div>
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">公式任务</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.formula_task_count)}
                    </div>
                  </div>
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">公式单元格</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.formula_cell_count)}
                    </div>
                  </div>
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">指标父节点任务</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.metric_rollup_task_count)}
                    </div>
                  </div>
                  <div className="rounded border border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] p-3">
                    <div className="text-[11px] text-[var(--bb-text-muted)]">父节点单元格</div>
                    <div className="mt-1 text-lg font-semibold text-[var(--bb-text-strong)]">
                      {formatCount(activeStats.metric_rollup_cell_count)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 overflow-hidden rounded border border-[var(--bb-border-soft)]">
                  <table className="bb-table bb-table-dense w-full table-fixed">
                    <colgroup>
                      <col className="w-56" />
                      <col />
                    </colgroup>
                    <tbody>
                      <tr>
                        <td className="w-56 bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">手工补录覆盖单元格</td>
                        <td className="px-3 py-2">{formatCount(activeStats.manual_override_cell_count)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">公式重算写入单元格</td>
                        <td className="px-3 py-2">{formatCount(activeStats.formula_rows_recalculated)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">父节点 rollup 写入单元格</td>
                        <td className="px-3 py-2">{formatCount(activeStats.metric_rollup_cells_written)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">预算汇总刷新行数</td>
                        <td className="px-3 py-2">{formatCount(activeStats.summary_rows_rebuilt)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">预算透视聚合行数</td>
                        <td className="px-3 py-2">{formatCount(activeStats.budget_aggregate_rows_rebuilt)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">展示对比同步行数</td>
                        <td className="px-3 py-2">{formatCount(activeStats.compare_rows_inserted)}</td>
                      </tr>
                      <tr>
                        <td className="bg-[var(--bb-bg-subtle)] px-3 py-2 text-[var(--bb-text-muted)]">对比透视聚合行数</td>
                        <td className="px-3 py-2">{formatCount(activeStats.compare_aggregate_rows_rebuilt)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {activeStats.metric_rollup_audit_items.length > 0 ? (
                  <div className="mt-3 overflow-hidden rounded border border-[var(--bb-border-soft)]">
                    <div className="border-b border-[var(--bb-border-soft)] bg-[var(--bb-bg-subtle)] px-3 py-2 text-xs font-medium text-[var(--bb-text-strong)]">
                      指标树父节点预览
                      {activeStats.metric_rollup_audit_truncated ? "（仅显示前 200 条）" : ""}
                    </div>
                    <div className="max-h-72 overflow-auto">
                      <table className="bb-table bb-table-dense w-full min-w-[1120px] table-fixed">
                        <colgroup>
                          <col className="w-32" />
                          <col className="w-44" />
                          <col className="w-52" />
                          <col className="w-24" />
                          <col className="w-20" />
                          <col className="w-20" />
                          <col className="w-24" />
                          <col />
                        </colgroup>
                        <thead className="sticky top-0 z-10 bg-gray-100">
                          <tr>
                            <th className="px-3 py-2 text-left">父节点</th>
                            <th className="px-3 py-2 text-left">写入指标编码</th>
                            <th className="px-3 py-2 text-left">机构产品来源</th>
                            <th className="px-3 py-2 text-left">产品范围</th>
                            <th className="px-3 py-2 text-left">方法</th>
                            <th className="px-3 py-2 text-left">类型</th>
                            <th className="px-3 py-2 text-right">单元格</th>
                            <th className="px-3 py-2 text-left">来源</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeStats.metric_rollup_audit_items.map((item) => {
                            const refs = orgProductRefsByDataAcctCode.get(normalizeCode(item.target_data_acct_code)) ?? [];
                            const targetMetricCode = refs[0]?.metricCode ?? item.target_metric_code ?? item.target_data_acct_code;
                            const sourceMetricCodes = item.source_metric_codes ?? item.source_codes;
                            return (
                              <tr key={`${item.target_data_acct_code}-${item.budget_actual}`}>
                                <td className="truncate px-3 py-2 font-mono text-[11px]">{item.node_code}</td>
                                <td
                                  className="truncate px-3 py-2 font-mono text-[11px]"
                                  title={item.target_data_acct_code === targetMetricCode ? targetMetricCode : `${targetMetricCode} / ${item.target_data_acct_code}`}
                                >
                                  {targetMetricCode}
                                </td>
                                <td
                                  className="truncate px-3 py-2 text-[11px]"
                                  title={refs.map((ref) => `${ref.metricCode} ${ref.metricName} -> ${ref.dataAcctCode}`).join("\n")}
                                >
                                  {refs.length > 0 ? (
                                    <span className="inline-flex max-w-full items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
                                      <span className="truncate font-mono">{refs[0].metricCode}</span>
                                      {refs.length > 1 ? <span className="shrink-0 text-gray-500">+{refs.length - 1}</span> : null}
                                    </span>
                                  ) : (
                                    <span className="text-[var(--bb-text-muted)]">-</span>
                                  )}
                                </td>
                                <td className="truncate px-3 py-2">{item.scope_code}</td>
                                <td className="truncate px-3 py-2">{rollupMethodLabel(item.method)}</td>
                                <td className="truncate px-3 py-2">{budgetActualLabel([item.budget_actual])}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.cell_count)}</td>
                                <td className="truncate px-3 py-2" title={item.formula || sourceMetricCodes.join("、")}>
                                  {item.method === "FORMULA" ? item.formula || "-" : metricCodesLabel(sourceMetricCodes, orgProductRefsByDataAcctCode)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                {activeStats.warnings.length > 0 ? (
                  <div className="mt-3 space-y-1">
                    {activeStats.warnings.map((warning) => (
                      <div key={warning} className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        {warning}
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-xs text-[var(--bb-text-muted)]">暂无跑批结果</div>
            )}
          </div>
        </section>

        <section className="bb-panel flex h-72 min-h-56 flex-col overflow-hidden">
          <div className="bb-panel-header">
            <div className="bb-panel-title">执行历史</div>
            <button
              type="button"
              onClick={() => void loadHistory()}
              className="bb-btn bb-btn-secondary h-7 px-2"
              disabled={historyLoading}
            >
              <RefreshCw className={`w-3 h-3 ${historyLoading ? "animate-spin" : ""}`} />
              刷新
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="bb-table bb-table-dense w-full min-w-[1240px] table-fixed">
              <colgroup>
                <col className="w-36" />
                <col className="w-28" />
                <col className="w-40" />
                <col className="w-28" />
                <col className="w-44" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
              </colgroup>
              <thead className="sticky top-0 z-10 bg-gray-100">
                <tr>
                  <th className="px-3 py-2 text-left">执行时间</th>
                  <th className="px-3 py-2 text-left">版本</th>
                  <th className="px-3 py-2 text-left">产品范围</th>
                  <th className="px-3 py-2 text-left">数据类型</th>
                  <th className="px-3 py-2 text-left">动作</th>
                  <th className="px-3 py-2 text-right">公式写入</th>
                  <th className="px-3 py-2 text-right">汇总行数</th>
                  <th className="px-3 py-2 text-right">预算聚合</th>
                  <th className="px-3 py-2 text-right">对比行数</th>
                  <th className="px-3 py-2 text-right">对比聚合</th>
                  <th className="px-3 py-2 text-right">影响行数</th>
                  <th className="px-3 py-2 text-left">操作人</th>
                </tr>
              </thead>
              <tbody>
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="px-3 py-8 text-center text-xs text-[var(--bb-text-muted)]">
                      {historyLoading ? "正在加载..." : "暂无执行历史"}
                    </td>
                  </tr>
                ) : (
                  history.map((item) => {
                    const actions = [
                      item.run_formula ? "公式落库" : "",
                      item.rebuild_summary ? "刷新汇总" : "",
                      item.sync_compare ? "同步对比" : "",
                      item.rebuild_aggregate ? "生成聚合表" : "",
                    ].filter(Boolean);
                    return (
                      <tr key={item.log_id}>
                        <td className="truncate px-3 py-2 whitespace-nowrap">{formatTime(item.create_time)}</td>
                        <td className="truncate px-3 py-2 whitespace-nowrap">
                          {item.budget_year ?? "-"} / V{item.version_id ?? "-"}
                        </td>
                        <td className="truncate px-3 py-2 whitespace-nowrap">
                          {item.product_code === "ALL" ? "全部明细产品" : item.product_code || "-"}
                          {item.product_count > 0 ? `（${formatCount(item.product_count)}）` : ""}
                        </td>
                        <td className="truncate px-3 py-2 whitespace-nowrap">{budgetActualLabel(item.budget_actuals)}</td>
                        <td className="truncate px-3 py-2 whitespace-nowrap">{actions.length > 0 ? actions.join("、") : "-"}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.formula_rows_recalculated)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.summary_rows_rebuilt)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.budget_aggregate_rows_rebuilt)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.compare_rows_inserted)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.compare_aggregate_rows_rebuilt)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCount(item.affected_rows)}</td>
                        <td className="truncate px-3 py-2 whitespace-nowrap">{item.user_id ?? "-"}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
