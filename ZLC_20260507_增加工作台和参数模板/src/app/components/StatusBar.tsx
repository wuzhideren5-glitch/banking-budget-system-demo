import { useEffect, useRef, useState } from "react";
import { Database, Clock } from "lucide-react";
import { apiGet, type GlobalRefreshStatusDto } from "@/lib/api";

export type StatusBarState = {
  dbConnected: boolean;
  lastGlobalCalcRefreshTime: string | null;
};

function formatDisplayTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace("T", " ");
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function StatusBar({ state }: { state: StatusBarState }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuLoading, setMenuLoading] = useState(false);
  const [menuError, setMenuError] = useState<string>("");
  const [status, setStatus] = useState<GlobalRefreshStatusDto | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const loadStatus = async () => {
    setMenuLoading(true);
    setMenuError("");
    try {
      const row = await apiGet<GlobalRefreshStatusDto>("/api/global-refresh-status");
      setStatus(row);
    } catch (e) {
      setMenuError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setMenuLoading(false);
    }
  };

  useEffect(() => {
    if (!menuOpen) return;
    void loadStatus();
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      const node = menuRef.current;
      if (!node) return;
      if (e.target instanceof Node && !node.contains(e.target)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onDocClick);
    return () => window.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  return (
    <div className="h-7 bg-[#34495e] text-white flex items-center px-3 text-xs border-t border-[#2c3e50]">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Database className="w-3 h-3 text-blue-400" />
          <span className="text-gray-300">数据库: {state.dbConnected ? "已连接" : "未连接"}</span>
        </div>

        <div className="relative flex items-center gap-1.5" ref={menuRef}>
          <Clock className="w-3 h-3 text-gray-400" />
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="text-gray-300 hover:text-white underline underline-offset-2"
          >
            数据库最后全局计算并刷新时间: {formatDisplayTime(state.lastGlobalCalcRefreshTime)}
          </button>
          {menuOpen && (
            <div className="absolute bottom-7 left-0 z-50 min-w-[33rem] max-w-[42rem] rounded border border-gray-200 bg-white p-3 text-[12px] text-gray-800 shadow-lg">
              <div className="mb-2 font-medium text-gray-900">数据库全局刷新最新时间状态</div>
              {menuLoading && <div className="text-gray-500">加载中...</div>}
              {!menuLoading && menuError && <div className="text-red-600">{menuError}</div>}
              {!menuLoading && !menuError && status && (
                <div className="space-y-1">
                  {status.annual_items.map((item) => (
                    <div key={`${item.data_file_name}-${item.year}`} className="flex items-center justify-between gap-3">
                      <span className="text-gray-700">{`${item.data_file_name}（${item.year}）`}</span>
                      <span className="text-gray-900">{formatDisplayTime(item.refresh_time_a)}</span>
                    </div>
                  ))}
                  <div className="mt-2 border-t border-gray-100 pt-2 flex items-center justify-between gap-3">
                    <span className="text-gray-700">Compare 数据库更新时间</span>
                    <span className="text-gray-900">{formatDisplayTime(status.compare_refresh_time_b)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-gray-700">下一次计划更新时间</span>
                    <span className="text-gray-900">{formatDisplayTime(status.next_planned_refresh_time_c)}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
