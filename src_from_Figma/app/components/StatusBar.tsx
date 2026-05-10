import { Wifi, Database, CheckCircle, AlertCircle, Clock, Settings } from "lucide-react";

export function StatusBar() {
  return (
    <div className="h-7 bg-[#34495e] text-white flex items-center justify-between px-3 text-xs border-t border-[#2c3e50]">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <CheckCircle className="w-3 h-3 text-green-400" />
          <span className="text-gray-300">系统就绪</span>
        </div>

        <div className="flex items-center gap-1.5">
          <Database className="w-3 h-3 text-blue-400" />
          <span className="text-gray-300">数据库: 已连接</span>
        </div>

        <div className="flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-gray-400" />
          <span className="text-gray-300">数据库最后全局计算并刷新时间: 2026-04-08 14:32</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <AlertCircle className="w-3 h-3 text-yellow-400" />
          <span className="text-gray-300">3条待处理消息</span>
        </div>

        <div className="flex items-center gap-1.5">
          <Wifi className="w-3 h-3 text-green-400" />
          <span className="text-gray-300">在线</span>
        </div>

        <button className="hover:bg-[#2c3e50] p-1 rounded transition-colors">
          <Settings className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
