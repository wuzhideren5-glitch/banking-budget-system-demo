import { useState, useRef, useEffect } from "react";
import { Search, Plus, Edit, Trash2, Save, ArrowUpDown, ArrowUp, ArrowDown, Calculator, ChevronRight, ChevronDown, Minimize2, Maximize2, ChevronsDown, ChevronsUp, Maximize, FileText, Database as DatabaseIcon, Upload, RefreshCw, Building2, GripVertical, X } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

export function AnalysisReportContent() {
  const [searchText, setSearchText] = useState("");
  const [reports] = useState([
    { id: "RPT001", name: "2026年第一季度资产负债分析", type: "资产负债分析", remark: "季度常规报告" },
    { id: "RPT002", name: "各部门预算执行情况对比", type: "预算执行分析", remark: "包含零售、公司、金融市场部" },
    { id: "RPT003", name: "产品收益率趋势分析", type: "收益率分析", remark: "重点关注理财产品" },
    { id: "RPT004", name: "存贷款余额月度分析", type: "存贷分析", remark: "" },
    { id: "RPT005", name: "风险资产质量评估报告", type: "风险分析", remark: "需提交监管部门" },
    { id: "RPT006", name: "部门成本费用分析", type: "成本分析", remark: "用于绩效考核" },
  ]);

  const filteredReports = reports.filter(report =>
    report.name.toLowerCase().includes(searchText.toLowerCase()) ||
    report.id.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-800">智能分析报告</h3>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索报告标题"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-64"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto border border-gray-300 rounded">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-gray-100 sticky top-0">
            <tr>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告编号</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告名称</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告类型</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">备注</th>
            </tr>
          </thead>
          <tbody>
            {filteredReports.map((report) => (
              <tr key={report.id} className="hover:bg-blue-50">
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.id}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.name}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.type}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-500">{report.remark}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// 智能演示PPT内容
