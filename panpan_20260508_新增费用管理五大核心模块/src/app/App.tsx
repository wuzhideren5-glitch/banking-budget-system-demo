import { useEffect, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import { Header, type HeaderSession, type HeaderVersionSnapshotItem } from "./components/Header";
import { NavigationTree } from "./components/NavigationTree";
import { ChatBot } from "./components/ChatBot";
import { WorkArea, Tab } from "./components/WorkArea";
import { StatusBar, type StatusBarState } from "./components/StatusBar";
import { ChevronLeft, ChevronRight, ChevronsLeft, Eye, EyeOff } from "lucide-react";
import {
  apiGet,
  apiPost,
  type AgentPivotSuggestionDto,
  type LoginResponseDto,
  type SessionInfo,
  type VersionSnapshotResponseDto,
} from "@/lib/api";
import { UserStorageProvider } from "@/app/UserStorageContext";

const CHAT_EXPAND_SIZE_NORMAL = 20;
const CHAT_EXPAND_SIZE_DOUBLE = CHAT_EXPAND_SIZE_NORMAL * 2;
const CHAT_MAX_SIZE = 40;
const PIVOT_COMPARE_SETTINGS_STORAGE_KEY_BASE = "budget_pivot_compare_settings_v1";
const CHAT_BUNDLE_KEY_BASE = "budget_agent_chat_bundle_v2";
const PIVOT_APPLY_COMPARE_EVENT = "budget-agent-apply-pivot-suggestion-compare";

function pivotCompareSettingsStorageKey(userId: number): string {
  return `${PIVOT_COMPARE_SETTINGS_STORAGE_KEY_BASE}__u${userId}`;
}

function chatBundleKeyForUser(userId: number): string {
  return `${CHAT_BUNDLE_KEY_BASE}__u${userId}`;
}

export default function App() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [pendingRightExpandSize, setPendingRightExpandSize] = useState<number | null>(null);
  const [rightPanelSize, setRightPanelSize] = useState(CHAT_EXPAND_SIZE_NORMAL);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTab, setActiveTab] = useState<string>("");
  const leftNavPanelRef = useRef<ImperativePanelHandle | null>(null);
  const rightChatPanelRef = useRef<ImperativePanelHandle | null>(null);
  const [headerSession, setHeaderSession] = useState<HeaderSession | null>(null);
  const [versionSnapshotItems, setVersionSnapshotItems] = useState<HeaderVersionSnapshotItem[]>([]);
  const [permissionType, setPermissionType] = useState<number>(3);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string>("");
  const [needChangePassword, setNeedChangePassword] = useState(false);
  const [loginUserName, setLoginUserName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [submittingAuth, setSubmittingAuth] = useState(false);
  const [statusBar, setStatusBar] = useState<StatusBarState>({
    dbConnected: false,
    lastGlobalCalcRefreshTime: null,
  });

  const loadSession = async (): Promise<boolean> => {
    try {
      const s = await apiGet<SessionInfo>("/api/session");
      setHeaderSession({
        userId: s.user_id,
        softwareVersion: s.software_version,
        budgetYear: s.budget_year,
        versionId: s.version_id,
        versionName: s.version_name,
        userDisplayName: s.user_display_name,
        userRole: s.user_role,
        permissionType: s.permission_type,
      });
      setPermissionType(s.permission_type);
      setNeedChangePassword(s.first_login_required);
      setStatusBar({
        dbConnected: s.db_connected,
        lastGlobalCalcRefreshTime: s.last_global_calc_refresh_time,
      });
      try {
        const snapshot = await apiGet<VersionSnapshotResponseDto>("/api/version-snapshot");
        setVersionSnapshotItems(
          (snapshot.items ?? []).map((item) => ({
            label: item.label,
            budgetYear: item.budget_year,
            versionId: item.version_id,
            versionName: item.version_name,
            currentMonth: item.current_month,
          })),
        );
      } catch {
        setVersionSnapshotItems([]);
      }
      setAuthError("");
      return true;
    } catch {
      setHeaderSession(null);
      setVersionSnapshotItems([]);
      setPermissionType(3);
      setNeedChangePassword(false);
      setStatusBar({ dbConnected: false, lastGlobalCalcRefreshTime: null });
      return false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await loadSession();
      if (!cancelled && !ok) {
        setAuthError("");
      }
      if (!cancelled) setAuthLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handler = () => {
      void loadSession();
    };
    window.addEventListener("budget-version-snapshot-changed", handler);
    return () => window.removeEventListener("budget-version-snapshot-changed", handler);
  }, []);

  useEffect(() => {
    const panel = rightChatPanelRef.current;
    if (!panel || rightCollapsed) return;
    panel.expand();
    if (pendingRightExpandSize === null) return;
    let frameId = 0;
    const applyResize = () => {
      panel.resize(pendingRightExpandSize);
      setPendingRightExpandSize(null);
    };
    frameId = window.requestAnimationFrame(applyResize);
    return () => {
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, [rightCollapsed, pendingRightExpandSize]);

  useEffect(() => {
    const panel = rightChatPanelRef.current;
    if (!panel) return;
    if (rightCollapsed) {
      panel.collapse();
    } else {
      panel.expand();
    }
  }, [rightCollapsed]);

  /** 左侧导航始终保留在 PanelGroup 内（collapsible），避免条件卸载面板导致布局/命中区域错乱、右侧助手无法收起 */
  useEffect(() => {
    const panel = leftNavPanelRef.current;
    if (!panel) return;
    if (leftCollapsed) {
      panel.collapse();
    } else {
      panel.expand();
    }
  }, [leftCollapsed]);

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

  const expandAssistant = (size: number) => {
    setRightCollapsed(false);
    setPendingRightExpandSize(size);
  };

  const openPivotTableWithSuggestion = (suggestion?: AgentPivotSuggestionDto | null) => {
    if (suggestion) {
      try {
        const pivotKey = pivotCompareSettingsStorageKey(headerSession!.userId);
        localStorage.setItem(
          pivotKey,
          JSON.stringify({
            rowFieldIds: suggestion.row_field_ids ?? [],
            columnFieldIds: suggestion.column_field_ids ?? [],
            pageFieldIds: suggestion.page_field_ids ?? [],
            valueFieldIds: suggestion.value_field_ids?.length ? suggestion.value_field_ids : ["value"],
            pageFieldSelections: suggestion.page_selections ?? {},
            pivotSearchText: suggestion.pivot_search_text ?? "",
            showRowTotal: true,
            showColumnTotal: true,
          }),
        );
      } catch {
        // ignore localStorage quota errors
      }
      window.dispatchEvent(
        new CustomEvent(PIVOT_APPLY_COMPARE_EVENT, {
          detail: suggestion,
        }),
      );
    }
    handleNavigationClick("analysis-pivot-table-compare", "数据透视表-多年度对比透视");
  };

  const rightPanelAtMax = !rightCollapsed && rightPanelSize >= CHAT_MAX_SIZE - 0.01;

  const handleLogin = async () => {
    setSubmittingAuth(true);
    setAuthError("");
    try {
      const res = await apiPost<LoginResponseDto>("/api/login", {
        user_name: loginUserName,
        password: loginPassword,
      });
      if (res.need_change_password) {
        setNeedChangePassword(true);
      }
      const ok = await loadSession();
      if (!ok) {
        setAuthError("登录后读取会话失败，请重试");
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmittingAuth(false);
    }
  };

  const handleFirstPasswordChange = async () => {
    setSubmittingAuth(true);
    setAuthError("");
    try {
      await apiPost("/api/change-password-first-login", {
        new_password: newPassword,
      });
      setNeedChangePassword(false);
      setNewPassword("");
      await loadSession();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "改密失败");
    } finally {
      setSubmittingAuth(false);
    }
  };

  const handleLogout = async () => {
    try {
      await apiPost("/api/logout", {});
    } catch {
      // ignore
    }
    setTabs([]);
    setActiveTab("");
    setHeaderSession(null);
    setNeedChangePassword(false);
    setLoginPassword("");
    setShowLoginPassword(false);
    setShowNewPassword(false);
  };

  if (authLoading) {
    return <div className="size-full flex items-center justify-center text-sm text-gray-600">正在检查登录状态...</div>;
  }

  if (!headerSession) {
    return (
      <div className="size-full flex items-center justify-center bg-[#ecf0f1]">
        <div className="w-[360px] bg-white border border-gray-300 rounded p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-800 mb-4">预算系统登录</h2>
          <div className="space-y-3">
            <input
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
              placeholder="用户名"
              value={loginUserName}
              onChange={(e) => setLoginUserName(e.target.value)}
            />
            <div className="relative">
              <input
                className="w-full border border-gray-300 rounded px-2 py-1.5 pr-9 text-sm"
                placeholder="密码"
                type={showLoginPassword ? "text" : "password"}
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowLoginPassword((prev) => !prev)}
                className="absolute inset-y-0 right-0 px-2.5 flex items-center text-gray-500 hover:text-gray-700"
                title={showLoginPassword ? "隐藏密码" : "显示密码"}
                aria-label={showLoginPassword ? "隐藏密码" : "显示密码"}
              >
                {showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <div className="text-[11px] text-gray-500 space-y-1">
              <p>1）用户名区分大小写，请按管理员分配的原始用户名输入。</p>
              <p>2）密码不少于8位，至少包含1个字母，且区分大小写。</p>
            </div>
            {authError && <div className="text-xs text-red-600">{authError}</div>}
            <button
              className="w-full bg-[#2c3e50] text-white rounded py-1.5 text-sm disabled:opacity-60"
              onClick={() => void handleLogin()}
              disabled={submittingAuth}
            >
              {submittingAuth ? "登录中..." : "登录"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (needChangePassword) {
    return (
      <div className="size-full flex items-center justify-center bg-[#ecf0f1]">
        <div className="w-[420px] bg-white border border-gray-300 rounded p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-800 mb-2">首次登录请修改密码</h2>
          <p className="text-xs text-gray-500 mb-3">密码规则：至少8位，至少包含1个字母，且区分大小写。</p>
          <div className="relative">
            <input
              className="w-full border border-gray-300 rounded px-2 py-1.5 pr-9 text-sm"
              placeholder="新密码"
              type={showNewPassword ? "text" : "password"}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowNewPassword((prev) => !prev)}
              className="absolute inset-y-0 right-0 px-2.5 flex items-center text-gray-500 hover:text-gray-700"
              title={showNewPassword ? "隐藏密码" : "显示密码"}
              aria-label={showNewPassword ? "隐藏密码" : "显示密码"}
            >
              {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {authError && <div className="text-xs text-red-600 mt-2">{authError}</div>}
          <button
            className="w-full bg-[#2c3e50] text-white rounded py-1.5 text-sm mt-3 disabled:opacity-60"
            onClick={() => void handleFirstPasswordChange()}
            disabled={submittingAuth}
          >
            {submittingAuth ? "提交中..." : "提交新密码"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <UserStorageProvider userId={headerSession.userId}>
    <div className="size-full flex flex-col bg-[#ecf0f1]">
      <Header
        session={headerSession}
        versionSnapshotItems={versionSnapshotItems}
        onLogout={() => void handleLogout()}
      />

      <div className="flex-1 overflow-hidden flex">
        {/* 左侧导航折叠按钮 */}
        {leftCollapsed && (
          <div className="w-8 bg-[#f5f6fa] border-r border-gray-300 flex items-start justify-center pt-2 flex-shrink-0 z-[1]">
            <button
              type="button"
              onClick={() => setLeftCollapsed(false)}
              className="w-6 h-8 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors"
              title="展开导航"
            >
              <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
            </button>
          </div>
        )}

        {/* 可调整大小的面板组 */}
        <div className="flex-1 min-w-0 min-h-0">
          <PanelGroup direction="horizontal">
            {/* 左侧导航面板：不条件卸载，仅用 collapse/expand，与右侧助手一致，保证面板组结构稳定 */}
            <Panel
              ref={leftNavPanelRef}
              id="left-nav"
              order={1}
              defaultSize={20}
              minSize={15}
              maxSize={40}
              collapsible
              collapsedSize={0}
              className="relative min-w-0"
            >
              <NavigationTree onItemClick={handleNavigationClick} permissionType={permissionType} />
              <button
                type="button"
                onClick={() => setLeftCollapsed(true)}
                className="absolute top-2 right-2 w-6 h-6 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors z-10"
                title="折叠导航"
              >
                <ChevronLeft className="w-3.5 h-3.5 text-gray-600" />
              </button>
            </Panel>
            <PanelResizeHandle
              className={
                leftCollapsed
                  ? "w-0 pointer-events-none"
                  : "w-1 bg-gray-300 hover:bg-[#3498db] transition-colors"
              }
            />

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
            <PanelResizeHandle
              className={`transition-colors ${
                rightCollapsed
                  ? "w-0 pointer-events-none"
                  : "w-1 bg-gray-300 hover:bg-[#3498db]"
              }`}
            />
            <Panel
              ref={rightChatPanelRef}
              id="right-chat"
              order={3}
              defaultSize={20}
              minSize={15}
              maxSize={CHAT_MAX_SIZE}
              collapsible
              collapsedSize={0}
              onResize={setRightPanelSize}
              className={`relative ${rightCollapsed ? "overflow-hidden" : ""}`}
            >
              <ChatBot
                key={headerSession.userId}
                chatBundleStorageKey={chatBundleKeyForUser(headerSession.userId)}
                userDisplayName={headerSession.userDisplayName}
                onOpenPivotTable={openPivotTableWithSuggestion}
                onExpandAssistantDouble={() => {
                  if (rightPanelAtMax) return;
                  expandAssistant(CHAT_EXPAND_SIZE_DOUBLE);
                }}
                onCollapseAssistant={() => setRightCollapsed(true)}
                disableExpandAssistantDouble={rightPanelAtMax}
              />
            </Panel>
          </PanelGroup>
        </div>

        {/* 右侧聊天折叠按钮 */}
        {rightCollapsed && (
          <div className="w-8 bg-[#f5f6fa] border-l border-gray-300 flex flex-col items-center pt-2 gap-1.5 flex-shrink-0 z-[1]">
            <button
              type="button"
              onClick={() => expandAssistant(CHAT_EXPAND_SIZE_NORMAL)}
              className="w-6 h-8 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors"
              title="展开助手"
            >
              <ChevronLeft className="w-3.5 h-3.5 text-gray-600" />
            </button>
            <button
              type="button"
              onClick={() => expandAssistant(CHAT_EXPAND_SIZE_DOUBLE)}
              className="w-6 h-8 bg-gray-200 hover:bg-gray-300 border border-gray-300 rounded flex items-center justify-center shadow-sm transition-colors"
              title="双倍展开助手"
            >
              <ChevronsLeft className="w-3.5 h-3.5 text-gray-600" />
            </button>
          </div>
        )}
      </div>

      <StatusBar state={statusBar} />
    </div>
    </UserStorageProvider>
  );
}