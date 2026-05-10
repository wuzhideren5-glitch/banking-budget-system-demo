import { useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Header } from "./components/Header";
import { NavigationTree } from "./components/NavigationTree";
import { ChatBot } from "./components/ChatBot";
import { WorkArea, Tab } from "./components/WorkArea";
import { StatusBar } from "./components/StatusBar";
import { ChevronLeft, ChevronRight } from "lucide-react";

export default function App() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTab, setActiveTab] = useState<string>("");

  const handleNavigationClick = (id: string, label: string) => {
    // 检查标签是否已经存在
    const existingTab = tabs.find(tab => tab.id === id);
    if (existingTab) {
      // 如果已存在，直接激活
      setActiveTab(id);
    } else {
      // 如果不存在，创建新标签
      const newTab: Tab = { id, title: label };
      setTabs([...tabs, newTab]);
      setActiveTab(id);
    }
  };

  const handleTabClose = (id: string) => {
    const newTabs = tabs.filter(tab => tab.id !== id);
    setTabs(newTabs);

    // 如果关闭的是当前激活的标签，激活前一个标签
    if (activeTab === id && newTabs.length > 0) {
      setActiveTab(newTabs[newTabs.length - 1].id);
    } else if (newTabs.length === 0) {
      setActiveTab("");
    }
  };

  const handleTabClick = (id: string) => {
    setActiveTab(id);
  };

  const handleTabReorder = (id: string) => {
    // 将指定的标签移到第一个位置
    const tab = tabs.find(t => t.id === id);
    if (tab) {
      const newTabs = [tab, ...tabs.filter(t => t.id !== id)];
      setTabs(newTabs);
      setActiveTab(id);
    }
  };

  return (
    <div className="size-full flex flex-col bg-[#ecf0f1]">
      <Header />

      <div className="flex-1 overflow-hidden flex">
        {/* 左侧导航折叠按钮 */}
        {leftCollapsed && (
          <div className="w-8 bg-[#f5f6fa] border-r border-gray-300 flex items-start justify-center pt-2 flex-shrink-0">
            <button
              onClick={() => setLeftCollapsed(false)}
              className="w-6 h-8 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors"
              title="展开导航"
            >
              <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
            </button>
          </div>
        )}

        {/* 可调整大小的面板组 */}
        <div className="flex-1 min-w-0">
          <PanelGroup direction="horizontal">
            {/* 左侧导航面板 */}
            {!leftCollapsed && (
              <>
                <Panel id="left-nav" order={1} defaultSize={20} minSize={15} maxSize={40} className="relative">
                  <NavigationTree onItemClick={handleNavigationClick} />
                  <button
                    onClick={() => setLeftCollapsed(true)}
                    className="absolute top-2 right-2 w-6 h-6 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors z-10"
                    title="折叠导航"
                  >
                    <ChevronLeft className="w-3.5 h-3.5 text-gray-600" />
                  </button>
                </Panel>
                <PanelResizeHandle className="w-1 bg-gray-300 hover:bg-[#3498db] transition-colors" />
              </>
            )}

            {/* 中间工作区 */}
            <Panel id="work-area" order={2} minSize={30}>
              <WorkArea
                tabs={tabs}
                activeTab={activeTab}
                onTabClick={handleTabClick}
                onTabClose={handleTabClose}
                onTabReorder={handleTabReorder}
              />
            </Panel>

            {/* 右侧聊天面板 */}
            {!rightCollapsed && (
              <>
                <PanelResizeHandle className="w-1 bg-gray-300 hover:bg-[#3498db] transition-colors" />
                <Panel id="right-chat" order={3} defaultSize={20} minSize={15} maxSize={40} className="relative">
                  <ChatBot />
                  <button
                    onClick={() => setRightCollapsed(true)}
                    className="absolute top-2 left-2 w-6 h-6 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors z-10"
                    title="折叠助手"
                  >
                    <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
                  </button>
                </Panel>
              </>
            )}
          </PanelGroup>
        </div>

        {/* 右侧聊天折叠按钮 */}
        {rightCollapsed && (
          <div className="w-8 bg-[#f5f6fa] border-l border-gray-300 flex items-start justify-center pt-2 flex-shrink-0">
            <button
              onClick={() => setRightCollapsed(false)}
              className="w-6 h-8 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors"
              title="展开助手"
            >
              <ChevronLeft className="w-3.5 h-3.5 text-gray-600" />
            </button>
          </div>
        )}
      </div>

      <StatusBar />
    </div>
  );
}