import { useState, useRef, useEffect } from "react";
import { X, ChevronDown } from "lucide-react";
import { DataAccountContent } from "./DataAccountContent";
import { BudgetSubjectCatalogContent } from "./BudgetSubjectCatalogContent";
import { DataProductContent } from "./DataProductContent";
import { ExpenseActualImportContent } from "./ExpenseActualImportContent";
import { DataReportContent } from "./DataReportContent";
import { DataDepartmentContent } from "./DataDepartmentContent";
import { BudgetInputContent } from "./BudgetInputContent";
import { ExpenseForecastContent } from "./ExpenseForecastContent";
import { BudgetAssumptionContent } from "./BudgetAssumptionContent";
import { ForecastWorkbenchContent } from "./ForecastWorkbenchContent";
import { PivotTableContent } from "./PivotTableContent";
import { ExpenseBudgetExecutionContent } from "./ExpenseBudgetExecutionContent";
import { PivotChartContent } from "./PivotChartContent";
import { AnalysisReportContent } from "./AnalysisReportContent";
import { AnalysisPPTContent } from "./AnalysisPPTContent";
import { ConfigSystemContent } from "./ConfigSystemContent";
import { DataSyncManagementContent } from "./DataSyncManagementContent";
import { ConfigUserContent } from "./ConfigUserContent";
import { AgentDialogTestContent } from "./AgentDialogTestContent";
import { BudgetPredictionContent } from "./BudgetPredictionContent";

export interface Tab {
  id: string;
  title: string;
}

interface WorkAreaProps {
  tabs: Tab[];
  activeTab: string;
  onTabClick: (id: string) => void;
  onTabClose: (id: string) => void;
  onTabReorder: (id: string) => void;
}

export function WorkArea({ tabs, activeTab, onTabClick, onTabClose, onTabReorder }: WorkAreaProps) {
  const [showOverflow, setShowOverflow] = useState(false);
  const [visibleTabs, setVisibleTabs] = useState<Tab[]>(tabs);
  const [overflowTabs, setOverflowTabs] = useState<Tab[]>([]);
  const tabBarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 简单实现：假设超过8个标签就会溢出
    if (tabs.length > 8) {
      setVisibleTabs(tabs.slice(0, 8));
      setOverflowTabs(tabs.slice(8));
    } else {
      setVisibleTabs(tabs);
      setOverflowTabs([]);
    }
  }, [tabs]);

  const handleOverflowTabClick = (tab: Tab) => {
    // 将点击的标签移到第一个位置
    onTabReorder(tab.id);
    setShowOverflow(false);
  };

  const renderTabContent = (tabId: string) => {
    switch (tabId) {
      case "data-account":
        return <DataAccountContent />;
      case "data-budget-subject":
        return <BudgetSubjectCatalogContent />;
      case "data-report":
        return <DataReportContent />;
      case "data-product":
        return <DataProductContent />;
      case "data-department":
        return <DataDepartmentContent />;
      case "input-basic":
        return <BudgetInputContent />;
      case "forecast-workbench":
        return <ForecastWorkbenchContent />;
      case "input-prediction":
        return <BudgetPredictionContent />;
      case "assumption-basic":
        return <BudgetAssumptionContent />;
      case "input-expense-actual-import":
        return <ExpenseActualImportContent />;
      case "input-expense-forecast":
        return <ExpenseForecastContent />;
      case "analysis-pivot-table-current":
        return <PivotTableContent dataSource="budget" />;
      case "analysis-pivot-table-compare":
        return <PivotTableContent dataSource="compare" />;
      case "analysis-expense-budget-execution":
        return <ExpenseBudgetExecutionContent />;
      case "analysis-pivot-chart":
        return <PivotChartContent />;
      case "analysis-report":
        return <AnalysisReportContent />;
      case "analysis-ppt":
        return <AnalysisPPTContent />;
      case "config-user":
        return <ConfigUserContent />;
      case "config-system":
        return <ConfigSystemContent />;
      case "config-data-sync":
        return <DataSyncManagementContent />;
      case "config-agent-debug":
        return <AgentDialogTestContent />;
      case "help-guide":
        return (
          <div className="p-4 h-full overflow-auto">
            <h3 className="text-sm font-medium text-gray-800 mb-3">使用说明</h3>
            <div className="text-xs text-gray-700 space-y-3">
              <section>
                <h4 className="font-medium text-gray-800 mb-2">系统概述</h4>
                <p className="text-gray-600 leading-relaxed">
                  银行财务预算管理系统是一款专为银行业务设计的预算编制、管理和分析工具，支持多维度数据录入和智能分析。
                </p>
              </section>
              <section>
                <h4 className="font-medium text-gray-800 mb-2">快速开始</h4>
                <ol className="list-decimal list-inside space-y-1.5 text-gray-600">
                  <li>从左侧导航栏选择功能模块</li>
                  <li>在工作区中打开相应的标签页</li>
                  <li>使用右侧智能助手获取帮助和建议</li>
                </ol>
              </section>
              <section>
                <h4 className="font-medium text-gray-800 mb-2">主要功能</h4>
                <ul className="list-disc list-inside space-y-1.5 text-gray-600">
                  <li>基础数据维护：管理数据科目、报表科目、产品科目和部门科目</li>
                  <li>预算数据输入：录入和维护预算基础数据</li>
                  <li>多维分析工具：提供数据透视表、透视图、智能报告和PPT生成</li>
                  <li>系统配置：用户权限管理和系统参数设置</li>
                </ul>
              </section>
            </div>
          </div>
        );
      case "help-faq":
        return (
          <div className="p-4 h-full overflow-auto">
            <h3 className="text-sm font-medium text-gray-800 mb-3">常见问题</h3>
            <div className="space-y-3">
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 如何新增科目？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  A: 进入相应的科目维护界面，点击新增按钮，填写科目信息后保存即可。
                </p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 标签页太多时如何管理？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  A: 超过8个标签时，右侧会出现扩展按钮，点击可查看隐藏的标签。点击隐藏标签可将其移到第一位。
                </p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 如何调整左右面板的宽度？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  A: 将鼠标移到面板之间的分隔线上，按住拖动即可调整宽度。
                </p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 智能助手可以做什么？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  A: 智能助手可以回答预算相关问题、提供操作建议、支持文件上传和语音交互。
                </p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 如何导出分析报告？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  A: 在多维分析工具中生成报告后，可以导出为Excel、PDF或PPT格式。
                </p>
              </div>
            </div>
          </div>
        );
      case "help-contact":
        return (
          <div className="p-4 h-full overflow-auto">
            <h3 className="text-sm font-medium text-gray-800 mb-3">联系管理员</h3>
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded p-3">
                <h4 className="text-xs font-medium text-gray-800 mb-2">技术支持</h4>
                <div className="space-y-1.5 text-xs text-gray-700">
                  <p><span className="font-medium">联系人：</span>李明</p>
                  <p><span className="font-medium">电话：</span>010-12345678 转 8001</p>
                  <p><span className="font-medium">邮箱：</span>support@bank.com</p>
                  <p><span className="font-medium">工作时间：</span>周一至周五 9:00-18:00</p>
                </div>
              </div>
              <div className="bg-green-50 border border-green-200 rounded p-3">
                <h4 className="text-xs font-medium text-gray-800 mb-2">业务咨询</h4>
                <div className="space-y-1.5 text-xs text-gray-700">
                  <p><span className="font-medium">联系人：</span>王芳</p>
                  <p><span className="font-medium">电话：</span>010-12345678 转 8002</p>
                  <p><span className="font-medium">邮箱：</span>business@bank.com</p>
                  <p><span className="font-medium">工作时间：</span>周一至周五 9:00-18:00</p>
                </div>
              </div>
              <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                <h4 className="text-xs font-medium text-gray-800 mb-2">紧急联系</h4>
                <div className="space-y-1.5 text-xs text-gray-700">
                  <p><span className="font-medium">24小时热线：</span>400-888-9999</p>
                  <p className="text-gray-600 mt-2">如遇紧急问题或系统故障，请拨打24小时热线，我们将第一时间为您解决。</p>
                </div>
              </div>
            </div>
          </div>
        );
      default:
        return (
          <div className="p-4">
            <p className="text-xs text-gray-600">未知页面</p>
          </div>
        );
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="h-8 flex items-center bg-[#ecf0f1] border-b border-gray-300 relative">
        <div ref={tabBarRef} className="flex items-center gap-0.5 px-1 flex-1 overflow-hidden">
          {visibleTabs.map((tab) => (
            <div
              key={tab.id}
              className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors ${
                activeTab === tab.id
                  ? "bg-white text-gray-800 border-t-2 border-[#3498db]"
                  : "bg-transparent text-gray-600 hover:bg-gray-100"
              }`}
              onClick={() => onTabClick(tab.id)}
            >
              <span className="text-xs whitespace-nowrap">{tab.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onTabClose(tab.id);
                }}
                className="hover:bg-gray-200 rounded p-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>

        {overflowTabs.length > 0 && (
          <div className="relative">
            <button
              onClick={() => setShowOverflow(!showOverflow)}
              className="px-2 py-1.5 text-gray-600 hover:text-gray-800 hover:bg-gray-100 border-l border-gray-300"
              title="更多标签"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>

            {showOverflow && (
              <div className="absolute right-0 top-full mt-1 bg-white border border-gray-300 rounded shadow-lg z-20 min-w-[150px]">
                {overflowTabs.map((tab) => (
                  <div
                    key={tab.id}
                    className="flex items-center justify-between px-3 py-2 hover:bg-gray-100 cursor-pointer text-xs border-b border-gray-200 last:border-b-0"
                    onClick={() => handleOverflowTabClick(tab)}
                  >
                    <span className="text-gray-700">{tab.title}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onTabClose(tab.id);
                        setShowOverflow(false);
                      }}
                      className="ml-2 hover:bg-gray-200 rounded p-0.5"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {tabs.length === 0 ? (
          <div className="h-full bg-gray-50 p-6 md:p-8 overflow-auto">
            <div className="max-w-5xl mx-auto bg-white border border-gray-200 rounded-lg shadow-sm p-6 md:p-8">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">欢迎使用管衡之家--银行财务预算智能体</h2>
              <p className="text-sm text-gray-700 leading-relaxed mb-6">
                本系统面向银行预算编制、录入、分析与复盘场景。你可以从左侧导航进入不同业务模块，在中间工作区以多标签方式并行处理任务，
                也可以通过右侧智能助手快速完成澄清、查询与分析。
              </p>

              <section className="mb-6">
                <h3 className="text-base font-semibold text-gray-800 mb-3">左侧导航栏：功能模块说明</h3>
                <div className="space-y-3 text-sm text-gray-700 leading-relaxed">
                  <p>
                    <span className="font-medium text-gray-800">1）基础数据维护：</span>
                    维护数据科目、报告科目、产品科目和部门科目。建议先完成主数据和映射关系，再进行预算录入与分析，避免出现“科目不存在”或口径不一致。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">2）预算数据输入：</span>
                    进入预算基础数据维护后，可以按产品、期间和预算/实际口径进行录入与修订。数据写入后可配合重算与透视分析快速验证结果是否符合预期。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">3）多维分析工具：</span>
                    包含数据透视表、透视图、智能分析报告与智能演示 PPT。适合从“汇总看趋势”到“明细做钻取”的完整分析流程。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">4）系统配置与帮助：</span>
                    可查看系统设定、帮助说明、常见问题和联系信息，方便快速上手与排障。
                  </p>
                </div>
              </section>

              <section className="mb-6">
                <h3 className="text-base font-semibold text-gray-800 mb-3">右侧聊天机器人：推荐使用方式</h3>
                <div className="space-y-3 text-sm text-gray-700 leading-relaxed">
                  <p>
                    <span className="font-medium text-gray-800">先说目标，再补条件：</span>
                    例如“分析个人金融部预算执行差异”，机器人会自动提示缺失要素（时间范围、对比方式、粒度等），并提供可点击的候选项。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">支持澄清与重跑：</span>
                    你可以点击“按默认执行”或“按当前口径重跑”，快速触发只读查询。若结果不满意，可点“不满意”进入二次澄清并继续迭代。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">分析结果可沉淀经验：</span>
                    有效会话会写入长期记忆，后续可减少重复追问，让机器人更贴合你的分析习惯。
                  </p>
                </div>
              </section>

              <section>
                <h3 className="text-base font-semibold text-gray-800 mb-3">快速开始（建议顺序）</h3>
                <ol className="list-decimal list-inside space-y-2 text-sm text-gray-700 leading-relaxed">
                  <li>先在“基础数据维护”确认科目、产品、部门及映射关系。</li>
                  <li>进入“预算数据输入”完成预算/实际数据录入或导入。</li>
                  <li>在“多维分析工具”中查看透视结果，再结合右侧机器人做进一步分析与解释。</li>
                </ol>
              </section>
            </div>
          </div>
        ) : (
          renderTabContent(activeTab)
        )}
      </div>
    </div>
  );
}
