import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Download, RefreshCw } from "lucide-react";
import {
  exportExpenseBudgetExecutionReport,
  getExpenseBudgetExecutionReport,
} from "@/lib/expense/expenseBudgetExecutionApi";
import type {
  ExpenseBudgetExecutionAmountUnit,
  ExpenseBudgetExecutionMode,
  ExpenseBudgetExecutionPerspective,
  ExpenseBudgetExecutionResponseDto,
  ExpenseBudgetExecutionTemplateSubjectNodeDto,
} from "@/lib/expense/expenseBudgetExecutionApi";
import {
  buildExpenseBudgetExecutionExportRequest,
  buildExpenseBudgetExecutionLastYearMonthlyLabels,
  buildExpenseBudgetExecutionMonthlyLabels,
  buildExpenseBudgetExecutionReportRequest,
  describeExpenseBudgetExecutionSummary,
  expenseBudgetExecutionStorageKeys,
  findExpenseBudgetExecutionSubjectScopeNodeById,
  getExpenseBudgetExecutionAmountDivisor,
  getExpenseBudgetExecutionGroupOptions,
  getExpenseBudgetExecutionModeView,
  getExpenseBudgetExecutionOwnerOptions,
  getExpenseBudgetExecutionTreeMeta,
  normalizeExpenseBudgetExecutionAmountUnit,
  normalizeExpenseBudgetExecutionReportMode,
  normalizeExpenseBudgetExecutionReportMonth,
  normalizeExpenseBudgetExecutionSubjectId,
} from "@/lib/expense/expenseBudgetExecutionViewModel";
import { downloadBlob } from "@/lib/shared/api";
import { ExpenseBudgetExecutionControls } from "@/app/components/expense/ExpenseBudgetExecutionControls";
import { ExpenseBudgetExecutionMatrixTable } from "@/app/components/expense/ExpenseBudgetExecutionMatrixTable";
import { ExpenseBudgetExecutionMetricTable } from "@/app/components/expense/ExpenseBudgetExecutionMetricTable";
import { ExpenseBudgetExecutionTreeReport } from "@/app/components/expense/ExpenseBudgetExecutionTreeReport";

type AmountUnit = ExpenseBudgetExecutionAmountUnit;

export function ExpenseBudgetExecutionContent() {
  const [reportMode, setReportMode] = useState<ExpenseBudgetExecutionMode>("query");
  const perspective: ExpenseBudgetExecutionPerspective = "group";
  const [queryEntityName, setQueryEntityName] = useState("");
  const [queryGroupName, setQueryGroupName] = useState("");
  const [queryOwnerDept, setQueryOwnerDept] = useState("");
  const [queryReportMonth, setQueryReportMonth] = useState("");
  const [templateKeyword, setTemplateKeyword] = useState("");
  const [subjectKeyword, setSubjectKeyword] = useState("");
  const [templateEntityName, setTemplateEntityName] = useState("");
  const [subjectEntityName, setSubjectEntityName] = useState("");
  const [templateGroupName, setTemplateGroupName] = useState("");
  const [templateOwnerDept, setTemplateOwnerDept] = useState("");
  const [templateReportMonth, setTemplateReportMonth] = useState("");
  const [subjectReportMonth, setSubjectReportMonth] = useState("");
  const [subjectSelectedId, setSubjectSelectedId] = useState("");
  const [amountUnit, setAmountUnit] = useState<AmountUnit>("yuan");
  const [includeZeroRows, setIncludeZeroRows] = useState(false);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [report, setReport] = useState<ExpenseBudgetExecutionResponseDto | null>(null);
  const [templateMonthlyExpanded, setTemplateMonthlyExpanded] = useState(false);
  const [templateLastYearMonthlyExpanded, setTemplateLastYearMonthlyExpanded] = useState(false);
  const [templateExpanded, setTemplateExpanded] = useState<Record<number, boolean>>({});
  const [collapsedMetricGroups, setCollapsedMetricGroups] = useState<Record<string, boolean>>({});
  const [metricMonthlyExpanded, setMetricMonthlyExpanded] = useState<Record<string, boolean>>({});
  const [metricLastYearExpanded, setMetricLastYearExpanded] = useState<Record<string, boolean>>({});
  const [matrixMonthlyExpanded, setMatrixMonthlyExpanded] = useState(false);
  const [selectedTemplateSubjectId, setSelectedTemplateSubjectId] = useState<number | null>(null);
  const templateEntityHydratedRef = useRef(false);
  const templateGroupHydratedKeysRef = useRef<Set<string>>(new Set());
  const templateOwnerHydratedKeysRef = useRef<Set<string>>(new Set());
  const modeView = getExpenseBudgetExecutionModeView({ reportMode, templateKeyword, subjectKeyword });
  const { hasTreeSection, activeKeyword, keywordMode } = modeView;
  const amountDivisor = getExpenseBudgetExecutionAmountDivisor(amountUnit);
  const hasSelectedQueryEntity = Boolean(queryEntityName);
  const hasSelectedQueryGroup = Boolean(queryGroupName);
  const hasSelectedTemplateEntity = Boolean(templateEntityName);
  const hasSelectedTemplateGroup = Boolean(templateGroupName);
  const availableEntities = report?.available_entities ?? [];
  const queryScopeOptions = report?.template_scope_options ?? [];
  const templateGroupHydrationKey = templateEntityName;
  const templateOwnerHydrationKey = `${templateEntityName}::${templateGroupName}`;
  const templateScopeOptions = report?.template_scope_options ?? [];
  const subjectScopeTree = report?.subject_scope_tree ?? [];
  const normalizedSubjectSelectedId = normalizeExpenseBudgetExecutionSubjectId(subjectSelectedId);
  const selectedSubjectNode = useMemo(
    () =>
      normalizedSubjectSelectedId
        ? findExpenseBudgetExecutionSubjectScopeNodeById(subjectScopeTree, Number(normalizedSubjectSelectedId))
        : null,
    [normalizedSubjectSelectedId, subjectScopeTree],
  );
  const queryGroupOptions = useMemo(
    () => getExpenseBudgetExecutionGroupOptions(queryScopeOptions, queryEntityName),
    [queryEntityName, queryScopeOptions],
  );
  const queryOwnerOptions = useMemo(
    () => getExpenseBudgetExecutionOwnerOptions(queryScopeOptions, queryEntityName, queryGroupName),
    [queryEntityName, queryGroupName, queryScopeOptions],
  );
  const templateGroupOptions = useMemo(
    () => getExpenseBudgetExecutionGroupOptions(templateScopeOptions, templateEntityName),
    [templateEntityName, templateScopeOptions],
  );
  const templateOwnerOptions = useMemo(
    () => getExpenseBudgetExecutionOwnerOptions(templateScopeOptions, templateEntityName, templateGroupName),
    [templateEntityName, templateGroupName, templateScopeOptions],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedMode = normalizeExpenseBudgetExecutionReportMode(
      window.localStorage.getItem(expenseBudgetExecutionStorageKeys.reportMode),
    );
    if (savedMode) {
      setReportMode(savedMode);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedQueryMonth = window.localStorage.getItem(expenseBudgetExecutionStorageKeys.queryReportMonth);
    const normalizedQueryMonth = normalizeExpenseBudgetExecutionReportMonth(savedQueryMonth);
    if (normalizedQueryMonth) {
      setQueryReportMonth(normalizedQueryMonth);
    }
    const savedSubjectId = window.localStorage.getItem(expenseBudgetExecutionStorageKeys.subjectSelectedId);
    const normalizedSubjectId = normalizeExpenseBudgetExecutionSubjectId(savedSubjectId);
    if (normalizedSubjectId) {
      setSubjectSelectedId(normalizedSubjectId);
    }
    const savedSubjectMonth = window.localStorage.getItem(expenseBudgetExecutionStorageKeys.subjectReportMonth);
    const normalizedSubjectMonth = normalizeExpenseBudgetExecutionReportMonth(savedSubjectMonth);
    if (normalizedSubjectMonth) {
      setSubjectReportMonth(normalizedSubjectMonth);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedUnit = normalizeExpenseBudgetExecutionAmountUnit(
      window.localStorage.getItem(expenseBudgetExecutionStorageKeys.amountUnit),
    );
    if (savedUnit) {
      setAmountUnit(savedUnit);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.reportMode, reportMode);
  }, [reportMode]);

  const reportFilterState = useMemo(
    () => ({
      reportMode,
      perspective,
      amountUnit,
      activeKeyword,
      includeZeroRows,
      queryEntityName,
      queryGroupName,
      queryOwnerDept,
      queryReportMonth,
      subjectEntityName,
      subjectReportMonth,
      subjectSelectedId,
      templateEntityName,
      templateGroupName,
      templateOwnerDept,
      templateReportMonth,
    }),
    [
      activeKeyword,
      amountUnit,
      includeZeroRows,
      perspective,
      queryEntityName,
      queryGroupName,
      queryOwnerDept,
      queryReportMonth,
      reportMode,
      subjectEntityName,
      subjectReportMonth,
      subjectSelectedId,
      templateEntityName,
      templateGroupName,
      templateOwnerDept,
      templateReportMonth,
    ],
  );

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getExpenseBudgetExecutionReport(buildExpenseBudgetExecutionReportRequest(reportFilterState));
      setReport(result);
    } catch (e) {
      alert(e instanceof Error ? `加载费用预算执行报表失败：${e.message}` : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [reportFilterState]);

  useEffect(() => {
    if (reportMode !== "query") return;
    if (!report?.current_month) return;
    if (!queryReportMonth) {
      setQueryReportMonth(String(report.current_month));
    }
  }, [queryReportMonth, report?.current_month, reportMode]);

  useEffect(() => {
    if (reportMode !== "template") return;
    if (!report?.current_month) return;
    if (!templateReportMonth) {
      const savedMonth =
        typeof window !== "undefined"
          ? window.localStorage.getItem(expenseBudgetExecutionStorageKeys.templateReportMonth)
          : null;
      const normalizedSavedMonth = normalizeExpenseBudgetExecutionReportMonth(savedMonth);
      if (normalizedSavedMonth) {
        setTemplateReportMonth(normalizedSavedMonth);
        return;
      }
      setTemplateReportMonth(String(report.current_month));
    }
  }, [report?.current_month, reportMode, templateReportMonth]);

  useEffect(() => {
    if (reportMode !== "subject") return;
    if (!report?.current_month) return;
    if (!subjectReportMonth) {
      setSubjectReportMonth(String(report.current_month));
    }
  }, [report?.current_month, reportMode, subjectReportMonth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!queryReportMonth) return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.queryReportMonth, queryReportMonth);
  }, [queryReportMonth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!templateReportMonth) return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.templateReportMonth, templateReportMonth);
  }, [templateReportMonth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!subjectReportMonth) return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.subjectReportMonth, subjectReportMonth);
  }, [subjectReportMonth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!subjectSelectedId) {
      window.localStorage.removeItem(expenseBudgetExecutionStorageKeys.subjectSelectedId);
      return;
    }
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.subjectSelectedId, subjectSelectedId);
  }, [subjectSelectedId]);

  useEffect(() => {
    if (reportMode !== "template") return;
    const availableEntities = report?.available_entities ?? [];
    if (availableEntities.length === 0) return;
    if (templateEntityName || templateEntityHydratedRef.current) return;
    const savedEntity =
      typeof window !== "undefined"
        ? window.localStorage.getItem(expenseBudgetExecutionStorageKeys.templateEntity)
        : null;
    if (savedEntity && availableEntities.includes(savedEntity)) {
      setTemplateEntityName(savedEntity);
    }
    templateEntityHydratedRef.current = true;
  }, [report?.available_entities, reportMode, templateEntityName]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.templateEntity, templateEntityName);
  }, [templateEntityName]);

  useEffect(() => {
    if (reportMode !== "template") return;
    if (!hasSelectedTemplateEntity) {
      if (templateGroupName) setTemplateGroupName("");
      return;
    }
    if (templateGroupOptions.length === 0) {
      if (templateGroupName) setTemplateGroupName("");
      return;
    }
    if (templateGroupName || templateGroupHydratedKeysRef.current.has(templateGroupHydrationKey)) return;
    const savedGroup =
      typeof window !== "undefined"
        ? window.localStorage.getItem(expenseBudgetExecutionStorageKeys.templateGroup)
        : null;
    if (savedGroup && templateGroupOptions.includes(savedGroup)) {
      setTemplateGroupName(savedGroup);
    }
    templateGroupHydratedKeysRef.current.add(templateGroupHydrationKey);
  }, [hasSelectedTemplateEntity, reportMode, templateGroupHydrationKey, templateGroupName, templateGroupOptions]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.templateGroup, templateGroupName);
  }, [templateGroupName]);

  useEffect(() => {
    if (reportMode !== "template") return;
    if (!hasSelectedTemplateEntity || !hasSelectedTemplateGroup) {
      if (templateOwnerDept) setTemplateOwnerDept("");
      return;
    }
    if (templateOwnerOptions.length === 0) {
      if (templateOwnerDept) setTemplateOwnerDept("");
      return;
    }
    if (templateOwnerDept || templateOwnerHydratedKeysRef.current.has(templateOwnerHydrationKey)) return;
    const savedOwner =
      typeof window !== "undefined"
        ? window.localStorage.getItem(expenseBudgetExecutionStorageKeys.templateOwner)
        : null;
    if (savedOwner && templateOwnerOptions.includes(savedOwner)) {
      setTemplateOwnerDept(savedOwner);
    }
    templateOwnerHydratedKeysRef.current.add(templateOwnerHydrationKey);
  }, [hasSelectedTemplateEntity, hasSelectedTemplateGroup, reportMode, templateOwnerDept, templateOwnerHydrationKey, templateOwnerOptions]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.templateOwner, templateOwnerDept);
  }, [templateOwnerDept]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(expenseBudgetExecutionStorageKeys.amountUnit, amountUnit);
  }, [amountUnit]);

  useEffect(() => {
    if (hasTreeSection) {
      setTemplateExpanded({});
      setSelectedTemplateSubjectId(null);
    }
  }, [hasTreeSection, reportMode]);

  useEffect(() => {
    setCollapsedMetricGroups({});
    setMetricMonthlyExpanded({});
    setMetricLastYearExpanded({});
    setMatrixMonthlyExpanded(false);
  }, [report]);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  useEffect(() => {
    if (!hasTreeSection) return;
    const subjectTree = report?.subject_tree ?? [];
    if (subjectTree.length === 0) return;
    setTemplateExpanded((prev) => {
      if (Object.keys(prev).length > 0) return prev;
      const next: Record<number, boolean> = {};
      const walk = (nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[]) => {
        nodes.forEach((node) => {
          if (node.level_number <= 2) next[node.id] = true;
          walk(node.children);
        });
      };
      walk(subjectTree);
      return next;
    });
  }, [hasTreeSection, report]);

  useEffect(() => {
    if (reportMode !== "subject") return;
    if (report?.mode !== "subject") return;
    const normalized = report?.selected_entity_name ?? "";
    setSubjectEntityName((prev) => (prev === normalized ? prev : normalized));
  }, [report?.mode, report?.selected_entity_name, reportMode]);

  useEffect(() => {
    if (reportMode !== "subject") return;
    if (report?.mode !== "subject") return;
    const normalized = report?.selected_subject_id != null ? String(report.selected_subject_id) : "";
    setSubjectSelectedId((prev) => (prev === normalized ? prev : normalized));
  }, [report?.mode, report?.selected_subject_id, reportMode]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await exportExpenseBudgetExecutionReport(
        buildExpenseBudgetExecutionExportRequest({
          ...reportFilterState,
          includeMonthlyActuals: templateMonthlyExpanded,
          includeLastYearMonthlyActuals: templateLastYearMonthlyExpanded,
        }),
      );
      downloadBlob(blob, filename || "expense_budget_execution.xlsx");
    } catch (e) {
      alert(e instanceof Error ? `导出失败：${e.message}` : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const summaryText = useMemo(
    () => describeExpenseBudgetExecutionSummary(report, reportMode, selectedSubjectNode),
    [report, reportMode, selectedSubjectNode],
  );

  const reportTree = report?.subject_tree ?? [];
  const treeMeta = useMemo(() => getExpenseBudgetExecutionTreeMeta(report, reportMode), [report, reportMode]);
  const monthlyBusinessRows = report?.monthly_business_rows ?? [];
  const monthlyItRows = report?.monthly_it_rows ?? [];
  const monthlyManagedBlocks = report?.monthly_daily_managed_blocks ?? [];
  const monthlyOtherColumns = report?.monthly_daily_other_columns ?? [];
  const monthlyOtherRows = report?.monthly_daily_other_rows ?? [];
  const consistencyWarnings = report?.consistency_warnings ?? [];
  const visibleMonthlyLabels = useMemo(
    () => buildExpenseBudgetExecutionMonthlyLabels(report?.current_month),
    [report?.current_month],
  );
  const visibleLastYearMonthlyLabels = useMemo(
    () => buildExpenseBudgetExecutionLastYearMonthlyLabels(report?.budget_year),
    [report?.budget_year],
  );
  const metricTableProps = {
    amountDivisor,
    visibleMonthlyLabels,
    visibleLastYearMonthlyLabels,
    collapsedMetricGroups,
    setCollapsedMetricGroups,
    metricMonthlyExpanded,
    setMetricMonthlyExpanded,
    metricLastYearExpanded,
    setMetricLastYearExpanded,
  };

  const treeReport = (
    <ExpenseBudgetExecutionTreeReport
      reportMode={reportMode}
      title={treeMeta.title}
      nodeLabel={treeMeta.nodeLabel}
      loading={loading}
      loadingText={treeMeta.loadingText}
      rows={reportTree}
      amountDivisor={amountDivisor}
      visibleMonthlyLabels={visibleMonthlyLabels}
      visibleLastYearMonthlyLabels={visibleLastYearMonthlyLabels}
      expandedRows={templateExpanded}
      setExpandedRows={setTemplateExpanded}
      selectedRowId={selectedTemplateSubjectId}
      setSelectedRowId={setSelectedTemplateSubjectId}
      currentActualExpanded={templateMonthlyExpanded}
      setCurrentActualExpanded={setTemplateMonthlyExpanded}
      lastYearActualExpanded={templateLastYearMonthlyExpanded}
      setLastYearActualExpanded={setTemplateLastYearMonthlyExpanded}
    />
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-gray-800">费用预算执行报表</h3>
          <p className="text-xs text-gray-500 mt-1">
            {summaryText ||
              "保留原月报格式，同时支持部门模式按预算科目层级查看费用类型执行情况、科目模式按预算科目查看部门树费用分布"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void loadReport()}
            disabled={loading}
            className="px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 disabled:opacity-60 inline-flex items-center gap-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || loading}
            className="px-3 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 inline-flex items-center gap-1"
            title="导出当前报表"
          >
            <Download className="w-3.5 h-3.5" />
            {exporting ? "导出中..." : "导出Excel"}
          </button>
        </div>
      </div>

      <ExpenseBudgetExecutionControls
        reportMode={reportMode}
        setReportMode={setReportMode}
        loading={loading}
        availableEntities={availableEntities}
        currentMonth={report?.current_month ?? null}
        query={{
          entityName: queryEntityName,
          groupName: queryGroupName,
          ownerDept: queryOwnerDept,
          reportMonth: queryReportMonth,
          groupOptions: queryGroupOptions,
          ownerOptions: queryOwnerOptions,
          hasSelectedEntity: hasSelectedQueryEntity,
          hasSelectedGroup: hasSelectedQueryGroup,
          setEntityName: setQueryEntityName,
          setGroupName: setQueryGroupName,
          setOwnerDept: setQueryOwnerDept,
          setReportMonth: setQueryReportMonth,
        }}
        template={{
          entityName: templateEntityName,
          groupName: templateGroupName,
          ownerDept: templateOwnerDept,
          reportMonth: templateReportMonth,
          groupOptions: templateGroupOptions,
          ownerOptions: templateOwnerOptions,
          hasSelectedEntity: hasSelectedTemplateEntity,
          hasSelectedGroup: hasSelectedTemplateGroup,
          setEntityName: setTemplateEntityName,
          setGroupName: setTemplateGroupName,
          setOwnerDept: setTemplateOwnerDept,
          setReportMonth: setTemplateReportMonth,
        }}
        subject={{
          entityName: subjectEntityName,
          selectedSubjectId: subjectSelectedId,
          selectedSubjectNode,
          scopeTree: subjectScopeTree,
          reportMonth: subjectReportMonth,
          setEntityName: setSubjectEntityName,
          setSelectedSubjectId: setSubjectSelectedId,
          setReportMonth: setSubjectReportMonth,
        }}
        amountUnit={amountUnit}
        setAmountUnit={setAmountUnit}
        activeKeyword={activeKeyword}
        setActiveKeyword={(value) => {
          if (keywordMode === "template") {
            setTemplateKeyword(value);
          } else if (keywordMode === "subject") {
            setSubjectKeyword(value);
          }
        }}
        includeZeroRows={includeZeroRows}
        setIncludeZeroRows={setIncludeZeroRows}
        onQuery={() => void loadReport()}
      />

      {consistencyWarnings.length > 0 ? (
        <div className="max-h-36 flex-none overflow-y-auto border-b border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
            <div className="min-w-0 space-y-1">
              <div className="font-semibold">跨表同类指标数据不一致预警（{consistencyWarnings.length} 条）</div>
              {consistencyWarnings.slice(0, 12).map((warning, idx) => (
                <div key={`${warning.metric_name}-${warning.field}-${idx}`} className="leading-5">
                  {warning.message}
                  <span className="ml-1 text-amber-800">
                    {warning.values
                      .map((item) => `${item.report}: ${item.value == null ? "-" : item.value}`)
                      .join("；")}
                  </span>
                </div>
              ))}
              {consistencyWarnings.length > 12 ? (
                <div>还有 {consistencyWarnings.length - 12} 条，请导出或切换筛选条件后继续核对。</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {reportMode === "query" ? (
          <div className="p-4 space-y-4 bg-gray-50">
            {treeReport}
            <ExpenseBudgetExecutionMetricTable
              {...metricTableProps}
              title="1、业务费用"
              rows={monthlyBusinessRows}
              labelHeader="费用归属部门"
              mergeLabelCells
            />
            <ExpenseBudgetExecutionMetricTable
              {...metricTableProps}
              title="2、IT费用"
              rows={monthlyItRows}
              labelHeader="费用归属部门"
              mergeLabelCells
            />
            {monthlyManagedBlocks.length > 0 ? (
              <section className="space-y-4">
                <div className="px-1 pt-1 text-[13px] font-semibold text-slate-700">3、日常费用</div>
                {monthlyManagedBlocks.map((block) => (
                  <ExpenseBudgetExecutionMetricTable
                    key={block.title}
                    {...metricTableProps}
                    title={block.title}
                    rows={block.rows}
                    labelHeader="归口管理部门"
                    mergeLabelCells
                  />
                ))}
              </section>
            ) : null}
            <ExpenseBudgetExecutionMatrixTable
              title="3.2 日常费用-分解至使用部门"
              columns={monthlyOtherColumns}
              rows={monthlyOtherRows}
              amountDivisor={amountDivisor}
              visibleMonthlyLabels={visibleMonthlyLabels}
              monthlyExpanded={matrixMonthlyExpanded}
              setMonthlyExpanded={setMatrixMonthlyExpanded}
              collapsedMetricGroups={collapsedMetricGroups}
              setCollapsedMetricGroups={setCollapsedMetricGroups}
            />
          </div>
        ) : (
          treeReport
        )}
      </div>
    </div>
  );
}
