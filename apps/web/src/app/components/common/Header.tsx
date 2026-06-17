import { useEffect, useMemo, useState } from "react";
import { User, Database } from "lucide-react";

export type HeaderSession = {
  /** 与 localStorage 分用户隔离一致 */
  userId: number;
  softwareVersion: string;
  budgetYear: number;
  versionId: number;
  versionName: string;
  userDisplayName: string;
  userRole: string;
  permissionType: number;
};

export type HeaderVersionSnapshotItem = {
  label: string;
  budgetYear: number;
  versionId: number;
  versionName: string;
  /** 来自版本表的 current_month；无则不在下拉中展示月份段 */
  currentMonth?: number;
};

export function Header({
  session,
  versionSnapshotItems = [],
  onLogout,
}: {
  session: HeaderSession | null;
  versionSnapshotItems?: HeaderVersionSnapshotItem[];
  onLogout?: () => void;
}) {
  const DISPLAY_SOFTWARE_VERSION = "2026_v1.01";
  const s = session;
  const [selectedSnapshotIdx, setSelectedSnapshotIdx] = useState(0);
  useEffect(() => {
    setSelectedSnapshotIdx(0);
  }, [versionSnapshotItems]);
  const effectiveItems = useMemo(() => {
    if (versionSnapshotItems.length > 0) return versionSnapshotItems;
    if (!s) return [] as HeaderVersionSnapshotItem[];
    return [
      {
        label: "可编辑版本",
        budgetYear: s.budgetYear,
        versionId: s.versionId,
        versionName: s.versionName || "—",
        currentMonth: undefined,
      },
    ];
  }, [versionSnapshotItems, s]);
  return (
    <div className="bb-topbar flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <Database className="w-4 h-4" />
        <span className="text-sm font-medium">管衡之家-财务预算智能体</span>
        <span className="text-xs text-gray-300">软件版本: {DISPLAY_SOFTWARE_VERSION}</span>
      </div>

      <div className="flex items-center gap-6 text-xs">
        <select
          className="min-w-[min(100%,32rem)] max-w-[52rem] rounded border border-[#54708c] bg-[#2b4663] px-2 py-0.5 text-[11px] text-white"
          value={Math.min(selectedSnapshotIdx, Math.max(0, effectiveItems.length - 1))}
          onChange={(e) => setSelectedSnapshotIdx(Number(e.target.value))}
        >
          {effectiveItems.map((item, idx) => (
            <option key={`${item.label}-${item.versionId}-${idx}`} value={idx}>
              {`${item.label}｜预算年份:${item.budgetYear}｜版本号:${item.versionId}｜版本名称:${item.versionName}${
                item.currentMonth !== undefined ? `｜当前月份:${item.currentMonth}` : ""
              }`}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <User className="w-3.5 h-3.5" />
          <span className="font-medium">{s?.userDisplayName ?? "—"}</span>
          <span className="text-gray-400">|</span>
          <span className="text-gray-300">{s?.userRole ?? "—"}</span>
        </div>
        {s && onLogout && (
          <button
            type="button"
            onClick={onLogout}
            className="rounded border border-[#90a4b8] px-2 py-0.5 text-[11px] hover:bg-[#2b4663]"
          >
            退出登录
          </button>
        )}
      </div>
    </div>
  );
}
