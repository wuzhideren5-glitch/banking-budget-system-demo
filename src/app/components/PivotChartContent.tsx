import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  apiGet,
  apiPostBlob,
  apiPost,
  type ChartBarRequestDto,
  type ChartPptExportRequestDto,
  type ChartReportTreeNodeDto,
  type ChartStackedRequestDto,
  type ChartStackedResponseDto,
  type ChartVersionItemDto,
  type ChartVersionOptionsResponseDto,
  type ChartVersionSelectionDto,
} from "@/lib/api";

type ChartTabId = "bar" | "stacked" | "line" | "pie";

type FlatReportNode = {
  report_acct_code: string;
  report_acct_name: string;
  is_summary: boolean;
  depth: number;
};

const chartTabs: Array<{ id: ChartTabId; label: string }> = [
  { id: "bar", label: "柱状图" },
  { id: "stacked", label: "堆积图" },
  { id: "line", label: "曲线图" },
  { id: "pie", label: "饼环图" },
];

const palette = ["#3B82F6", "#06B6D4", "#10B981", "#F59E0B", "#F97316", "#A855F7", "#EF4444"];

function formatValue(v: number): string {
  return Number(v).toFixed(2);
}

function toNumber(value: unknown): number {
  return typeof value === "number" ? value : Number(value ?? 0);
}

function formatByType(value: unknown, valueType?: string | null): string {
  const numeric = toNumber(value);
  if (valueType === "百分比") return `${numeric.toFixed(2)}%`;
  return numeric.toFixed(2);
}

function lightenHex(hexColor: string, ratio: number): string {
  const text = hexColor.replace("#", "");
  if (text.length !== 6) return hexColor;
  const clamp = Math.max(0, Math.min(1, ratio));
  const toPart = (start: string) => {
    const base = Number.parseInt(start, 16);
    const mixed = Math.round(base + (255 - base) * clamp);
    return mixed.toString(16).padStart(2, "0");
  };
  return `#${toPart(text.slice(0, 2))}${toPart(text.slice(2, 4))}${toPart(text.slice(4, 6))}`;
}

function flattenReportTree(nodes: ChartReportTreeNodeDto[], depth = 0): FlatReportNode[] {
  const rows: FlatReportNode[] = [];
  for (const node of nodes) {
    rows.push({
      report_acct_code: node.report_acct_code,
      report_acct_name: node.report_acct_name,
      is_summary: node.is_summary,
      depth,
    });
    rows.push(...flattenReportTree(node.children ?? [], depth + 1));
  }
  return rows;
}

function findReportNode(nodes: ChartReportTreeNodeDto[], code: string): ChartReportTreeNodeDto | null {
  for (const n of nodes) {
    if (n.report_acct_code === code) return n;
    const found = findReportNode(n.children ?? [], code);
    if (found) return found;
  }
  return null;
}

export function PivotChartContent() {
  const [activeTab, setActiveTab] = useState<ChartTabId>("bar");
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [reportNodes, setReportNodes] = useState<FlatReportNode[]>([]);
  const [reportTree, setReportTree] = useState<ChartReportTreeNodeDto[]>([]);
  const [versionOptions, setVersionOptions] = useState<ChartVersionItemDto[]>([]);

  const [selectedReportCode, setSelectedReportCode] = useState("");
  const [useAllVersions, setUseAllVersions] = useState(true);
  const [manualYear, setManualYear] = useState<number | "">("");
  const [manualVersionKey, setManualVersionKey] = useState("");
  const [singleVersionGranularity, setSingleVersionGranularity] = useState<"month" | "quarter">("month");
  const [stackMode, setStackMode] = useState<"absolute" | "percent">("absolute");
  const [barCompareScope, setBarCompareScope] = useState<"self" | "children">("self");
  const [lineCompareScope, setLineCompareScope] = useState<"self" | "children">("self");
  const [pieCompareScope, setPieCompareScope] = useState<"self" | "children">("children");
  const [pieDimension, setPieDimension] = useState<"segments" | "periods">("segments");
  const [pieAllVersionMode, setPieAllVersionMode] = useState<"segments" | "segments_by_year">("segments");
  const [pieSelectedYear, setPieSelectedYear] = useState("");
  const [pieTopN, setPieTopN] = useState(8);

  const [loadingData, setLoadingData] = useState(false);
  const [exportingPpt, setExportingPpt] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [stackedLoadError, setStackedLoadError] = useState<string | null>(null);
  const [barLoadError, setBarLoadError] = useState<string | null>(null);
  const [lineLoadError, setLineLoadError] = useState<string | null>(null);
  const [pieLoadError, setPieLoadError] = useState<string | null>(null);
  const [stackedData, setStackedData] = useState<ChartStackedResponseDto | null>(null);
  const [barData, setBarData] = useState<ChartStackedResponseDto | null>(null);
  const [lineData, setLineData] = useState<ChartStackedResponseDto | null>(null);
  const [pieData, setPieData] = useState<ChartStackedResponseDto | null>(null);

  const yearOptions = useMemo(() => {
    const ys = new Set<number>();
    for (const o of versionOptions) ys.add(o.year);
    return Array.from(ys).sort((a, b) => b - a);
  }, [versionOptions]);

  const resolvedManualYear = useMemo(() => {
    if (useAllVersions || yearOptions.length === 0) return null;
    if (manualYear !== "" && yearOptions.includes(manualYear as number)) return manualYear as number;
    return yearOptions[0];
  }, [useAllVersions, manualYear, yearOptions]);

  const versionsForManualYear = useMemo(() => {
    if (resolvedManualYear == null) return [];
    return versionOptions.filter((o) => o.year === resolvedManualYear);
  }, [versionOptions, resolvedManualYear]);

  const selectedManualVersions = useMemo<ChartVersionSelectionDto[]>(() => {
    if (!manualVersionKey) return [];
    const [db, vid] = manualVersionKey.split(":");
    if (!db || !vid) return [];
    const data_file_id = Number(db);
    const version_id = Number(vid);
    const ok = versionOptions.some((o) => o.data_file_id === data_file_id && o.version_id === version_id);
    return ok ? [{ data_file_id, version_id }] : [];
  }, [manualVersionKey, versionOptions]);

  const selectedManualVersionOption = useMemo(() => {
    if (!manualVersionKey) return null;
    const [dbText, versionText] = manualVersionKey.split(":");
    const dataFileId = Number(dbText);
    const versionId = Number(versionText);
    if (!Number.isFinite(dataFileId) || !Number.isFinite(versionId)) return null;
    return versionOptions.find(
      (opt) => opt.data_file_id === dataFileId && opt.version_id === versionId,
    ) ?? null;
  }, [manualVersionKey, versionOptions]);

  const isSingleManualVersion = !useAllVersions && selectedManualVersions.length === 1;

  const selectedReportNode = useMemo(
    () => findReportNode(reportTree, selectedReportCode),
    [reportTree, selectedReportCode],
  );
  const selectedReportHasChildren = (selectedReportNode?.children?.length ?? 0) > 0;
  const selectedReportIsSummary = selectedReportNode?.is_summary ?? true;
  const canUseChildrenComparison = selectedReportHasChildren || !selectedReportIsSummary;
  const canUsePieChildrenComparison = selectedReportIsSummary || canUseChildrenComparison;

  const chartData = useMemo(() => {
    if (!stackedData) return [];
    return stackedData.categories.map((category, idx) => {
      const row: Record<string, string | number> = { category };
      for (const series of stackedData.series) {
        row[series.key] = Number(series.values[idx] ?? 0);
      }
      return row;
    });
  }, [stackedData]);

  const barChartData = useMemo(() => {
    if (!barData) return [];
    return barData.categories.map((category, idx) => {
      const row: Record<string, string | number> = { category };
      for (const series of barData.series) {
        row[series.key] = Number(series.values[idx] ?? 0);
      }
      return row;
    });
  }, [barData]);

  const lineChartData = useMemo(() => {
    if (!lineData) return [];
    return lineData.categories.map((category, idx) => {
      const row: Record<string, string | number> = { category };
      for (const series of lineData.series) {
        row[series.key] = Number(series.values[idx] ?? 0);
      }
      return row;
    });
  }, [lineData]);

  const barSeriesTypeMap = useMemo(() => {
    if (!barData) return new Map<string, string | null | undefined>();
    return new Map(barData.series.map((series) => [series.key, series.value_type]));
  }, [barData]);

  const barMatrixTypeMap = useMemo(() => {
    if (!barData) return new Map<string, string | null | undefined>();
    return new Map(barData.matrix_rows.map((row) => [row.row_label, row.value_type]));
  }, [barData]);

  const barAllPercent = useMemo(() => {
    if (!barData || barData.series.length === 0) return false;
    return barData.series.every((series) => series.value_type === "百分比");
  }, [barData]);

  const pieSlices = useMemo(() => {
    if (!pieData || pieData.series.length === 0) return [];
    const raw = !useAllVersions && pieDimension === "periods"
      ? (() => {
          const first = pieData.series[0];
          return pieData.categories.map((name, idx) => ({
            name,
            value: Number(first.values[idx] ?? 0),
          }));
        })()
      : useAllVersions && pieAllVersionMode === "segments"
        ? (() => {
            const idxByYear = pieData.categories.findIndex((y) => y === pieSelectedYear);
            const yearIdx = idxByYear >= 0 ? idxByYear : Math.max(0, pieData.categories.length - 1);
            return pieData.series.map((series) => ({
              name: series.label,
              value: Number(series.values[yearIdx] ?? 0),
            }));
          })()
        : pieData.series.map((series) => ({
            name: series.label,
            value: series.values.reduce((acc, cur) => acc + Number(cur || 0), 0),
          }));
    const sorted = raw
      .filter((item) => Math.abs(item.value) > 0.000001)
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    if (sorted.length <= pieTopN) return sorted;
    const head = sorted.slice(0, pieTopN);
    const rest = sorted.slice(pieTopN);
    const otherTotal = rest.reduce((acc, cur) => acc + cur.value, 0);
    return [...head, { name: "其他", value: otherTotal }];
  }, [pieData, pieDimension, pieTopN, useAllVersions, pieAllVersionMode, pieSelectedYear]);

  const pieYearRings = useMemo(() => {
    if (!pieData || pieData.series.length === 0) return [];
    if (!useAllVersions || pieAllVersionMode !== "segments_by_year") return [];
    const totalRings = pieData.categories.length;
    return pieData.categories.map((yearLabel, yearIdx) => {
      const lightenRatio = totalRings <= 1 ? 0 : (yearIdx / Math.max(1, totalRings - 1)) * 0.45;
      const yearRingColor = lightenHex("#2563EB", lightenRatio);
      const raw = pieData.series
        .map((series, idx) => ({
          name: series.label,
          value: Number(series.values[yearIdx] ?? 0),
          color: lightenHex(palette[idx % palette.length], lightenRatio),
          year: yearLabel,
        }))
        .filter((item) => Math.abs(item.value) > 0.000001)
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

      const top = raw.slice(0, pieTopN);
      const rest = raw.slice(pieTopN);
      const otherValue = rest.reduce((acc, cur) => acc + cur.value, 0);
      const data = otherValue
        ? [...top, { name: "其他", value: otherValue, color: "#9CA3AF", year: yearLabel }]
        : top;
      const total = data.reduce((acc, cur) => acc + cur.value, 0);
      return {
        year: yearLabel,
        ringColor: yearRingColor,
        total,
        ringIndex: yearIdx,
        ringCount: totalRings,
        data: data.map((item) => ({
          ...item,
          percent: total ? item.value / total : 0,
        })),
      };
    });
  }, [pieData, pieTopN, useAllVersions, pieAllVersionMode]);

  const pieYearTotals = useMemo(() => {
    if (!pieData) return [];
    const totals = Array.from({ length: pieData.categories.length }, () => 0);
    for (const series of pieData.series) {
      for (let i = 0; i < totals.length; i += 1) {
        totals[i] += Number(series.values[i] ?? 0);
      }
    }
    return totals;
  }, [pieData]);

  const pieMatrixRowsByYear = useMemo(() => {
    if (!pieData || !useAllVersions) return [];
    const rows = pieData.series.map((series) => ({
      label: series.label,
      values: pieData.categories.map((_, idx) => Number(series.values[idx] ?? 0)),
    }));
    const sorted = [...rows].sort(
      (a, b) =>
        b.values.reduce((acc, cur) => acc + Math.abs(cur), 0) -
        a.values.reduce((acc, cur) => acc + Math.abs(cur), 0),
    );
    if (sorted.length <= pieTopN) return sorted;
    const head = sorted.slice(0, pieTopN);
    const rest = sorted.slice(pieTopN);
    const otherValues = pieData.categories.map((_, idx) =>
      rest.reduce((acc, row) => acc + Number(row.values[idx] ?? 0), 0),
    );
    return [...head, { label: "其他", values: otherValues }];
  }, [pieData, useAllVersions, pieTopN]);

  const pieTotalValue = useMemo(
    () => pieSlices.reduce((acc, cur) => acc + Number(cur.value || 0), 0),
    [pieSlices],
  );

  const currentChartHasData = useMemo(() => {
    if (activeTab === "bar") return !!barData?.categories?.length && !!barData.series.length;
    if (activeTab === "stacked") return !!stackedData?.categories?.length && !!stackedData.series.length;
    if (activeTab === "line") return !!lineData?.categories?.length && !!lineData.series.length;
    if (activeTab === "pie") {
      if (useAllVersions && pieAllVersionMode === "segments_by_year") {
        return pieYearRings.some((ring) => ring.data.length > 0);
      }
      return pieSlices.length > 0;
    }
    return false;
  }, [activeTab, barData, stackedData, lineData, useAllVersions, pieAllVersionMode, pieYearRings, pieSlices]);

  const buildPptExportPayload = (): ChartPptExportRequestDto | null => {
    const chartLabelMap: Record<ChartTabId, string> = {
      bar: "柱状图",
      stacked: "堆积图",
      line: "曲线图",
      pie: "饼环图",
    };
    const reportLabel = selectedReportNode
      ? `${selectedReportNode.report_acct_code} ${selectedReportNode.report_acct_name}`
      : selectedReportCode || "未选择报告科目";
    const versionScopeLabel = useAllVersions
      ? "全部展示对比年度"
      : selectedManualVersionOption
        ? `${selectedManualVersionOption.year}年 ${selectedManualVersionOption.version_name}`
        : "单版本";
    const granularityLabel = useAllVersions
      ? "年度对比"
      : singleVersionGranularity === "quarter"
        ? "按季度"
        : "按月度";
    const title = `数据透视图 - ${chartLabelMap[activeTab]} - ${reportLabel}`;
    const subtitle = `版本口径：${versionScopeLabel} | 统计粒度：${granularityLabel}`;

    if (activeTab === "bar") {
      if (!barData || !barData.categories.length || !barData.series.length) return null;
      return {
        chart_type: "bar",
        title,
        subtitle,
        categories: barData.categories,
        series: barData.series.map((s) => ({ name: s.label, values: s.values.map((v) => Number(v ?? 0)) })),
        matrix_headers: barData.matrix_headers,
        matrix_rows: barData.matrix_rows.map((row) => ({
          label: row.row_label,
          values: row.values.map((v) => formatByType(v, barMatrixTypeMap.get(row.row_label))),
        })),
      };
    }
    if (activeTab === "stacked") {
      if (!stackedData || !stackedData.categories.length || !stackedData.series.length) return null;
      return {
        chart_type: "stacked",
        title,
        subtitle: `${subtitle} | 展示模式：${stackMode === "percent" ? "占比" : "累计值"}`,
        categories: stackedData.categories,
        series: stackedData.series.map((s) => ({ name: s.label, values: s.values.map((v) => Number(v ?? 0)) })),
        matrix_headers: stackedData.matrix_headers,
        matrix_rows: stackedData.matrix_rows.map((row) => ({
          label: row.row_label,
          values: row.values.map((v) => (stackMode === "percent" ? `${v.toFixed(2)}%` : v.toFixed(2))),
        })),
      };
    }
    if (activeTab === "line") {
      if (!lineData || !lineData.categories.length || !lineData.series.length) return null;
      return {
        chart_type: "line",
        title,
        subtitle,
        categories: lineData.categories,
        series: lineData.series.map((s) => ({ name: s.label, values: s.values.map((v) => Number(v ?? 0)) })),
        matrix_headers: lineData.matrix_headers,
        matrix_rows: lineData.matrix_rows.map((row) => ({
          label: row.row_label,
          values: row.values.map((v) => formatByType(v, row.value_type)),
        })),
      };
    }
    if (activeTab === "pie") {
      if (useAllVersions && pieAllVersionMode === "segments_by_year") {
        if (!pieYearRings.length) return null;
        const categories = Array.from(
          new Set(pieYearRings.flatMap((ring) => ring.data.map((item) => item.name))),
        );
        if (!categories.length) return null;
        return {
          chart_type: "doughnut",
          title: `${title}（下级科目占比年度比较）`,
          subtitle,
          categories,
          series: pieYearRings.map((ring) => ({
            name: ring.year,
            values: categories.map((cat) => {
              const item = ring.data.find((d) => d.name === cat);
              return Number(item?.value ?? 0);
            }),
          })),
          matrix_headers: [
            ...(pieData?.categories.map((year) => `${year} 数值`) ?? []),
            ...(pieData?.categories.map((year) => `${year} 占比`) ?? []),
          ],
          matrix_rows: pieMatrixRowsByYear.map((row) => ({
            label: row.label,
            values: [
              ...row.values.map((v) => formatValue(v)),
              ...row.values.map((v, idx) => {
                const total = pieYearTotals[idx] ?? 0;
                const pct = total ? (v / total) * 100 : 0;
                return `${pct.toFixed(2)}%`;
              }),
            ],
          })),
        };
      }
      if (!pieSlices.length) return null;
      return {
        chart_type: "pie",
        title,
        subtitle: useAllVersions ? `${subtitle} | 年度：${pieSelectedYear}` : subtitle,
        categories: pieSlices.map((s) => s.name),
        series: [
          {
            name: "占比",
            values: pieSlices.map((s) => Number(s.value ?? 0)),
          },
        ],
        matrix_headers: ["数值", "占比"],
        matrix_rows: pieSlices.map((item) => {
          const pct = pieTotalValue ? (item.value / pieTotalValue) * 100 : 0;
          return {
            label: item.name,
            values: [formatValue(item.value), `${pct.toFixed(2)}%`],
          };
        }),
      };
    }
    return null;
  };

  const handleExportPpt = async () => {
    const payload = buildPptExportPayload();
    if (!payload) {
      setExportError("当前图表无可导出的数据");
      return;
    }
    setExportError(null);
    setExportingPpt(true);
    try {
      const { blob, filename } = await apiPostBlob("/api/chart/export-ppt", payload);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename ?? "pivot_chart.pptx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "导出PPT失败";
      setExportError(msg);
    } finally {
      setExportingPpt(false);
    }
  };

  useEffect(() => {
    if (!selectedReportIsSummary && barCompareScope === "self") {
      setBarCompareScope("children");
    }
  }, [selectedReportIsSummary, barCompareScope]);

  useEffect(() => {
    if (!selectedReportIsSummary && lineCompareScope === "self") {
      setLineCompareScope("children");
    }
  }, [selectedReportIsSummary, lineCompareScope]);

  useEffect(() => {
    if (!canUsePieChildrenComparison && pieCompareScope === "children") {
      setPieCompareScope("self");
    }
  }, [canUsePieChildrenComparison, pieCompareScope]);

  useEffect(() => {
    if (pieDimension === "segments" && selectedReportIsSummary && pieCompareScope !== "children") {
      setPieCompareScope("children");
    }
  }, [pieDimension, selectedReportIsSummary, pieCompareScope]);

  useEffect(() => {
    if (!pieData || !useAllVersions || pieAllVersionMode !== "segments") return;
    if (pieData.categories.length === 0) return;
    if (!pieSelectedYear || !pieData.categories.includes(pieSelectedYear)) {
      setPieSelectedYear(pieData.categories[pieData.categories.length - 1]);
    }
  }, [pieData, useAllVersions, pieAllVersionMode, pieSelectedYear]);

  const reloadMeta = async (): Promise<void> => {
    setLoadingMeta(true);
    setMetaError(null);
    try {
      const [tree, versions] = await Promise.all([
        apiGet<ChartReportTreeNodeDto[]>("/api/chart/report-tree"),
        apiGet<ChartVersionOptionsResponseDto>("/api/chart/version-options"),
      ]);
      const flat = flattenReportTree(tree);
      setReportTree(tree);
      setReportNodes(flat);
      const defaultNode = flat.find((n) => n.is_summary);
      setSelectedReportCode((prev) => prev || defaultNode?.report_acct_code || "");
      setVersionOptions(versions.options ?? []);
    } catch (e) {
      setMetaError(e instanceof Error ? e.message : "加载图表配置失败");
    } finally {
      setLoadingMeta(false);
    }
  };

  useEffect(() => {
    void reloadMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onSnapshotChanged = () => {
      void reloadMeta();
    };
    window.addEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    return () => {
      window.removeEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadStackedData = async () => {
    if (!selectedReportCode) {
      setStackedLoadError("请先选择报告科目");
      return;
    }
    if (!useAllVersions && selectedManualVersions.length === 0) {
      setStackedLoadError("请选择年度与版本");
      return;
    }
    setLoadingData(true);
    setStackedLoadError(null);
    try {
      const payload: ChartStackedRequestDto = {
        report_acct_code: selectedReportCode,
        use_all_versions: useAllVersions,
        selected_versions: selectedManualVersions,
        single_version_granularity: singleVersionGranularity,
        stack_mode: stackMode,
      };
      const data = await apiPost<ChartStackedResponseDto>("/api/chart/stacked", payload);
      setStackedData(data);
    } catch (e) {
      setStackedLoadError(e instanceof Error ? e.message : "加载堆积图数据失败");
      setStackedData(null);
    } finally {
      setLoadingData(false);
    }
  };

  const loadBarData = async () => {
    if (!selectedReportCode) {
      setBarLoadError("请先选择报告科目");
      return;
    }
    if (!useAllVersions && selectedManualVersions.length === 0) {
      setBarLoadError("请选择年度与版本");
      return;
    }
    setLoadingData(true);
    setBarLoadError(null);
    try {
      const payload: ChartBarRequestDto = {
        report_acct_code: selectedReportCode,
        bar_compare_scope: barCompareScope,
        use_all_versions: useAllVersions,
        selected_versions: selectedManualVersions,
        single_version_granularity: singleVersionGranularity,
      };
      const data = await apiPost<ChartStackedResponseDto>("/api/chart/bar", payload);
      setBarData(data);
    } catch (e) {
      setBarLoadError(e instanceof Error ? e.message : "加载柱状图数据失败");
      setBarData(null);
    } finally {
      setLoadingData(false);
    }
  };

  const loadLineData = async () => {
    if (!selectedReportCode) {
      setLineLoadError("请先选择报告科目");
      return;
    }
    if (!useAllVersions && selectedManualVersions.length === 0) {
      setLineLoadError("请选择年度与版本");
      return;
    }
    setLoadingData(true);
    setLineLoadError(null);
    try {
      const payload: ChartBarRequestDto = {
        report_acct_code: selectedReportCode,
        bar_compare_scope: lineCompareScope,
        use_all_versions: useAllVersions,
        selected_versions: selectedManualVersions,
        single_version_granularity: singleVersionGranularity,
      };
      const data = await apiPost<ChartStackedResponseDto>("/api/chart/bar", payload);
      setLineData(data);
    } catch (e) {
      setLineLoadError(e instanceof Error ? e.message : "加载曲线图数据失败");
      setLineData(null);
    } finally {
      setLoadingData(false);
    }
  };

  const loadPieData = async () => {
    if (!selectedReportCode) {
      setPieLoadError("请先选择报告科目");
      return;
    }
    if (!useAllVersions && selectedManualVersions.length === 0) {
      setPieLoadError("请选择年度与版本");
      return;
    }
    const pieScope: "self" | "children" = useAllVersions
      ? "children"
      : pieDimension === "periods"
        ? "self"
        : pieCompareScope;
    if (pieScope === "children" && !canUsePieChildrenComparison) {
      setPieLoadError("所选报告科目没有下级科目");
      return;
    }
    setLoadingData(true);
    setPieLoadError(null);
    try {
      const payload: ChartBarRequestDto = {
        report_acct_code: selectedReportCode,
        bar_compare_scope: pieScope,
        use_all_versions: useAllVersions,
        selected_versions: selectedManualVersions,
        single_version_granularity: singleVersionGranularity,
      };
      const data = await apiPost<ChartStackedResponseDto>("/api/chart/bar", payload);
      setPieData(data);
    } catch (e) {
      setPieLoadError(e instanceof Error ? e.message : "加载饼图数据失败");
      setPieData(null);
    } finally {
      setLoadingData(false);
    }
  };

  useEffect(() => {
    if (!loadingMeta && selectedReportCode) {
      void loadStackedData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMeta]);

  useEffect(() => {
    if (loadingMeta || !selectedReportCode) return;
    if (activeTab !== "bar") return;
    void loadBarData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMeta, activeTab, selectedReportCode]);

  useEffect(() => {
    if (loadingMeta || !selectedReportCode) return;
    if (activeTab !== "line") return;
    void loadLineData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMeta, activeTab, selectedReportCode]);

  useEffect(() => {
    if (loadingMeta || !selectedReportCode) return;
    if (activeTab !== "pie") return;
    void loadPieData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMeta, activeTab, selectedReportCode, pieDimension, pieAllVersionMode, useAllVersions]);

  const renderBarTab = () => (
    <div className="space-y-3">
      <div className="border border-gray-300 rounded p-3 space-y-3 bg-white">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-gray-700">报告科目</label>
          <select
            value={selectedReportCode}
            onChange={(e) => setSelectedReportCode(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[260px]"
          >
            <option value="">请选择报告科目</option>
            {reportNodes.map((node) => (
              <option
                key={node.report_acct_code}
                value={node.report_acct_code}
              >
                {`${"　".repeat(node.depth)}${node.report_acct_code} ${node.report_acct_name}${
                  node.is_summary ? "" : "（非汇总）"
                }`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={useAllVersions}
              onChange={() => setUseAllVersions(true)}
            />
            全部展示对比年度
          </label>
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={!useAllVersions}
              onChange={() => {
                setUseAllVersions(false);
                setManualVersionKey("");
              }}
            />
            选择年度与版本
          </label>
        </div>

        {!useAllVersions && (
          <div className="flex flex-wrap items-center gap-3">
            {yearOptions.length === 0 ? (
              <span className="text-xs text-gray-500">暂无可用年度数据</span>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">年度</label>
                  <select
                    value={resolvedManualYear != null ? String(resolvedManualYear) : ""}
                    onChange={(e) => {
                      setManualYear(Number(e.target.value));
                      setManualVersionKey("");
                    }}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[120px]"
                  >
                    {yearOptions.map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">版本</label>
                  <select
                    value={manualVersionKey}
                    onChange={(e) => setManualVersionKey(e.target.value)}
                    disabled={versionsForManualYear.length === 0}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[220px] disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="">
                      {versionsForManualYear.length === 0 ? "该年度无版本" : "请选择版本"}
                    </option>
                    {versionsForManualYear.map((opt) => (
                      <option key={`${opt.data_file_id}:${opt.version_id}`} value={`${opt.data_file_id}:${opt.version_id}`}>
                        {`${opt.version_id}-${opt.version_name}`}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-gray-700 shrink-0">比较范围</span>
          <label
            className={`inline-flex items-center gap-1 ${!selectedReportIsSummary ? "text-gray-400" : ""}`}
            title={!selectedReportIsSummary ? "非汇总科目不支持本科目比较" : undefined}
          >
            <input
              type="radio"
              checked={barCompareScope === "self"}
              onChange={() => setBarCompareScope("self")}
              disabled={!selectedReportIsSummary}
            />
            本科目比较
          </label>
          <label
            className="inline-flex items-center gap-1"
          >
            <input
              type="radio"
              checked={barCompareScope === "children"}
              onChange={() => setBarCompareScope("children")}
            />
            下级科目比较
          </label>
          {isSingleManualVersion && (
            <>
              <span className="text-gray-700 shrink-0">比较粒度</span>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "month"}
                  onChange={() => setSingleVersionGranularity("month")}
                />
                月度比较
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "quarter"}
                  onChange={() => setSingleVersionGranularity("quarter")}
                />
                季度比较
              </label>
            </>
          )}
          <button
            type="button"
            onClick={() => void loadBarData()}
            className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 ml-auto shrink-0"
            disabled={loadingData}
          >
            {loadingData ? "加载中..." : "更新图表"}
          </button>
        </div>
      </div>

      {barLoadError && <div className="text-xs text-red-600">{barLoadError}</div>}
      {metaError && <div className="text-xs text-red-600">{metaError}</div>}

      <div className="border border-gray-300 rounded p-3 bg-white">
        <div className="text-xs font-medium text-gray-800 mb-2">柱状图视图</div>
        {loadingMeta ? (
          <div className="text-xs text-gray-500 py-8 text-center">正在加载图表配置...</div>
        ) : !barData || !barData.categories.length ? (
          <div className="text-xs text-gray-500 py-8 text-center">暂无可展示数据</div>
        ) : (
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barChartData} margin={{ left: 16, right: 16, top: 16, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value) => (barAllPercent ? `${toNumber(value).toFixed(2)}%` : toNumber(value).toFixed(2))}
                />
                <Tooltip
                  formatter={(value, name) => formatByType(value, barSeriesTypeMap.get(String(name)))}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, lineHeight: "16px" }}
                  iconSize={10}
                  iconType="square"
                />
                {barData.series.map((s, idx) => (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    name={s.label}
                    fill={palette[idx % palette.length]}
                    maxBarSize={48}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="border border-gray-300 rounded p-3 bg-white overflow-auto">
        <div className="text-xs font-medium text-gray-800 mb-2">图表数据矩阵</div>
        {!barData || !barData.matrix_rows.length ? (
          <div className="text-xs text-gray-500 py-2">暂无数据</div>
        ) : (
          <table className="w-full text-xs border-collapse min-w-[680px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="border border-gray-300 px-2 py-1 text-left">
                  {barCompareScope === "self" ? "报告科目（合计）" : "报告科目（下级）"}
                </th>
                {barData.matrix_headers.map((h) => (
                  <th key={h} className="border border-gray-300 px-2 py-1 text-right">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {barData.matrix_rows.map((row) => (
                <tr key={row.row_label}>
                  <td className="border border-gray-300 px-2 py-1">{row.row_label}</td>
                  {row.values.map((v, idx) => (
                    <td key={`${row.row_label}-${idx}`} className="border border-gray-300 px-2 py-1 text-right">
                      {formatByType(v, barMatrixTypeMap.get(row.row_label))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  const renderLineTab = () => (
    <div className="space-y-3">
      <div className="border border-gray-300 rounded p-3 space-y-3 bg-white">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-gray-700">报告科目</label>
          <select
            value={selectedReportCode}
            onChange={(e) => setSelectedReportCode(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[260px]"
          >
            <option value="">请选择报告科目</option>
            {reportNodes.map((node) => (
              <option
                key={node.report_acct_code}
                value={node.report_acct_code}
              >
                {`${"　".repeat(node.depth)}${node.report_acct_code} ${node.report_acct_name}${
                  node.is_summary ? "" : "（非汇总）"
                }`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={useAllVersions}
              onChange={() => setUseAllVersions(true)}
            />
            全部展示对比年度
          </label>
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={!useAllVersions}
              onChange={() => {
                setUseAllVersions(false);
                setManualVersionKey("");
              }}
            />
            选择年度与版本
          </label>
        </div>

        {!useAllVersions && (
          <div className="flex flex-wrap items-center gap-3">
            {yearOptions.length === 0 ? (
              <span className="text-xs text-gray-500">暂无可用年度数据</span>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">年度</label>
                  <select
                    value={resolvedManualYear != null ? String(resolvedManualYear) : ""}
                    onChange={(e) => {
                      setManualYear(Number(e.target.value));
                      setManualVersionKey("");
                    }}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[120px]"
                  >
                    {yearOptions.map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">版本</label>
                  <select
                    value={manualVersionKey}
                    onChange={(e) => setManualVersionKey(e.target.value)}
                    disabled={versionsForManualYear.length === 0}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[220px] disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="">
                      {versionsForManualYear.length === 0 ? "该年度无版本" : "请选择版本"}
                    </option>
                    {versionsForManualYear.map((opt) => (
                      <option key={`${opt.data_file_id}:${opt.version_id}`} value={`${opt.data_file_id}:${opt.version_id}`}>
                        {`${opt.version_id}-${opt.version_name}`}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-gray-700 shrink-0">比较范围</span>
          <label
            className={`inline-flex items-center gap-1 ${!selectedReportIsSummary ? "text-gray-400" : ""}`}
            title={!selectedReportIsSummary ? "非汇总科目不支持本科目趋势" : undefined}
          >
            <input
              type="radio"
              checked={lineCompareScope === "self"}
              onChange={() => setLineCompareScope("self")}
              disabled={!selectedReportIsSummary}
            />
            本科目趋势
          </label>
          <label
            className="inline-flex items-center gap-1"
          >
            <input
              type="radio"
              checked={lineCompareScope === "children"}
              onChange={() => setLineCompareScope("children")}
            />
            下级科目趋势
          </label>
          {isSingleManualVersion && (
            <>
              <span className="text-gray-700 shrink-0">比较粒度</span>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "month"}
                  onChange={() => setSingleVersionGranularity("month")}
                />
                月度
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "quarter"}
                  onChange={() => setSingleVersionGranularity("quarter")}
                />
                季度
              </label>
            </>
          )}
          <button
            type="button"
            onClick={() => void loadLineData()}
            className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 ml-auto shrink-0"
            disabled={loadingData}
          >
            {loadingData ? "加载中..." : "更新图表"}
          </button>
        </div>
      </div>

      {lineLoadError && <div className="text-xs text-red-600">{lineLoadError}</div>}
      {metaError && <div className="text-xs text-red-600">{metaError}</div>}

      <div className="border border-gray-300 rounded p-3 bg-white">
        <div className="text-xs font-medium text-gray-800 mb-2">曲线图视图</div>
        {loadingMeta ? (
          <div className="text-xs text-gray-500 py-8 text-center">正在加载图表配置...</div>
        ) : !lineData || !lineData.categories.length ? (
          <div className="text-xs text-gray-500 py-8 text-center">暂无可展示数据</div>
        ) : (
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineChartData} margin={{ left: 16, right: 16, top: 16, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => formatValue(toNumber(value))} />
                <Legend
                  wrapperStyle={{ fontSize: 12, lineHeight: "16px" }}
                  iconSize={10}
                  iconType="circle"
                />
                {lineData.series.map((s, idx) => (
                  <Line
                    key={s.key}
                    type="monotone"
                    dataKey={s.key}
                    name={s.label}
                    stroke={palette[idx % palette.length]}
                    strokeWidth={2}
                    dot={lineData.series.length <= 4 ? { r: 2 } : false}
                    activeDot={{ r: 4 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="border border-gray-300 rounded p-3 bg-white overflow-auto">
        <div className="text-xs font-medium text-gray-800 mb-2">图表数据矩阵</div>
        {!lineData || !lineData.matrix_rows.length ? (
          <div className="text-xs text-gray-500 py-2">暂无数据</div>
        ) : (
          <table className="w-full text-xs border-collapse min-w-[680px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="border border-gray-300 px-2 py-1 text-left">
                  {lineCompareScope === "self" ? "报告科目（合计）" : "报告科目（下级）"}
                </th>
                {lineData.matrix_headers.map((h) => (
                  <th key={h} className="border border-gray-300 px-2 py-1 text-right">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lineData.matrix_rows.map((row) => (
                <tr key={row.row_label}>
                  <td className="border border-gray-300 px-2 py-1">{row.row_label}</td>
                  {row.values.map((v, idx) => (
                    <td key={`${row.row_label}-${idx}`} className="border border-gray-300 px-2 py-1 text-right">
                      {v.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  const renderPieTab = () => (
    <div className="space-y-3">
      <div className="border border-gray-300 rounded p-3 space-y-3 bg-white">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-gray-700">报告科目</label>
          <select
            value={selectedReportCode}
            onChange={(e) => setSelectedReportCode(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[260px]"
          >
            <option value="">请选择报告科目</option>
            {reportNodes.map((node) => (
              <option
                key={node.report_acct_code}
                value={node.report_acct_code}
                disabled={!node.is_summary}
              >
                {`${"　".repeat(node.depth)}${node.report_acct_code} ${node.report_acct_name}${
                  node.is_summary ? "" : "（非汇总，不可选）"
                }`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={useAllVersions}
              onChange={() => setUseAllVersions(true)}
            />
            全部展示对比年度
          </label>
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={!useAllVersions}
              onChange={() => {
                setUseAllVersions(false);
                setManualVersionKey("");
              }}
            />
            选择年度与版本
          </label>
        </div>

        {!useAllVersions && (
          <div className="flex flex-wrap items-center gap-3">
            {yearOptions.length === 0 ? (
              <span className="text-xs text-gray-500">暂无可用年度数据</span>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">年度</label>
                  <select
                    value={resolvedManualYear != null ? String(resolvedManualYear) : ""}
                    onChange={(e) => {
                      setManualYear(Number(e.target.value));
                      setManualVersionKey("");
                    }}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[120px]"
                  >
                    {yearOptions.map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">版本</label>
                  <select
                    value={manualVersionKey}
                    onChange={(e) => setManualVersionKey(e.target.value)}
                    disabled={versionsForManualYear.length === 0}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[220px] disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="">
                      {versionsForManualYear.length === 0 ? "该年度无版本" : "请选择版本"}
                    </option>
                    {versionsForManualYear.map((opt) => (
                      <option key={`${opt.data_file_id}:${opt.version_id}`} value={`${opt.data_file_id}:${opt.version_id}`}>
                        {`${opt.version_id}-${opt.version_name}`}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-gray-700 shrink-0">构成方式</span>
          {useAllVersions ? (
            <>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={pieAllVersionMode === "segments"}
                  onChange={() => setPieAllVersionMode("segments")}
                />
                下级科目占比
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={pieAllVersionMode === "segments_by_year"}
                  onChange={() => setPieAllVersionMode("segments_by_year")}
                />
                下级科目占比年度比较
              </label>
            </>
          ) : (
            <>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={pieDimension === "segments"}
                  onChange={() => setPieDimension("segments")}
                />
                下级科目占比
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={pieDimension === "periods"}
                  onChange={() => setPieDimension("periods")}
                />
                期间占比
              </label>
            </>
          )}
          {!useAllVersions && pieDimension === "periods" && (
            <>
              <span className="text-gray-700 shrink-0">比较粒度</span>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "month"}
                  onChange={() => setSingleVersionGranularity("month")}
                />
                月度
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "quarter"}
                  onChange={() => setSingleVersionGranularity("quarter")}
                />
                季度
              </label>
            </>
          )}
          <div className="flex items-center gap-2 ml-auto">
            {useAllVersions && pieAllVersionMode === "segments" && pieData?.categories?.length ? (
              <>
                <label className="text-gray-700">比较年度</label>
                <select
                  value={pieSelectedYear}
                  onChange={(e) => setPieSelectedYear(e.target.value)}
                  className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[120px]"
                >
                  {pieData.categories.map((year) => (
                    <option key={`pie-year-${year}`} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
            <label className="text-gray-700">显示前 N 项</label>
            <select
              value={String(pieTopN)}
              onChange={(e) => setPieTopN(Number(e.target.value))}
              className="border border-gray-300 rounded px-2 py-1 text-xs"
            >
              {[5, 8, 10, 12].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void loadPieData()}
              className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 shrink-0"
              disabled={loadingData}
            >
              {loadingData ? "加载中..." : "更新图表"}
            </button>
          </div>
        </div>
      </div>

      {pieLoadError && <div className="text-xs text-red-600">{pieLoadError}</div>}
      {metaError && <div className="text-xs text-red-600">{metaError}</div>}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(420px,1fr)_320px] gap-3">
        <div className="border border-gray-300 rounded p-3 bg-white">
          <div className="text-xs font-medium text-gray-800 mb-2">饼环图视图</div>
          {(() => {
            const showYearRing = useAllVersions && pieAllVersionMode === "segments_by_year";
            const ringCount = pieYearRings.length;
            const ringGap = 4;
            const maxOuter = 120;
            const minInner = 28;
            const ringWidth = ringCount > 0
              ? Math.max(8, (maxOuter - minInner - ringGap * Math.max(0, ringCount - 1)) / ringCount)
              : 0;
            return loadingMeta ? (
              <div className="text-xs text-gray-500 py-8 text-center">正在加载图表配置...</div>
            ) : showYearRing ? (
              ringCount === 0 ? (
                <div className="text-xs text-gray-500 py-8 text-center">暂无可展示数据</div>
              ) : (
                <div className="h-[360px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Tooltip
                        formatter={(value, _name, item) => {
                          const payload = item?.payload as { percent?: number } | undefined;
                          const pct = (payload?.percent ?? 0) * 100;
                          return `${formatValue(toNumber(value))} (${pct.toFixed(2)}%)`;
                        }}
                        labelFormatter={(label) => `年度：${String(label ?? "")}`}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: 12, lineHeight: "16px" }}
                        iconSize={10}
                        iconType="circle"
                      />
                      {pieYearRings.map((ring, idx) => {
                        const outerRadius = maxOuter - idx * (ringWidth + ringGap);
                        const innerRadius = Math.max(minInner, outerRadius - ringWidth);
                        return (
                          <Pie
                            key={`pie-ring-${ring.year}`}
                            data={ring.data}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={innerRadius}
                            outerRadius={outerRadius}
                            labelLine={false}
                            legendType={idx === 0 ? "circle" : "none"}
                          >
                            {ring.data.map((entry, eIdx) => (
                              <Cell key={`${ring.year}-${entry.name}-${eIdx}`} fill={entry.color} />
                            ))}
                          </Pie>
                        );
                      })}
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )
            ) : pieSlices.length === 0 ? (
              <div className="text-xs text-gray-500 py-8 text-center">暂无可展示数据</div>
            ) : (
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Tooltip
                      formatter={(value) =>
                        `${formatValue(toNumber(value))} (${((toNumber(value) / (pieTotalValue || 1)) * 100).toFixed(2)}%)`
                      }
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 12, lineHeight: "16px" }}
                      iconSize={10}
                      iconType="circle"
                    />
                    <Pie
                      data={pieSlices}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={120}
                      label={(props: {
                        cx?: number;
                        cy?: number;
                        midAngle?: number;
                        innerRadius?: number;
                        outerRadius?: number;
                        percent?: number;
                        name?: string | number;
                      }) => {
                        const RADIAN = Math.PI / 180;
                        const cx = props.cx ?? 0;
                        const cy = props.cy ?? 0;
                        const midAngle = props.midAngle ?? 0;
                        const innerRadius = props.innerRadius ?? 0;
                        const outerRadius = props.outerRadius ?? 0;
                        const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
                        const x = cx + radius * Math.cos(-midAngle * RADIAN);
                        const y = cy + radius * Math.sin(-midAngle * RADIAN);
                        return (
                          <text
                            x={x}
                            y={y}
                            fill="#374151"
                            textAnchor={x > cx ? "start" : "end"}
                            dominantBaseline="central"
                            fontSize={12}
                          >
                            {`${String(props.name ?? "")} ${((props.percent ?? 0) * 100).toFixed(1)}%`}
                          </text>
                        );
                      }}
                      labelLine={false}
                    >
                      {pieSlices.map((entry, idx) => (
                        <Cell key={`${entry.name}-${idx}`} fill={palette[idx % palette.length]} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
            );
          })()}
        </div>
        <div className="border border-gray-300 rounded p-3 bg-white">
          {useAllVersions && pieAllVersionMode === "segments_by_year" ? (
            <>
              <div className="text-xs font-medium text-gray-800 mb-2">年度颜色示例</div>
              {pieYearRings.length === 0 ? (
                <div className="text-xs text-gray-500 py-2">暂无数据</div>
              ) : (
                <div className="space-y-2 max-h-[360px] overflow-auto pr-1">
                  {pieYearRings.map((ring) => {
                    const layerText =
                      ring.ringIndex === 0
                        ? "外圈"
                        : ring.ringIndex === ring.ringCount - 1
                          ? "内圈"
                          : `第${ring.ringIndex + 1}圈`;
                    return (
                      <div
                        key={`ring-legend-${ring.year}`}
                        className="text-xs border border-gray-200 rounded px-2 py-2 bg-white"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-block w-3.5 h-3.5 rounded-sm border border-gray-300"
                            style={{ backgroundColor: ring.ringColor }}
                          />
                          <span className="font-medium text-gray-700">{ring.year}</span>
                          <span className="text-gray-500">{layerText}</span>
                        </div>
                        <div className="mt-1 text-gray-500">该年度环颜色由外向内逐渐变浅</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="text-xs font-medium text-gray-800 mb-2">构成明细</div>
              {pieSlices.length === 0 ? (
                <div className="text-xs text-gray-500 py-2">暂无数据</div>
              ) : (
                <div className="space-y-1.5 max-h-[360px] overflow-auto pr-1">
                  {pieSlices.map((item, idx) => {
                    const ratio = pieTotalValue ? (item.value / pieTotalValue) * 100 : 0;
                    return (
                      <div key={`${item.name}-${idx}`} className="text-xs border border-gray-200 rounded px-2 py-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="truncate text-gray-700">{item.name}</div>
                          <div className="text-gray-500">{ratio.toFixed(2)}%</div>
                        </div>
                        <div className="mt-1 text-gray-800">{formatValue(item.value)}</div>
                        <div className="mt-1 h-1.5 bg-gray-100 rounded overflow-hidden">
                          <div
                            className="h-full"
                            style={{
                              width: `${Math.max(2, ratio)}%`,
                              backgroundColor: palette[idx % palette.length],
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="border border-gray-300 rounded p-3 bg-white overflow-auto">
        <div className="text-xs font-medium text-gray-800 mb-2">图表数据矩阵</div>
        {useAllVersions && pieDimension === "segments" ? (
          !pieData || !pieData.categories.length || !pieMatrixRowsByYear.length ? (
            <div className="text-xs text-gray-500 py-2">暂无数据</div>
          ) : (
            <table className="w-full text-xs border-collapse min-w-[920px]">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-2 py-1 text-left">下级科目</th>
                  {pieData.categories.map((year) => (
                    <th key={`${year}-value`} className="border border-gray-300 px-2 py-1 text-right">
                      {year} 数值
                    </th>
                  ))}
                  {pieData.categories.map((year) => (
                    <th key={`${year}-pct`} className="border border-gray-300 px-2 py-1 text-right">
                      {year} 占比
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pieMatrixRowsByYear.map((row) => (
                  <tr key={`pie-year-row-${row.label}`}>
                    <td className="border border-gray-300 px-2 py-1">{row.label}</td>
                    {row.values.map((v, idx) => (
                      <td key={`${row.label}-v-${idx}`} className="border border-gray-300 px-2 py-1 text-right">
                        {formatValue(v)}
                      </td>
                    ))}
                    {row.values.map((v, idx) => {
                      const total = pieYearTotals[idx] ?? 0;
                      const pct = total ? (v / total) * 100 : 0;
                      return (
                        <td key={`${row.label}-p-${idx}`} className="border border-gray-300 px-2 py-1 text-right">
                          {pct.toFixed(2)}%
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : pieSlices.length === 0 ? (
          <div className="text-xs text-gray-500 py-2">暂无数据</div>
        ) : (
          <table className="w-full text-xs border-collapse min-w-[520px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="border border-gray-300 px-2 py-1 text-left">维度项</th>
                <th className="border border-gray-300 px-2 py-1 text-right">数值</th>
                <th className="border border-gray-300 px-2 py-1 text-right">占比</th>
              </tr>
            </thead>
            <tbody>
              {pieSlices.map((item, idx) => {
                const pct = pieTotalValue ? (item.value / pieTotalValue) * 100 : 0;
                return (
                  <tr key={`${item.name}-matrix-${idx}`}>
                    <td className="border border-gray-300 px-2 py-1">{item.name}</td>
                    <td className="border border-gray-300 px-2 py-1 text-right">{formatValue(item.value)}</td>
                    <td className="border border-gray-300 px-2 py-1 text-right">{pct.toFixed(2)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  const renderStackedTab = () => (
    <div className="space-y-3">
      <div className="border border-gray-300 rounded p-3 space-y-3 bg-white">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-gray-700">报告科目</label>
          <select
            value={selectedReportCode}
            onChange={(e) => setSelectedReportCode(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[260px]"
          >
            <option value="">请选择报告科目</option>
            {reportNodes.map((node) => (
              <option
                key={node.report_acct_code}
                value={node.report_acct_code}
                disabled={!node.is_summary}
              >
                {`${"　".repeat(node.depth)}${node.report_acct_code} ${node.report_acct_name}${
                  node.is_summary ? "" : "（非汇总，不可选）"
                }`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={useAllVersions}
              onChange={() => setUseAllVersions(true)}
            />
            全部展示对比年度
          </label>
          <label className="inline-flex items-center gap-1">
            <input
              type="radio"
              checked={!useAllVersions}
              onChange={() => {
                setUseAllVersions(false);
                setManualVersionKey("");
              }}
            />
            选择年度与版本
          </label>
          {useAllVersions && (
            <button
              type="button"
              onClick={() => void loadStackedData()}
              className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 ml-auto shrink-0"
              disabled={loadingData}
            >
              {loadingData ? "加载中..." : "更新图表"}
            </button>
          )}
        </div>

        {!useAllVersions && (
          <div className="flex flex-wrap items-center gap-3">
            {yearOptions.length === 0 ? (
              <>
                <span className="text-xs text-gray-500">暂无可用年度数据</span>
                <button
                  type="button"
                  onClick={() => void loadStackedData()}
                  className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 ml-auto shrink-0"
                  disabled={loadingData}
                >
                  {loadingData ? "加载中..." : "更新图表"}
                </button>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">年度</label>
                  <select
                    value={resolvedManualYear != null ? String(resolvedManualYear) : ""}
                    onChange={(e) => {
                      setManualYear(Number(e.target.value));
                      setManualVersionKey("");
                    }}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[120px]"
                  >
                    {yearOptions.map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-600">版本</label>
                  <select
                    value={manualVersionKey}
                    onChange={(e) => setManualVersionKey(e.target.value)}
                    disabled={versionsForManualYear.length === 0}
                    className="border border-gray-300 rounded px-2 py-1 text-xs min-w-[220px] disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="">
                      {versionsForManualYear.length === 0 ? "该年度无版本" : "请选择版本"}
                    </option>
                    {versionsForManualYear.map((opt) => (
                      <option key={`${opt.data_file_id}:${opt.version_id}`} value={`${opt.data_file_id}:${opt.version_id}`}>
                        {`${opt.version_id}-${opt.version_name}`}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={() => void loadStackedData()}
                  className="px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 ml-auto shrink-0"
                  disabled={loadingData}
                >
                  {loadingData ? "加载中..." : "更新图表"}
                </button>
              </>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 text-xs w-full">
          {isSingleManualVersion && (
            <>
              <span className="text-gray-700 shrink-0">比较粒度</span>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "month"}
                  onChange={() => setSingleVersionGranularity("month")}
                />
                月度比较
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  checked={singleVersionGranularity === "quarter"}
                  onChange={() => setSingleVersionGranularity("quarter")}
                />
                季度比较
              </label>
            </>
          )}
          <div className="flex flex-wrap items-center gap-2 ml-auto">
            <span className="text-gray-700">展示模式</span>
            <label className="inline-flex items-center gap-1">
              <input
                type="radio"
                checked={stackMode === "absolute"}
                onChange={() => setStackMode("absolute")}
              />
              累计堆积图
            </label>
            <label className="inline-flex items-center gap-1">
              <input
                type="radio"
                checked={stackMode === "percent"}
                onChange={() => setStackMode("percent")}
              />
              占比堆积图
            </label>
          </div>
        </div>
      </div>

      {stackedLoadError && <div className="text-xs text-red-600">{stackedLoadError}</div>}
      {metaError && <div className="text-xs text-red-600">{metaError}</div>}

      <div className="border border-gray-300 rounded p-3 bg-white">
        <div className="text-xs font-medium text-gray-800 mb-2">堆积图视图</div>
        {loadingMeta ? (
          <div className="text-xs text-gray-500 py-8 text-center">正在加载图表配置...</div>
        ) : !stackedData || !stackedData.categories.length ? (
          <div className="text-xs text-gray-500 py-8 text-center">暂无可展示数据</div>
        ) : (
          <div className="h-[360px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ left: 16, right: 16, top: 16, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value) =>
                    stackMode === "percent" ? `${toNumber(value).toFixed(2)}%` : toNumber(value).toFixed(2)
                  }
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, lineHeight: "16px" }}
                  iconSize={10}
                  iconType="square"
                />
                {stackedData.series.map((s, idx) => (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    stackId="stacked"
                    name={s.label}
                    fill={palette[idx % palette.length]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="border border-gray-300 rounded p-3 bg-white overflow-auto">
        <div className="text-xs font-medium text-gray-800 mb-2">图表数据矩阵</div>
        {!stackedData || !stackedData.matrix_rows.length ? (
          <div className="text-xs text-gray-500 py-2">暂无数据</div>
        ) : (
          <table className="w-full text-xs border-collapse min-w-[680px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="border border-gray-300 px-2 py-1 text-left">报告科目（拆分项）</th>
                {stackedData.matrix_headers.map((h) => (
                  <th key={h} className="border border-gray-300 px-2 py-1 text-right">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stackedData.matrix_rows.map((row) => (
                <tr key={row.row_label}>
                  <td className="border border-gray-300 px-2 py-1">{row.row_label}</td>
                  {row.values.map((v, idx) => (
                    <td key={`${row.row_label}-${idx}`} className="border border-gray-300 px-2 py-1 text-right">
                      {stackMode === "percent" ? `${v.toFixed(2)}%` : v.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-4 h-full overflow-auto">
      <h3 className="text-sm font-medium text-gray-800 mb-3">数据透视图</h3>
      <div className="border-b border-gray-300 mb-3">
        <div className="flex items-end justify-between gap-3">
          <div role="tablist" aria-label="数据透视图类型标签页" className="flex items-end gap-1">
            {chartTabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={isActive}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-2 text-xs border rounded-t-md transition-colors ${
                    isActive
                      ? "bg-white text-blue-700 border-gray-300 border-b-white font-medium"
                      : "bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200"
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={() => void handleExportPpt()}
            className="mb-1 px-3 py-1.5 text-xs rounded bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-60 shrink-0"
            disabled={exportingPpt || !currentChartHasData}
            title={!currentChartHasData ? "当前图表暂无可导出数据" : "导出当前图表到PPT"}
          >
            {exportingPpt ? "导出中..." : "导出到PPT"}
          </button>
        </div>
      </div>

      {exportError && <div className="text-xs text-red-600 mb-2">{exportError}</div>}

      {activeTab === "stacked" && renderStackedTab()}
      {activeTab === "bar" && renderBarTab()}
      {activeTab === "line" && renderLineTab()}
      {activeTab === "pie" && renderPieTab()}
    </div>
  );
}
