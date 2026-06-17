import { useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import { renderWorkspaceModule } from "@/app/workspaceCatalog";

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
    if (tabs.length > 8) {
      setVisibleTabs(tabs.slice(0, 8));
      setOverflowTabs(tabs.slice(8));
    } else {
      setVisibleTabs(tabs);
      setOverflowTabs([]);
    }
  }, [tabs]);

  const handleOverflowTabClick = (tab: Tab) => {
    onTabReorder(tab.id);
    setShowOverflow(false);
  };

  return (
    <div className="bb-app-chrome h-full flex flex-col">
      <div className="h-8 flex items-center bg-[var(--bb-bg-muted)] border-b border-[var(--bb-border)] relative">
        <div ref={tabBarRef} className="flex items-center gap-0.5 px-1 flex-1 overflow-hidden">
          {visibleTabs.map((tab) => (
            <div
              key={tab.id}
              className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors ${
                activeTab === tab.id
                  ? "bg-white text-[var(--bb-text-strong)] border-t-2 border-[var(--bb-primary)]"
                  : "bg-transparent text-[var(--bb-text-muted)] hover:bg-[var(--bb-bg-subtle)]"
              }`}
              onClick={() => onTabClick(tab.id)}
            >
              <span className="text-xs whitespace-nowrap">{tab.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onTabClose(tab.id);
                }}
                className="hover:bg-[var(--bb-bg-muted)] rounded p-0.5"
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
              className="px-2 py-1.5 text-[var(--bb-text-muted)] hover:text-[var(--bb-text-strong)] hover:bg-[var(--bb-bg-subtle)] border-l border-[var(--bb-border)]"
              title="更多标签"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>

            {showOverflow && (
              <div className="bb-popover absolute right-0 top-full mt-1 z-20 min-w-[150px]">
                {overflowTabs.map((tab) => (
                  <div
                    key={tab.id}
                    className="flex items-center justify-between px-3 py-2 hover:bg-[var(--bb-bg-subtle)] cursor-pointer text-xs border-b border-[var(--bb-border-soft)] last:border-b-0"
                    onClick={() => handleOverflowTabClick(tab)}
                  >
                    <span className="text-[var(--bb-text)]">{tab.title}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onTabClose(tab.id);
                        setShowOverflow(false);
                      }}
                      className="ml-2 hover:bg-[var(--bb-bg-muted)] rounded p-0.5"
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
          <div className="h-full bg-[var(--bb-bg-page)] p-6 md:p-8 overflow-auto">
            <div className="max-w-5xl mx-auto bb-panel p-6 md:p-8">
              <h2 className="text-base font-semibold text-[var(--bb-text-strong)] mb-4">欢迎使用管衡之家--银行财务预算智能体</h2>
              <p className="text-sm text-[var(--bb-text)] leading-relaxed mb-6">
                本系统围绕预算管理、部门费用预算管理、多维分析工具和系统配置中心组织工作区。当前指标体系以“机构及产品指标”为唯一配置入口，预算事实和报表直接使用同一体系主键。
              </p>

              <section className="mb-6">
                <h3 className="text-base font-semibold text-gray-800 mb-3">当前业务入口</h3>
                <div className="space-y-3 text-sm text-gray-700 leading-relaxed">
                  <p>
                    <span className="font-medium text-gray-800">1）规则配置台与主数据：</span>
                    机构及产品承载机构与产品主表；机构及产品指标承载指标编码、公式和录入口径，并作为唯一指标配置入口。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">2）预算管理：</span>
                    通过机构及产品数据录入确认并写入预算事实，并在预算展示报表与模拟测算模块中复核结果。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">3）部门费用预算管理模块：</span>
                    费用执行明细导入、费用预测逻辑配置、部门费用预测、费用预算执行报表和投入产出专题概览使用同一套部门费用管理目录。
                  </p>
                  <p>
                    <span className="font-medium text-gray-800">4）多维分析工具：</span>
                    当前年度透视、多年度对比透视、透视图、智能分析报告和智能演示 PPT 读取预算系统形成的结果口径。
                  </p>
                </div>
              </section>

              <section>
                <h3 className="text-base font-semibold text-gray-800 mb-3">推荐检查顺序</h3>
                <ol className="list-decimal list-inside space-y-2 text-sm text-gray-700 leading-relaxed">
                  <li>先确认机构及产品、机构及产品指标、部门科目、部门预算科目和 BI 映射。</li>
                  <li>再通过机构及产品数据录入写入预算事实，并导入费用执行明细。</li>
                  <li>最后查看预算展示报表、费用预算执行报表和多维分析结果。</li>
                </ol>
              </section>
            </div>
          </div>
        ) : (
          renderWorkspaceModule(activeTab)
        )}
      </div>
    </div>
  );
}
