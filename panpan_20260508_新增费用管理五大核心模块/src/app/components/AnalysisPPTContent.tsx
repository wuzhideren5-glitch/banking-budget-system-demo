import { useState, useRef, useEffect } from "react";
import { Search, Plus, Edit, Trash2, Save, ArrowUpDown, ArrowUp, ArrowDown, Calculator, ChevronRight, ChevronDown, Minimize2, Maximize2, ChevronsDown, ChevronsUp, Maximize, FileText, Database as DatabaseIcon, Upload, RefreshCw, Building2, GripVertical, X } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

export function AnalysisPPTContent() {
  const [searchText, setSearchText] = useState("");
  const [presentations] = useState([
    { id: "PPT001", name: "2026年Q1董事会汇报PPT", type: "董事会汇报", remark: "包含财务、业务、风险三部分" },
    { id: "PPT002", name: "零售银行部年度工作总结", type: "部门总结", remark: "重点展示个贷业绩" },
    { id: "PPT003", name: "产品收益率对比演示", type: "产品分析", remark: "竞品对比分析" },
    { id: "PPT004", name: "预算执行情况月度汇报", type: "预算汇报", remark: "高管月度会议使用" },
    { id: "PPT005", name: "风险管理委员会季度报告", type: "风控汇报", remark: "" },
    { id: "PPT006", name: "数字化转型进展汇报", type: "项目汇报", remark: "IT部门协同准备" },
  ]);

  const filteredPresentations = presentations.filter(ppt =>
    ppt.name.toLowerCase().includes(searchText.toLowerCase()) ||
    ppt.id.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-800">智能演示PPT</h3>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索PPT标题"
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
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示编号</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示PPT名称</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示类型</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">备注</th>
            </tr>
          </thead>
          <tbody>
            {filteredPresentations.map((ppt) => (
              <tr key={ppt.id} className="hover:bg-blue-50">
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.id}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.name}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.type}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-500">{ppt.remark}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
