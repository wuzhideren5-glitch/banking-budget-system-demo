import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";

import type {
  BusinessCostIncomeIndicatorDto,
  BusinessCostIncomeItemDto,
} from "@/lib/business/businessCostIncomeApi";
import {
  BUSINESS_COST_INCOME_FORMAT_LABELS,
  BUSINESS_COST_INCOME_SECTION_LABELS,
} from "@/lib/business/businessCostIncomeAdminViewModel";

type Props = {
  indicators: BusinessCostIncomeIndicatorDto[];
  items: BusinessCostIncomeItemDto[];
  submitting: boolean;
  onAdd: () => void;
  onMove: (index: number, direction: "up" | "down") => void;
  onToggle: (indicator: BusinessCostIncomeIndicatorDto) => void;
  onDelete: (id: number) => void;
};

export function BusinessCostIncomeIndicatorTable({
  indicators,
  items,
  submitting,
  onAdd,
  onMove,
  onToggle,
  onDelete,
}: Props) {
  return (
    <section className="rounded border border-gray-200 bg-white">
      <div className="px-4 py-2.5 border-b border-gray-200 bg-slate-50 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-slate-700">评估指标</span>
          <span className="text-gray-400">({indicators.length}项)</span>
        </div>
        <button
          type="button"
          onClick={onAdd}
          className="px-2 py-0.5 bg-blue-500 text-white rounded hover:bg-blue-600 inline-flex items-center gap-1"
        >
          <Plus className="w-3.5 h-3.5" />
          添加
        </button>
      </div>
      <div className="overflow-auto">
        <table className="w-full border-collapse text-xs whitespace-nowrap">
          <thead className="bg-gray-100">
            <tr className="text-left text-gray-700">
              <th className="border border-gray-200 px-2 py-2 w-[40px]">ID</th>
              <th className="border border-gray-200 px-2 py-2">名称</th>
              <th className="border border-gray-200 px-2 py-2">分子</th>
              <th className="border border-gray-200 px-2 py-2">分母</th>
              <th className="border border-gray-200 px-2 py-2 w-[80px]">格式</th>
              <th className="border border-gray-200 px-2 py-2 w-[80px]">排序</th>
              <th className="border border-gray-200 px-2 py-2 w-[60px]">启用</th>
              <th className="border border-gray-200 px-2 py-2 w-[60px]">操作</th>
            </tr>
          </thead>
          <tbody>
            {indicators.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-2 py-6 text-center text-gray-500">
                  暂无指标，点击右上角"+ 添加"新增
                </td>
              </tr>
            ) : (
              indicators.map((indicator, index) => {
                const numeratorItem = items.find(
                  (item) =>
                    item.section === indicator.numerator_section &&
                    item.id === indicator.numerator_item_id
                );
                const denominatorItem = items.find(
                  (item) =>
                    item.section === indicator.denominator_section &&
                    item.id === indicator.denominator_item_id
                );
                return (
                  <tr key={indicator.id} className="hover:bg-gray-50">
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-500">
                      {indicator.id}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5 font-medium text-gray-800">
                      {indicator.name}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                      {BUSINESS_COST_INCOME_SECTION_LABELS[indicator.numerator_section]}:{" "}
                      {numeratorItem?.name ?? `#${indicator.numerator_item_id}`}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                      {BUSINESS_COST_INCOME_SECTION_LABELS[indicator.denominator_section]}:{" "}
                      {denominatorItem?.name ?? `#${indicator.denominator_item_id}`}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                      {BUSINESS_COST_INCOME_FORMAT_LABELS[indicator.format]}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-700">{indicator.sort_order}</span>
                        <button
                          type="button"
                          onClick={() => onMove(index, "up")}
                          disabled={index === 0 || submitting}
                          className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                          title="上移"
                        >
                          <ChevronUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onMove(index, "down")}
                          disabled={index === indicators.length - 1 || submitting}
                          className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                          title="下移"
                        >
                          <ChevronDown className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => onToggle(indicator)}
                        disabled={submitting}
                        className={`px-2 py-0.5 rounded text-xs ${
                          indicator.enabled
                            ? "bg-green-100 text-green-700 hover:bg-green-200"
                            : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                        }`}
                      >
                        {indicator.enabled ? "启用" : "停用"}
                      </button>
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => onDelete(indicator.id)}
                        disabled={submitting}
                        className="px-1.5 py-0.5 rounded text-xs bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1 disabled:opacity-50"
                      >
                        <Trash2 className="w-3 h-3" />
                        删除
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
