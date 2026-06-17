import type { ReactNode } from "react";
import { BarChart3, Database, FileInput, HelpCircle, Settings } from "lucide-react";
import { BudgetSubjectCatalogContent } from "./components/budget/BudgetSubjectCatalogContent";
import { OrgProductContent } from "./components/org-product/OrgProductContent";
import { OrgProductMetricContent } from "./components/org-product/OrgProductMetricContent";
import { OrgProductDataEntryContent } from "./components/org-product/OrgProductDataEntryContent";
import { OrgProductForecastOutputContent } from "./components/org-product/OrgProductForecastOutputContent";
import { ExpenseActualImportContent } from "./components/expense/ExpenseActualImportContent";
import { ExpenseBudgetEntryContent } from "./components/expense/ExpenseBudgetEntryContent";
import { BiMappingContent } from "./components/business/BiMappingContent";
import { DataDepartmentContent } from "./components/business/DataDepartmentContent";
import { BudgetActualBatchContent } from "./components/budget/BudgetActualBatchContent";
import { ExpenseForecastContent } from "./components/expense/ExpenseForecastContent";
import { ExpenseForecastRuleContent } from "./components/expense/ExpenseForecastRuleContent";
import { PivotTableContent } from "./components/analysis/PivotTableContent";
import { ExpenseBudgetExecutionContent } from "./components/expense/ExpenseBudgetExecutionContent";
import { BusinessCostIncomeRatioActualImportContent } from "./components/business/BusinessCostIncomeRatioActualImportContent";
import { BusinessCostIncomeRatioAdminContent } from "./components/business/BusinessCostIncomeRatioAdminContent";
import { PivotChartContent } from "./components/analysis/PivotChartContent";
import { AnalysisReportContent } from "./components/analysis/AnalysisReportContent";
import { AnalysisPPTContent } from "./components/analysis/AnalysisPPTContent";
import { InputOutputTopicOverviewContent } from "./components/analysis/InputOutputTopicOverviewContent";
import { ConfigSystemContent } from "./components/system/ConfigSystemContent";
import { DataSyncManagementContent } from "./components/analysis/DataSyncManagementContent";
import { ConfigUserContent } from "./components/system/ConfigUserContent";
import { AgentDialogTestContent } from "./components/agent/AgentDialogTestContent";
import { BudgetSimulationContent } from "./components/budget/BudgetSimulationContent";
import { BudgetSimulationReverseContent } from "./components/budget/BudgetSimulationReverseContent";
import { BudgetDisplayReportContent } from "./components/budget/BudgetDisplayReportContent";
import { IntelligentBudgetSimulationContent } from "./components/budget/IntelligentBudgetSimulationContent";

export type WorkspaceNode = {
  id: string;
  label: string;
  icon: ReactNode | null;
  children?: WorkspaceNode[];
  requiredPermission?: 1 | 2 | 3;
  diagnostic?: boolean;
  render?: () => ReactNode;
};

function helpGuide() {
  return (
    <div className="p-4 h-full overflow-auto">
      <h3 className="text-sm font-medium text-gray-800 mb-3">使用说明</h3>
      <div className="text-xs text-gray-700 space-y-3">
        <section>
          <h4 className="font-medium text-gray-800 mb-2">当前业务主线</h4>
          <p className="text-gray-600 leading-relaxed">
            预算管理以机构及产品、机构及产品指标、机构及产品数据录入、预算输出报表和模拟测算形成闭环；部门费用预算管理以部门科目、部门预算科目、BI 映射、费用执行明细、费用预测和费用预算执行报表形成闭环。
          </p>
        </section>
        <section>
          <h4 className="font-medium text-gray-800 mb-2">口径优先级</h4>
          <ul className="list-disc list-inside space-y-1.5 text-gray-600">
            <li>指标体系以机构及产品指标为唯一配置入口，所有预算事实和报表直接使用同一套指标主键。</li>
            <li>预算事实录入以机构及产品数据录入为唯一人工入口，年度库的预算明细、汇总表和对比库读模型为运行结果。</li>
            <li>费用执行明细导入后作为费用预测和费用预算执行报表的实际数来源。</li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function helpFaq() {
  return (
    <div className="p-4 h-full overflow-auto">
      <h3 className="text-sm font-medium text-gray-800 mb-3">常见问题</h3>
      <div className="space-y-3">
        <div className="border-b border-gray-200 pb-3">
          <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 指标编码还有第二套维护入口吗？</h4>
          <p className="text-xs text-gray-600 leading-relaxed">
            A: 不能。请在“机构及产品指标”维护唯一指标体系；系统运行数据会直接引用同一套指标主键。
          </p>
        </div>
        <div className="border-b border-gray-200 pb-3">
          <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 费用执行明细应该在哪里导入？</h4>
          <p className="text-xs text-gray-600 leading-relaxed">
            A: 进入部门费用预算管理模块下的“费用执行明细导入”，导入后再查看费用预测和费用预算执行报表。
          </p>
        </div>
        <div className="border-b border-gray-200 pb-3">
          <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 智能分析报告和智能演示PPT 使用哪套数据？</h4>
          <p className="text-xs text-gray-600 leading-relaxed">
            A: 它们读取当前预算系统的汇总和对比读模型，不维护第二套主数据。
          </p>
        </div>
      </div>
    </div>
  );
}

function helpContact() {
  return (
    <div className="p-4 h-full overflow-auto">
      <h3 className="text-sm font-medium text-gray-800 mb-3">联系管理员</h3>
      <div className="rounded border border-[var(--bb-border)] bg-[var(--bb-bg-subtle)] p-3 text-xs text-[var(--bb-text)]">
        请联系本系统部署环境中配置的预算系统管理员；用户、权限、年度库和展示版本问题均由系统配置中心统一维护。
      </div>
    </div>
  );
}

export const workspaceTree: WorkspaceNode[] = [
  {
    id: "budget",
    label: "预算管理",
    icon: <FileInput className="w-3.5 h-3.5" />,
    children: [
      {
        id: "budget-rule-config",
        label: "规则配置台",
        icon: null,
        children: [
          { id: "org-product-tree", label: "机构及产品", icon: null, render: () => <OrgProductContent /> },
          { id: "org-product-metrics", label: "机构及产品指标", icon: null, render: () => <OrgProductMetricContent /> },
        ],
      },
      {
        id: "budget-input",
        label: "预算数据输入",
        icon: null,
        requiredPermission: 2,
        children: [
          { id: "org-product-data-entry", label: "机构及产品数据录入", icon: null, render: () => <OrgProductDataEntryContent /> },
          { id: "org-product-forecast-output", label: "机构及产品预测输出", icon: null, render: () => <OrgProductForecastOutputContent /> },
        ],
      },
      {
        id: "budget-output-report",
        label: "预算输出报表展示",
        icon: null,
        requiredPermission: 1,
        children: [
          { id: "budget-output-display-report", label: "预算展示报表", icon: null, render: () => <BudgetDisplayReportContent /> },
        ],
      },
      {
        id: "budget-simulation",
        label: "模拟测算模块",
        icon: null,
        requiredPermission: 2,
        children: [
          { id: "input-simulation", label: "模拟测算（正算）", icon: null, render: () => <BudgetSimulationContent /> },
          { id: "input-simulation-reverse", label: "模拟测算（倒算）", icon: null, render: () => <BudgetSimulationReverseContent /> },
          { id: "intelligent-budget-simulation", label: "智能预算模拟", icon: null, render: () => <IntelligentBudgetSimulationContent /> },
        ],
      },
    ],
  },
  {
    id: "department-expense-budget",
    label: "部门费用预算管理模块",
    icon: <Database className="w-3.5 h-3.5" />,
    children: [
      { id: "data-department", label: "部门科目维护", icon: null, render: () => <DataDepartmentContent /> },
      { id: "data-budget-subject", label: "部门预算科目维护", icon: null, render: () => <BudgetSubjectCatalogContent /> },
      { id: "data-bi-mapping", label: "BI映射维护", icon: null, render: () => <BiMappingContent /> },
      { id: "input-expense-budget-entry", label: "预算录入", icon: null, requiredPermission: 2, render: () => <ExpenseBudgetEntryContent /> },
      { id: "input-expense-actual-import", label: "费用执行明细导入", icon: null, requiredPermission: 2, render: () => <ExpenseActualImportContent /> },
      { id: "input-expense-forecast-rule", label: "费用预测逻辑配置", icon: null, requiredPermission: 2, render: () => <ExpenseForecastRuleContent /> },
      { id: "input-expense-forecast", label: "部门费用预测", icon: null, requiredPermission: 2, render: () => <ExpenseForecastContent /> },
      { id: "analysis-expense-budget-execution", label: "费用预算执行报表", icon: null, requiredPermission: 1, render: () => <ExpenseBudgetExecutionContent /> },
      { id: "input-business-cost-income-ratio-actual-import", label: "业务支出成本收入比实际导入", icon: null, requiredPermission: 2, render: () => <BusinessCostIncomeRatioActualImportContent /> },
      { id: "department-expense-business-cost-income-ratio-admin", label: "业务支出成本收入比维护", icon: null, render: () => <BusinessCostIncomeRatioAdminContent /> },
      { id: "department-expense-input-output-topic-overview", label: "投入产出专题概览", icon: null, requiredPermission: 1, render: () => <InputOutputTopicOverviewContent /> },
    ],
  },
  {
    id: "analysis",
    label: "多维分析工具",
    icon: <BarChart3 className="w-3.5 h-3.5" />,
    requiredPermission: 1,
    children: [
      { id: "analysis-pivot-table-current", label: "当前可编辑年度多版本透视报表", icon: null, render: () => <PivotTableContent dataSource="budget" /> },
      { id: "analysis-pivot-table-compare", label: "多年度对比透视报表", icon: null, render: () => <PivotTableContent dataSource="compare" /> },
      { id: "analysis-pivot-chart", label: "多年度数据透视图", icon: null, render: () => <PivotChartContent /> },
      { id: "analysis-report", label: "智能分析报告", icon: null, render: () => <AnalysisReportContent /> },
      { id: "analysis-ppt", label: "智能演示PPT", icon: null, render: () => <AnalysisPPTContent /> },
    ],
  },
  {
    id: "config",
    label: "系统配置中心",
    icon: <Settings className="w-3.5 h-3.5" />,
    children: [
      { id: "config-user", label: "用户和权限管理", icon: null, render: () => <ConfigUserContent /> },
      { id: "config-system", label: "系统设定控制", icon: null, render: () => <ConfigSystemContent /> },
      { id: "config-data-sync", label: "数据同步管理", icon: null, render: () => <DataSyncManagementContent /> },
      { id: "budget-actual-batch", label: "预算事实刷新跑批", icon: null, requiredPermission: 2, render: () => <BudgetActualBatchContent /> },
      { id: "config-agent-debug", label: "Agent对话测试", icon: null, diagnostic: true, render: () => <AgentDialogTestContent /> },
    ],
  },
  {
    id: "help",
    label: "帮助与使用说明",
    icon: <HelpCircle className="w-3.5 h-3.5" />,
    requiredPermission: 1,
    children: [
      { id: "help-guide", label: "使用说明", icon: null, render: helpGuide },
      { id: "help-faq", label: "常见问题", icon: null, render: helpFaq },
      { id: "help-contact", label: "联系管理员", icon: null, render: helpContact },
    ],
  },
];

function hasPermission(permissionType: number, required: number): boolean {
  if (permissionType === 1) return true;
  if (permissionType === 2) return required <= 2;
  return required <= 1;
}

export function filterWorkspaceTreeByPermission(nodes: WorkspaceNode[], permissionType: number): WorkspaceNode[] {
  const result: WorkspaceNode[] = [];
  for (const node of nodes) {
    const filteredChildren = node.children
      ? filterWorkspaceTreeByPermission(node.children, permissionType)
      : undefined;
    const required = node.requiredPermission ?? (node.render ? 3 : undefined);
    if (required !== undefined && !hasPermission(permissionType, required)) {
      continue;
    }
    if (node.children && filteredChildren?.length === 0) {
      continue;
    }
    result.push({
      ...node,
      children: filteredChildren,
    });
  }
  return result;
}

export function renderWorkspaceModule(moduleId: string): ReactNode {
  const stack = [...workspaceTree];
  while (stack.length > 0) {
    const node = stack.shift();
    if (!node) continue;
    if (node.id === moduleId && node.render) {
      return node.render();
    }
    if (node.children) {
      stack.push(...node.children);
    }
  }
  return (
    <div className="p-4">
      <p className="text-xs text-gray-600">未知页面</p>
    </div>
  );
}
