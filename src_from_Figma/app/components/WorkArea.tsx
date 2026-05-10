import { useState, useRef, useEffect } from "react";
import { X, Plus, ChevronDown } from "lucide-react";
import { DataAccountContent, DataReportContent, DataProductContent, DataDepartmentContent, BudgetInputContent, PivotTableContent, AnalysisReportContent, AnalysisPPTContent } from "./TabContent";

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
    // 根据不同的 tab ID 渲染不同的内容
    switch (tabId) {
      case "data-account":
        return <DataAccountContent />;
      case "data-report":
        return <DataReportContent />;
      case "data-product":
        return <DataProductContent />;
      case "data-department":
        return <DataDepartmentContent />;
      case "input-basic":
        return <BudgetInputContent />;
      case "analysis-pivot-table":
        return <PivotTableContent />;
      case "analysis-pivot-chart":
        return <div className="p-4"><h3 className="text-sm font-medium text-gray-800">数据透视图</h3><p className="text-xs text-gray-600 mt-2">此处为数据透视图分析工具...</p></div>;
      case "analysis-report":
        return <AnalysisReportContent />;
      case "analysis-ppt":
        return <AnalysisPPTContent />;
      case "config-user":
        return <div className="p-4"><h3 className="text-sm font-medium text-gray-800">用户和权限管理</h3><p className="text-xs text-gray-600 mt-2">此处为用户和权限管理界面...</p></div>;
      case "config-system":
        return <div className="p-4"><h3 className="text-sm font-medium text-gray-800">系统设定控制</h3><p className="text-xs text-gray-600 mt-2">此处为系统设定控制界面...</p></div>;
      case "help-guide":
        return (
          <div className="p-4 h-full overflow-auto">
            <h3 className="text-sm font-medium text-gray-800 mb-3">使用说明</h3>
            <div className="text-xs text-gray-700 space-y-3">
              <section>
                <h4 className="font-medium text-gray-800 mb-2">系统概述</h4>
                <p className="text-gray-600 leading-relaxed">银行财务预算管理系统是一款专为银行业务设计的预算编制、管理和分析工具，支持多维度数据录入和智能分析。</p>
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
                <p className="text-xs text-gray-600 leading-relaxed">A: 进入相应的科目维护界面，点击新增按钮，填写科目信息后保存即可。</p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 标签页太多时如何管理？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">A: 超过8个标签时，右侧会出现扩展按钮，点击可查看隐藏的标签。点击隐藏标签可将其移到第一位。</p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 如何调整左右面板的宽度？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">A: 将鼠标移到面板之间的分隔线上，按住拖动即可调整宽度。</p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 智能助手可以做什么？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">A: 智能助手可以回答预算相关问题、提供操作建议、支持文件上传和语音交互。</p>
              </div>
              <div className="border-b border-gray-200 pb-3">
                <h4 className="text-xs font-medium text-gray-800 mb-1.5">Q: 如何导出分析报告？</h4>
                <p className="text-xs text-gray-600 leading-relaxed">A: 在多维分析工具中生成报告后，可以导出为Excel、PDF或PPT格式。</p>
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
        return <div className="p-4"><p className="text-xs text-gray-600">未知页面</p></div>;
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
          <div className="h-full flex items-center justify-center bg-gray-50">
            <div className="text-center">
              <h2 className="text-lg font-medium text-gray-800 mb-2">欢迎使用银行财务预算管理系统</h2>
              <p className="text-xs text-gray-600">请从左侧导航栏选择功能模块开始工作</p>
            </div>
          </div>
        ) : (
          renderTabContent(activeTab)
        )}
      </div>
    </div>
  );
}
