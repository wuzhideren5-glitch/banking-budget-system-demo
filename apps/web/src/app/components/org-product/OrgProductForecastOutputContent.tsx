import { useEffect, useMemo, useRef, useState } from "react";
import { Download, RefreshCw, Search, ChevronDown, ChevronRight } from "lucide-react";
import { getSession, type SessionInfo } from "@/lib/system/systemApi";
import { getOrgProductTreeSnapshot } from "@/lib/org-product/orgProductTreeApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { getDataEntryVersions } from "@/lib/org-product/orgProductDataEntryApi";
import {
  getOrgProductOutputSnapshot,
  getOutputVersions,
  runOrgProductOutput,
  exportOrgProductOutput,
  commitOrgProductOutput,
} from "@/lib/org-product/orgProductOutputApi";
import {
  PILOT_ENTITY_CODE,
  PILOT_TABLE_NAME,
  annualAggHint,
  pickPilotEntityCode,
  pickPilotTableName,
} from "@/lib/org-product/orgProductPilot";
import { prepareOrgProductTreeFromStorage } from "@/lib/org-product/orgProductTree";

type OrgProductNode = {
  id: string;
  code: string;
  name: string;
  type: string;
  children?: OrgProductNode[];
};

type OrgProductTreeSnapshotDto =
  | { found: false }
  | { found: true; tree: OrgProductNode; updated_at: string };

type MetricNodePayload = {
  id: string;
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  note?: string;
  formula?: string;
  children?: MetricNodePayload[];
};

type MetricTablePayload = {
  id: string;
  name: string;
  metrics: MetricNodePayload[];
};

type OrgProductMetricSnapshotDto = {
  entities: { entity_code: string; entity_name: string; tables: MetricTablePayload[] }[];
};

type DataEntryVersionItemDto = { version_id: number; version_name: string; updated_at: string };
type DataEntryVersionsDto = { items: DataEntryVersionItemDto[] };

type OutputRowDto = {
  id: string;
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  value_type?: string;
  formula: string;
  months: number[];
  month_errors?: (string | null)[];
  annual: number | null;
  annual_method?: string;
};

type OutputEntityDto = {
  entity_code: string;
  entity_name: string;
  table_name: string;
  rows: OutputRowDto[];
};

type OutputRunResponseDto = { entities: OutputEntityDto[] };

type OutputVersionItemDto = { output_version_id: number; output_version_name: string; updated_at: string };
type OutputVersionsDto = { items: OutputVersionItemDto[] };
type OutputSnapshotDto = { found: boolean; payload?: OutputEntityDto; updated_at?: string };

function parseNumber(raw: unknown): number | null {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  const normalized = text.replace(/[,，\s]/g, "");
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function dataEntryNatureKind(nature: string, valueType?: string): "int" | "oneDecimal" | "percent2" {
  const vt = String(valueType || "").trim();
  if (vt === "金额" || vt === "户数") return "oneDecimal";
  if (vt === "百分比") return "percent2";
  const n = String(nature || "").trim();
  if (n === "资产余额" || n === "资产日均" || n === "负债余额" || n === "负债日均") return "int";
  if (n === "收入" || n === "支出" || n === "利润") return "oneDecimal";
  return "percent2";
}

function formatByNature(nature: string, value: number | null | undefined, valueType?: string): string {
  if (value == null || !Number.isFinite(value)) return "";
  const kind = dataEntryNatureKind(nature, valueType);
  if (kind === "int") return Math.round(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  if (kind === "oneDecimal") return value.toLocaleString("zh-CN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${(value * 100).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function splitSearchKeywords(raw: string): string[] {
  return raw
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function filterOrgProductTree(root: OrgProductNode, query: string): OrgProductNode | null {
  const keywords = splitSearchKeywords(query);
  if (!keywords.length) return root;
  const nodeText = `${root.code} ${root.name}`.toLowerCase();
  const selfHit = keywords.some((kw) => nodeText.includes(kw));
  const kids = (root.children ?? [])
    .map((c) => filterOrgProductTree(c, query))
    .filter((x): x is OrgProductNode => Boolean(x));
  if (selfHit || kids.length) {
    return { ...root, children: kids };
  }
  return null;
}

export function OrgProductForecastOutputContent() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [tree, setTree] = useState<OrgProductNode | null>(null);
  const [metricSnapshot, setMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);

  const [orgDropdownOpen, setOrgDropdownOpen] = useState(false);
  const orgDialogRef = useRef<HTMLDivElement | null>(null);
  const [orgExpanded, setOrgExpanded] = useState<Record<string, boolean>>({});
  const [orgSearchInput, setOrgSearchInput] = useState("");
  const [selectedEntityCode, setSelectedEntityCode] = useState("");

  const [selectedYear, setSelectedYear] = useState<number>(0);
  const [selectedTableName, setSelectedTableName] = useState("业务状况表");
  const [versionItems, setVersionItems] = useState<DataEntryVersionItemDto[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number>(0);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OutputEntityDto | null>(null);

  const [outputVersionItems, setOutputVersionItems] = useState<OutputVersionItemDto[]>([]);
  const [selectedOutputVersionId, setSelectedOutputVersionId] = useState<number>(0);
  const [outputVersionName, setOutputVersionName] = useState("");
  const [savingOutputVersion, setSavingOutputVersion] = useState(false);

  const entityNameByCode = useMemo(() => {
    const map = new Map<string, string>();
    const walk = (n: OrgProductNode) => {
      map.set(n.code, n.name);
      (n.children ?? []).forEach(walk);
    };
    if (tree) walk(tree);
    return map;
  }, [tree]);

  const tablesForEntity = useMemo(() => {
    const code = (selectedEntityCode || "").trim();
    if (!code || !metricSnapshot) return [];
    const hit = metricSnapshot.entities.find((e) => e.entity_code === code);
    return (hit?.tables ?? []).map((t) => t.name).filter(Boolean);
  }, [metricSnapshot, selectedEntityCode]);

  const selectedEntityLabel = useMemo(() => {
    const code = (selectedEntityCode || "").trim();
    if (!code) return "请选择机构或产品";
    const name = entityNameByCode.get(code) ?? "";
    return `${code} ${name}`.trim();
  }, [entityNameByCode, selectedEntityCode]);

  const outputErrorCount = useMemo(() => {
    if (!result) return 0;
    let cnt = 0;
    for (const r of result.rows ?? []) {
      for (const err of r.month_errors ?? []) {
        if (err) cnt += 1;
      }
    }
    return cnt;
  }, [result]);

  const loadAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [s, t, ms] = await Promise.all([
        getSession(),
        (getOrgProductTreeSnapshot() as Promise<OrgProductTreeSnapshotDto>),
        (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>),
      ]);
      setSession(s);
      setSelectedYear((prev) => (prev > 0 ? prev : s.budget_year));
      setSelectedVersionId((prev) => (prev > 0 ? prev : s.version_id));
      if ("found" in t && t.found && t.tree) setTree(prepareOrgProductTreeFromStorage(t.tree) as OrgProductNode);
      else setTree(null);
      setMetricSnapshot(ms);

      const configuredCodes = ms.entities.map((e) => e.entity_code).filter(Boolean);
      const fallbackEntity = configuredCodes[0] ?? "";
      const priorEntityCode = (selectedEntityCode || "").trim();
      const entityCode = pickPilotEntityCode(configuredCodes, priorEntityCode, fallbackEntity);
      setSelectedEntityCode((prev) => prev || entityCode);
      const tableNames = ms.entities.find((e) => e.entity_code === entityCode)?.tables?.map((t) => t.name) ?? [];
      const tableFallback =
        entityCode === PILOT_ENTITY_CODE
          ? PILOT_TABLE_NAME
          : tableNames[0] ?? "业务状况表";
      setSelectedTableName((prev) => pickPilotTableName(tableNames.length ? tableNames : [tableFallback], prev || tableFallback));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    const onTreeSaved = () => {
      void loadAll();
    };
    window.addEventListener("org-product-tree-saved", onTreeSaved);
    return () => window.removeEventListener("org-product-tree-saved", onTreeSaved);
  }, []);

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      const el = orgDialogRef.current;
      if (!el) return;
      if (!el.contains(e.target as Node)) {
        setOrgDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  useEffect(() => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code || !tn || !selectedYear) {
      setVersionItems([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await (getDataEntryVersions(
          code,
          selectedYear,
          { table_name: tn }
        ) as unknown as Promise<DataEntryVersionsDto>);
        if (cancelled) return;
        const items = resp.items ?? [];
        setVersionItems(items);
        const preferred = items.find((x) => x.version_id === (session?.version_id ?? -1))?.version_id;
        if (preferred != null) {
          setSelectedVersionId(preferred);
        } else if (items.length > 0) {
          setSelectedVersionId(items[0].version_id);
        } else {
          setSelectedVersionId(session?.version_id ?? 0);
        }
      } catch {
        if (!cancelled) {
          setVersionItems([]);
          setSelectedVersionId(session?.version_id ?? 0);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedEntityCode, selectedTableName, selectedYear, session?.version_id]);

  useEffect(() => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code || !tn || !selectedYear || !selectedVersionId) {
      setOutputVersionItems([]);
      setSelectedOutputVersionId(0);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await (getOutputVersions(
          code,
          selectedYear,
          { input_version_id: selectedVersionId, table_name: tn }
        ) as unknown as Promise<OutputVersionsDto>);
        if (cancelled) return;
        const items = resp.items ?? [];
        setOutputVersionItems(items);
        if (items.length > 0 && !items.some((x) => x.output_version_id === selectedOutputVersionId)) {
          setSelectedOutputVersionId(items[0].output_version_id);
        }
      } catch {
        if (!cancelled) {
          setOutputVersionItems([]);
          setSelectedOutputVersionId(0);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedEntityCode, selectedTableName, selectedYear, selectedVersionId, selectedOutputVersionId]);

  useEffect(() => {
    if (!tablesForEntity.length) return;
    if (!tablesForEntity.includes(selectedTableName)) {
      const code = (selectedEntityCode || "").trim();
      setSelectedTableName(
        code === PILOT_ENTITY_CODE ? pickPilotTableName(tablesForEntity, "") : tablesForEntity[0]
      );
    }
  }, [tablesForEntity, selectedTableName, selectedEntityCode]);

  const run = async () => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code) {
      setError("请选择机构或产品");
      return;
    }
    if (!tn) {
      setError("请选择指标表");
      return;
    }
    setRunning(true);
    setError("");
    try {
      const resp = await (runOrgProductOutput({
        entity_code: code,
        year: selectedYear,
        version_id: selectedVersionId,
        table_name: tn,
        include_children: false,
      }) as unknown as Promise<OutputRunResponseDto>);
      const entity = resp.entities?.[0] ?? null;
      setResult(entity);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "运行失败");
    } finally {
      setRunning(false);
    }
  };

  const exportCurrent = async () => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code || !tn) return;
    setError("");
    try {
      const { blob, filename } = await exportOrgProductOutput({
        entity_code: code,
        year: selectedYear,
        version_id: selectedVersionId,
        table_name: tn,
        include_children: false,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename ?? `预测输出_${code}_${selectedYear}_v${selectedVersionId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出当前表失败");
    }
  };

  const exportAll = async () => {
    const code = (selectedEntityCode || "").trim();
    if (!code) {
      setError("请选择机构或产品");
      return;
    }
    setError("");
    try {
      const { blob, filename } = await exportOrgProductOutput({
        entity_code: code,
        year: selectedYear,
        version_id: selectedVersionId,
        table_name: null,
        include_children: true,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename ?? `预测输出_全量_${code}_${selectedYear}_v${selectedVersionId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出全量失败");
    }
  };

  const loadSavedOutputVersion = async () => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code || !tn || !selectedYear || !selectedVersionId || !selectedOutputVersionId) return;
    setError("");
    try {
      const resp = await (getOrgProductOutputSnapshot(
        code,
        selectedYear,
        {
          input_version_id: selectedVersionId,
          output_version_id: selectedOutputVersionId,
          table_name: tn,
        }
      ) as unknown as Promise<OutputSnapshotDto>);
      if (!resp.found || !resp.payload) {
        setError("未找到该输出版本快照");
        return;
      }
      setResult(resp.payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取输出版本失败");
    }
  };

  const saveAsOutputVersion = async () => {
    const code = (selectedEntityCode || "").trim();
    const tn = (selectedTableName || "").trim();
    if (!code || !tn || !selectedYear || !selectedVersionId) return;
    if (savingOutputVersion) return;
    const force = outputErrorCount > 0 ? window.confirm(`检测到 ${outputErrorCount} 个公式错误，仍然强制保存输出版本？`) : false;
    setSavingOutputVersion(true);
    setError("");
    try {
      const resp = await (commitOrgProductOutput({
        entity_code: code,
        year: selectedYear,
        input_version_id: selectedVersionId,
        table_name: tn,
        output_version_id: null,
        output_version_name: outputVersionName,
        force,
      }) as unknown as Promise<{ ok: boolean; output_version_id: number }>);
      await (getOutputVersions(
        code,
        selectedYear,
        { input_version_id: selectedVersionId, table_name: tn }
      ) as unknown as Promise<OutputVersionsDto>).then((x) => {
        setOutputVersionItems(x.items ?? []);
        setSelectedOutputVersionId(resp.output_version_id);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存输出版本失败");
    } finally {
      setSavingOutputVersion(false);
    }
  };

  const renderOrgNode = (node: OrgProductNode, level: number) => {
    const children = node.children ?? [];
    const hasChildren = children.length > 0;
    const open = orgExpanded[node.id] ?? false;
    const selected = node.code === selectedEntityCode;
    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1.5 px-2 py-1 text-xs cursor-pointer hover:bg-gray-100 ${
            selected ? "bg-blue-50" : ""
          }`}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
          onClick={() => {
            setSelectedEntityCode(node.code);
            setOrgDropdownOpen(false);
          }}
        >
          {hasChildren ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setOrgExpanded((prev) => ({ ...prev, [node.id]: !(prev[node.id] ?? false) }));
              }}
              className="p-0.5 hover:bg-gray-200 rounded"
            >
              {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
            </button>
          ) : (
            <span className="w-4" />
          )}
          <span className="font-mono text-gray-600">{node.code}</span>
          <span className="text-gray-700">{node.name}</span>
        </div>
        {hasChildren && open ? children.map((c) => renderOrgNode(c, level + 1)) : null}
      </div>
    );
  };

  if (loading) {
    return <div className="p-4 text-sm text-gray-600">正在加载预测输出...</div>;
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-semibold text-gray-800">预测输出</div>
          <button
            type="button"
            onClick={() => void loadAll()}
            className="ml-auto inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="text-[11px] text-gray-700 whitespace-nowrap">机构及产品</div>
          <div className="relative min-w-[260px] flex-1" ref={orgDialogRef}>
            <button
              type="button"
              onClick={() => setOrgDropdownOpen((v) => !v)}
              className="w-full flex items-center justify-between gap-2 px-2.5 py-1 text-[11px] bg-white border border-gray-300 rounded hover:bg-gray-50"
            >
              <span className="text-gray-700 truncate">{selectedEntityLabel}</span>
              <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition ${orgDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {orgDropdownOpen ? (
              <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-300 rounded shadow-lg z-50 overflow-hidden">
                <div className="p-2 border-b border-gray-200">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      value={orgSearchInput}
                      onChange={(e) => setOrgSearchInput(e.target.value)}
                      placeholder="按机构或产品搜索..."
                      className="w-full pl-8 pr-2 py-1 text-[11px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>
                <div className="max-h-72 overflow-auto py-1">
                  {tree ? (
                    (() => {
                      const visible = filterOrgProductTree(tree, orgSearchInput);
                      if (!visible) return <div className="px-3 py-6 text-xs text-gray-500">未找到匹配的机构或产品。</div>;
                      return renderOrgNode(visible, 0);
                    })()
                  ) : (
                    <div className="px-3 py-6 text-xs text-gray-500">未加载到机构及产品（请先维护/初始化）</div>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <div className="text-[11px] text-gray-700 whitespace-nowrap">年度</div>
          <input
            value={String(selectedYear)}
            onChange={(e) => {
              const n = parseNumber(e.target.value);
              if (n == null) return;
              setSelectedYear(Math.max(2000, Math.min(2100, Math.round(n))));
            }}
            className="w-[90px] px-2 py-1 text-[11px] bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
          />

          <div className="text-[11px] text-gray-700 whitespace-nowrap">指标表</div>
          <select
            value={selectedTableName}
            onChange={(e) => setSelectedTableName(e.target.value)}
            className="px-2 py-1 text-[11px] bg-white border border-gray-300 rounded"
          >
            {(tablesForEntity.length ? tablesForEntity : ["业务状况表"]).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          <div className="text-[11px] text-gray-700 whitespace-nowrap">数据版本</div>
          <select
            value={String(selectedVersionId)}
            onChange={(e) => setSelectedVersionId(Number(e.target.value))}
            className="px-2 py-1 text-[11px] bg-white border border-gray-300 rounded"
          >
            {versionItems.length ? (
              versionItems.map((v) => (
                <option key={v.version_id} value={String(v.version_id)}>
                  {`v${v.version_id}${v.version_name ? ` ${v.version_name}` : ""}`}
                </option>
              ))
            ) : (
              <option value={String(selectedVersionId)}>{`v${selectedVersionId}${session?.version_name ? ` ${session.version_name}` : ""}`}</option>
            )}
          </select>

          <button
            type="button"
            disabled={running}
            onClick={() => void run()}
            className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1 text-[11px] text-white hover:bg-blue-700 disabled:opacity-50"
          >
            运行
          </button>
          <div className="ml-2 text-[11px] text-gray-700 whitespace-nowrap">输出版本</div>
          <select
            value={String(selectedOutputVersionId)}
            onChange={(e) => setSelectedOutputVersionId(Number(e.target.value))}
            className="px-2 py-1 text-[11px] bg-white border border-gray-300 rounded"
          >
            <option value="0">未选择</option>
            {outputVersionItems.map((v) => (
              <option key={v.output_version_id} value={String(v.output_version_id)}>
                {`o${v.output_version_id}${v.output_version_name ? ` ${v.output_version_name}` : ""}`}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!selectedOutputVersionId}
            onClick={() => void loadSavedOutputVersion()}
            className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            查看版本
          </button>
          <input
            value={outputVersionName}
            onChange={(e) => setOutputVersionName(e.target.value)}
            placeholder="输出版本备注"
            className="w-[160px] px-2 py-1 text-[11px] bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="button"
            disabled={savingOutputVersion}
            onClick={() => void saveAsOutputVersion()}
            className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1 text-[11px] text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            确认保存输出版本
          </button>
          <button
            type="button"
            onClick={() => void exportCurrent()}
            className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
          >
            <Download className="h-3.5 w-3.5" />
            导出当前表
          </button>
          <button
            type="button"
            onClick={() => void exportAll()}
            className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
          >
            <Download className="h-3.5 w-3.5" />
            导出全量
          </button>
        </div>
        {result && outputErrorCount > 0 ? (
          <div className="mt-2 text-xs text-amber-700">{`校验提示：检测到 ${outputErrorCount} 个公式错误（可先导出校验，再修公式或强制保存）。`}</div>
        ) : null}
        {error ? (
          <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
        ) : null}
      </div>

      <div className="flex-1 overflow-auto p-4">
        {!result ? (
          <div className="rounded border border-gray-200 bg-white p-6 text-sm text-gray-600">请选择条件后点击“运行”。</div>
        ) : (
          <div className="rounded border border-gray-200 bg-white overflow-auto">
            <div className="px-4 py-3 border-b border-gray-200">
              <div className="text-sm font-semibold text-gray-800">
                {result.entity_code} {result.entity_name} · {result.table_name}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                年度 {selectedYear} · 数据版本 v{selectedVersionId}
              </div>
              <div className="mt-2 rounded border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] text-blue-900 leading-relaxed">
                <span className="font-medium">「年度汇总」列口径（阶段 1）：</span>
                余额类取 12 月；收入/支出/利润为 12 个月合计；资产/负债日均按当年各月天数加权；率类有公式时按全年口径重算，无公式时取 12 月。
                与数据录入中只读的「{selectedYear}年预测」列可能不同，对外以本表为准。
              </div>
            </div>
            <table className="min-w-[1700px] w-full text-xs border-collapse">
              <thead className="sticky top-0 z-10 bg-gray-100">
                <tr className="text-left text-gray-700">
                  <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">科目层级</th>
                  <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">科目性质</th>
                  <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">科目代码</th>
                  <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">科目名称</th>
                  <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap" title="口径见上方说明">
                    年度汇总
                  </th>
                  {Array.from({ length: 12 }).map((_, idx) => (
                    <th key={`m-${idx + 1}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">
                      {idx + 1}月
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-white">
                {result.rows.map((r) => {
                  return (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="border border-gray-200 px-2 py-1 whitespace-nowrap text-gray-700">{r.levelLabel}</td>
                      <td className="border border-gray-200 px-2 py-1 whitespace-nowrap text-gray-700">{r.nature}</td>
                      <td className="border border-gray-200 px-2 py-1 whitespace-nowrap font-mono text-gray-700">{r.code}</td>
                      <td className="border border-gray-200 px-2 py-1 whitespace-nowrap text-gray-800">{r.name}</td>
                      <td
                        className="border border-gray-200 px-2 py-1 text-right whitespace-nowrap font-medium text-gray-900"
                        title={r.annual_method || annualAggHint(r.nature, Boolean(String(r.formula || "").trim()))}
                      >
                        {formatByNature(r.nature, r.annual, r.value_type)}
                      </td>
                      {Array.from({ length: 12 }).map((_, idx) => (
                        <td
                          key={`${r.id}-m-${idx}`}
                          title={r.month_errors?.[idx] ? String(r.month_errors[idx]) : ""}
                          className={`border border-gray-200 px-2 py-1 text-right whitespace-nowrap ${
                            r.month_errors?.[idx] ? "text-red-700 bg-red-50" : "text-gray-700"
                          }`}
                        >
                          {formatByNature(r.nature, r.months?.[idx], r.value_type)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {result.rows.length === 0 ? (
                  <tr>
                    <td colSpan={4 + 12 + 1} className="border border-gray-200 px-3 py-8 text-center text-gray-500">
                      暂无可展示的指标。
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
