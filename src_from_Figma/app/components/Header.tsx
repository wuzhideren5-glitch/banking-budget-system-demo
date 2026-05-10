import { User, Database } from "lucide-react";

export function Header() {
  return (
    <div className="h-10 bg-[#2c3e50] text-white flex items-center justify-between px-4 border-b border-[#34495e]">
      <div className="flex items-center gap-3">
        <Database className="w-4 h-4" />
        <span className="text-sm font-medium">管衡之家-财务预算智能体</span>
        <span className="text-xs text-gray-300">软件版本: 2026_v2.13</span>
      </div>

      <div className="flex items-center gap-6 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-gray-300">预算年份:</span>
          <span className="font-medium">2026</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-300">预算版本号:</span>
          <span className="font-medium">12033</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-300">预算版本名称:</span>
          <span className="font-medium">V2024.04.01</span>
        </div>
        <div className="flex items-center gap-2">
          <User className="w-3.5 h-3.5" />
          <span className="font-medium">Arthur</span>
          <span className="text-gray-400">|</span>
          <span className="text-gray-300">预算主管</span>
        </div>
      </div>
    </div>
  );
}
