import { useEffect, useMemo, useState } from "react";
import { apiGet, type ForecastWorkbenchLineRowDto, type ForecastWorkbenchOverviewDto } from "@/lib/api";

const bindingTypeLabel: Record<string, string> = {
  data_account: "数据科目",
  assumption_parameter: "假设参数",
  assumption_rule_template: "预测模板",
  rule_template: "预测模板",
  report_account: "报表科目",
};

export function ForecastWorkbenchContent() {
  const [overview, setOverview] = useState<ForecastWorkbenchOverviewDto | null>(null);
  const [selectedGroup, setSelectedGroup] = useState("全部");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiGet<ForecastWorkbenchOverviewDto>("/api/forecast-workbench/overview");
      setOverview(result);
      const groups = Array.from(new Set(result.lines.map((line) => line.line_group)));
      if (selectedGroup !== "全部" && !groups.includes(selectedGroup)) {
        setSelectedGroup("全部");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载预测预算工作台失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = useMemo(() => {
    const values = overview ? Array.from(new Set(overview.lines.map((line) => line.line_group))) : [];
    return ["全部", ...values];
  }, [overview]);

  const visibleLines = useMemo(() => {
    if (!overview) return [];
    if (selectedGroup === "全部") return overview.lines;
    return overview.lines.filter((line) => line.line_group === selectedGroup);
  }, [overview, selectedGroup]);

  const selectedLine = visibleLines[0] ?? null;

  const renderBindingBadges = (line: ForecastWorkbenchLineRowDto) => {
    if (!line.bindings.length) {
      return <span className="text-[11px] text-amber-700">待补绑定</span>;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {line.bindings.map((binding) => (
          <span
            key={binding.id}
            className="inline-flex items-center rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] text-blue-700"
          >
            {(bindingTypeLabel[binding.binding_type] || binding.binding_type) + " / " + (binding.binding_name || binding.binding_code)}
          </span>
        ))}
      </div>
    );
  };

  if (loading) {
    return <div className="p-4 text-sm text-gray-600">正在加载预测预算工作台...</div>;
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      </div>
    );
  }

  if (!overview) {
    return <div className="p-4 text-sm text-gray-600">暂无预测预算工作台数据。</div>;
  }

  return (
    <div className="h-full overflow-auto bg-gray-50">
      <div className="space-y-4 p-4">
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-800">预测预算工作台</h2>
              <p className="mt-1 text-xs text-gray-600">
                年度 {overview.budget_year} | 版本 {overview.version_name} | 预测起始月 {overview.current_month} 月
              </p>
            </div>
            <button
              onClick={() => void refresh()}
              className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
            >
              刷新概览
            </button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">工作台行数</div>
              <div className="mt-1 text-lg font-semibold text-gray-800">{overview.summary.layout_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">绑定总数</div>
              <div className="mt-1 text-lg font-semibold text-gray-800">{overview.summary.binding_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">已绑定行</div>
              <div className="mt-1 text-lg font-semibold text-emerald-700">{overview.summary.bound_line_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">待补齐行</div>
              <div className="mt-1 text-lg font-semibold text-amber-700">{overview.summary.unbound_line_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">数据科目</div>
              <div className="mt-1 text-lg font-semibold text-gray-800">{overview.summary.data_account_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">假设参数</div>
              <div className="mt-1 text-lg font-semibold text-gray-800">{overview.summary.parameter_count}</div>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-[11px] text-gray-500">预测模板</div>
              <div className="mt-1 text-lg font-semibold text-gray-800">{overview.summary.template_count}</div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-200 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                {groups.map((group) => (
                  <button
                    key={group}
                    onClick={() => setSelectedGroup(group)}
                    className={`rounded px-2.5 py-1 text-xs ${
                      selectedGroup === group ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                  >
                    {group}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-gray-50 text-left text-gray-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">预测行</th>
                    <th className="px-3 py-2 font-medium">分类</th>
                    <th className="px-3 py-2 font-medium">绑定概览</th>
                    <th className="px-3 py-2 font-medium">提示</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleLines.map((line) => (
                    <tr key={line.line_code} className="border-t border-gray-100 align-top">
                      <td className="px-3 py-2">
                        <div className="font-medium text-gray-800">{line.line_name}</div>
                        <div className="mt-1 text-[11px] text-gray-500">{line.line_code}</div>
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        <div>{line.line_group}</div>
                        <div className="mt-1 text-[11px] text-gray-500">{line.line_category}</div>
                      </td>
                      <td className="px-3 py-2">{renderBindingBadges(line)}</td>
                      <td className="px-3 py-2 text-gray-600">{line.binding_hint || line.remark || "-"}</td>
                    </tr>
                  ))}
                  {visibleLines.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-3 py-6 text-center text-gray-500">
                        当前分组暂无预测行。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-800">当前骨架说明</h3>
            <div className="mt-3 space-y-3 text-xs leading-6 text-gray-600">
              <p>该页面按“开鑫贷 / 小小账户”模板主线预置预测行，先聚焦展示每条预测行绑定的数据科目、参数和模板。</p>
              <p>当前优先覆盖利息净收入、净手续费收入、风险成本、平台费率、渠道费、保险代偿等关键预测主线。</p>
              <p>后续可继续补产品/部门切换、月度预测表、公式/模板编辑面板，并把手工锚点逐步替换成真实数据科目或假设参数。</p>
            </div>

            <div className="mt-4 rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-xs font-medium text-gray-700">示例选中行</div>
              {selectedLine ? (
                <div className="mt-2 space-y-2 text-xs text-gray-600">
                  <div>
                    <span className="font-medium text-gray-800">{selectedLine.line_name}</span>
                    <span className="ml-2 text-gray-500">{selectedLine.line_code}</span>
                  </div>
                  <div>绑定数量：{selectedLine.binding_count}</div>
                  <div>绑定角色：{selectedLine.bindings.map((item) => item.binding_role || "未标注").join(" / ") || "暂无"}</div>
                  <div>维护提示：{selectedLine.binding_hint || selectedLine.remark || "-"}</div>
                </div>
              ) : (
                <div className="mt-2 text-xs text-gray-500">暂无可展示的预测行。</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
