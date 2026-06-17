import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  Database,
  FileSpreadsheet,
  Filter,
  Layers3,
  Link2,
  Plus,
  Save,
  Search,
  SlidersHorizontal,
  Table2,
  Wand2,
  X,
} from "lucide-react";

// PROTOTYPE: Three variants of the product budget workbench, switchable via ?variant=, mounted as a new budget-management tab.

type Product = {
  code: string;
  name: string;
  owner: string;
  status: "ready" | "draft" | "warning";
};

type ComponentLine = {
  id: string;
  name: string;
  template: string;
  dataAccount: string;
  status: "ready" | "draft" | "warning";
  formula: string;
  jan: number;
  feb: number;
  mar: number;
  annual: number;
};

type BudgetRow = {
  id: string;
  reportCode: string;
  name: string;
  status: "ready" | "draft" | "warning";
  jan: number;
  feb: number;
  mar: number;
  annual: number;
  components: ComponentLine[];
};

type VariantKey = "A" | "B" | "C";

const products: Product[] = [
  { code: "Z0101", name: "开鑫贷", owner: "潘婷", status: "warning" },
  { code: "Z0102", name: "小小账户", owner: "潘婷", status: "draft" },
  { code: "Z0201", name: "联合贷", owner: "陈凯", status: "ready" },
  { code: "Z0301", name: "消费分期", owner: "陈凯", status: "ready" },
];

const rows: BudgetRow[] = [
  {
    id: "interest",
    reportCode: "A0101",
    name: "利息净收入",
    status: "warning",
    jan: 1280,
    feb: 1365,
    mar: 1420,
    annual: 17180,
    components: [
      {
        id: "self-interest",
        name: "自营利息收入",
        template: "贷款利息收入模板",
        dataAccount: "A1208 自持日均余额",
        status: "ready",
        formula: "A1208 * P(CUSTOMER_RATE) * DAYS / 360",
        jan: 820,
        feb: 860,
        mar: 905,
        annual: 10640,
      },
      {
        id: "joint-service",
        name: "联贷服务费收入",
        template: "平台服务费模板",
        dataAccount: "A1417 联贷日均余额",
        status: "draft",
        formula: "A1417 * P(KX_PLATFORM_FEE_RATE)",
        jan: 460,
        feb: 505,
        mar: 515,
        annual: 6540,
      },
    ],
  },
  {
    id: "fee",
    reportCode: "A0201",
    name: "净手续费收入",
    status: "draft",
    jan: 210,
    feb: 198,
    mar: 236,
    annual: 2860,
    components: [
      {
        id: "channel-fee",
        name: "渠道费支出",
        template: "比例分摊模板",
        dataAccount: "A1520 渠道费",
        status: "draft",
        formula: "A1417 * P(CONTRACT_CHANNEL_FEE_RATIO)",
        jan: -110,
        feb: -118,
        mar: -126,
        annual: -1480,
      },
    ],
  },
  {
    id: "risk",
    reportCode: "A0301",
    name: "风险成本",
    status: "warning",
    jan: -360,
    feb: -380,
    mar: -412,
    annual: -5020,
    components: [
      {
        id: "risk-cost",
        name: "逾期风险成本",
        template: "风险成本测算模板",
        dataAccount: "A1712 逾期90+余额",
        status: "warning",
        formula: "A1712 * P(OVERDUE_90_RATIO) - P(KX_INSURANCE_NET_COMP)",
        jan: -360,
        feb: -380,
        mar: -412,
        annual: -5020,
      },
    ],
  },
  {
    id: "profit",
    reportCode: "A0501",
    name: "预算利润",
    status: "ready",
    jan: 910,
    feb: 960,
    mar: 1012,
    annual: 12030,
    components: [],
  },
];

const statusMeta = {
  ready: { label: "已下发", cls: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  draft: { label: "草稿", cls: "border-sky-200 bg-sky-50 text-sky-700", icon: Save },
  warning: { label: "待补齐", cls: "border-amber-200 bg-amber-50 text-amber-700", icon: AlertTriangle },
};

function formatAmount(value: number) {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function StatusPill({ status }: { status: Product["status"] }) {
  const meta = statusMeta[status];
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${meta.cls}`}>
      <Icon className="h-3 w-3" />
      {meta.label}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function TextInput({ value, muted = false }: { value: string; muted?: boolean }) {
  return (
    <div className={`h-8 rounded border px-2 py-1.5 text-xs ${muted ? "border-slate-200 bg-slate-50 text-slate-500" : "border-slate-300 bg-white text-slate-700"}`}>
      {value}
    </div>
  );
}

function ActionButton({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "primary" | "danger";
}) {
  const cls =
    tone === "primary"
      ? "border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
      : tone === "danger"
        ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50";
  return <button className={`inline-flex h-8 items-center gap-1.5 rounded border px-2.5 text-xs ${cls}`}>{children}</button>;
}

function ProductRail({
  selectedCode,
  onSelect,
  compact = false,
}: {
  selectedCode: string;
  onSelect: (code: string) => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "space-y-1" : "h-full border-r border-slate-200 bg-slate-50"}>
      {!compact && (
        <div className="border-b border-slate-200 px-3 py-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold text-slate-800">我的负责产品</div>
            <ActionButton>
              <Plus className="h-3.5 w-3.5" />
              选择
            </ActionButton>
          </div>
          <div className="mt-2 flex h-8 items-center gap-2 rounded border border-slate-200 bg-white px-2 text-xs text-slate-400">
            <Search className="h-3.5 w-3.5" />
            搜索产品
          </div>
        </div>
      )}
      <div className={compact ? "space-y-1" : "space-y-1 p-2"}>
        {products.map((product) => (
          <button
            key={product.code}
            onClick={() => onSelect(product.code)}
            className={`w-full rounded border px-2.5 py-2 text-left transition ${
              selectedCode === product.code
                ? "border-blue-300 bg-white shadow-sm"
                : "border-transparent bg-transparent hover:border-slate-200 hover:bg-white"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-slate-800">{product.name}</div>
                <div className="mt-0.5 font-mono text-[11px] text-slate-400">{product.code}</div>
              </div>
              <StatusPill status={product.status} />
            </div>
            {!compact && <div className="mt-1 text-[11px] text-slate-500">负责人：{product.owner}</div>}
          </button>
        ))}
      </div>
    </div>
  );
}

function WorkbenchHeader({ product }: { product: Product }) {
  return (
    <div className="border-b border-slate-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-slate-900">{product.name} 产品预算工作台</h2>
            <StatusPill status={product.status} />
          </div>
          <div className="mt-1 text-xs text-slate-500">2026 年 | V2 滚动预测 | 预测起始月 5 月 | 产品范围 {product.code}</div>
        </div>
        <div className="flex items-center gap-2">
          <ActionButton>
            <Filter className="h-3.5 w-3.5" />
            口径
          </ActionButton>
          <ActionButton>
            <Copy className="h-3.5 w-3.5" />
            套用模板
          </ActionButton>
          <ActionButton tone="primary">
            <Wand2 className="h-3.5 w-3.5" />
            下发并试算
          </ActionButton>
        </div>
      </div>
    </div>
  );
}

function TrialTable({
  selectedRow,
  selectedComponent,
  onSelectRow,
  onSelectComponent,
  dense = false,
}: {
  selectedRow: string;
  selectedComponent: string;
  onSelectRow: (id: string) => void;
  onSelectComponent: (id: string) => void;
  dense?: boolean;
}) {
  return (
    <div className="overflow-auto">
      <table className="min-w-[940px] w-full border-separate border-spacing-0 text-xs">
        <thead className="sticky top-0 z-10 bg-slate-100 text-slate-600">
          <tr>
            <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">报告科目 / 组件</th>
            <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">状态</th>
            <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">模板/底层数据科目</th>
            <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">1月</th>
            <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">2月</th>
            <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">3月</th>
            <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">全年</th>
            <th className="border-b border-slate-200 px-2 py-2 text-center font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <>
              <tr
                key={row.id}
                onClick={() => onSelectRow(row.id)}
                className={`cursor-pointer ${selectedRow === row.id ? "bg-blue-50" : "bg-white hover:bg-slate-50"}`}
              >
                <td className="border-b border-slate-100 px-2 py-2">
                  <div className="flex items-center gap-1.5">
                    {row.components.length ? <ChevronDown className="h-3.5 w-3.5 text-slate-400" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-300" />}
                    <span className="font-mono text-[11px] text-slate-400">{row.reportCode}</span>
                    <span className="font-medium text-slate-800">{row.name}</span>
                  </div>
                </td>
                <td className="border-b border-slate-100 px-2 py-2">
                  <StatusPill status={row.status} />
                </td>
                <td className="border-b border-slate-100 px-2 py-2 text-slate-500">{row.components.length} 个计算组件</td>
                <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-700">{formatAmount(row.jan)}</td>
                <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-700">{formatAmount(row.feb)}</td>
                <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-700">{formatAmount(row.mar)}</td>
                <td className="border-b border-slate-100 px-2 py-2 text-right font-semibold text-slate-900">{formatAmount(row.annual)}</td>
                <td className="border-b border-slate-100 px-2 py-2 text-center">
                  <button className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-white">新增组件</button>
                </td>
              </tr>
              {row.components.map((component) => (
                <tr
                  key={component.id}
                  onClick={() => {
                    onSelectRow(row.id);
                    onSelectComponent(component.id);
                  }}
                  className={`cursor-pointer ${selectedComponent === component.id ? "bg-sky-50" : "bg-white hover:bg-slate-50"}`}
                >
                  <td className={`border-b border-slate-100 px-2 ${dense ? "py-1.5" : "py-2"}`}>
                    <div className="ml-7 flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                      <span className="text-slate-700">{component.name}</span>
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-2 py-2">
                    <StatusPill status={component.status} />
                  </td>
                  <td className="border-b border-slate-100 px-2 py-2">
                    <div className="text-slate-700">{component.template}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-slate-400">{component.dataAccount}</div>
                  </td>
                  <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-600">{formatAmount(component.jan)}</td>
                  <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-600">{formatAmount(component.feb)}</td>
                  <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-600">{formatAmount(component.mar)}</td>
                  <td className="border-b border-slate-100 px-2 py-2 text-right text-slate-700">{formatAmount(component.annual)}</td>
                  <td className="border-b border-slate-100 px-2 py-2 text-center">
                    <button className="rounded border border-blue-200 px-2 py-1 text-[11px] text-blue-700 hover:bg-blue-50">配置</button>
                  </td>
                </tr>
              ))}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RuleConfigurator({ component, mode = "panel" }: { component: ComponentLine | null; mode?: "panel" | "modal" | "bottom" }) {
  const content = (
    <div className="flex h-full flex-col bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">规则配置器</div>
            <div className="mt-1 text-xs text-slate-500">{component ? component.name : "请选择一个计算组件"}</div>
          </div>
          <StatusPill status={component?.status ?? "draft"} />
        </div>
      </div>
      <div className="border-b border-slate-200 bg-slate-50 px-3">
        <div className="flex gap-1">
          {["基本信息", "数据来源", "分摊动因", "输出内容"].map((tab, idx) => (
            <button
              key={tab}
              className={`border-b-2 px-3 py-2 text-xs ${
                idx === 1 ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <section className="mb-4 rounded border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-200 bg-blue-50 px-3 py-2">
            <div className="text-xs font-semibold text-blue-900">分摊目标</div>
            <ChevronDown className="h-3.5 w-3.5 text-blue-700" />
          </div>
          <div className="grid gap-3 p-3 md:grid-cols-2">
            <Field label="规则模板">
              <TextInput value={component?.template ?? "贷款利息收入模板"} />
            </Field>
            <Field label="费用项/预算科目">
              <TextInput value="利息净收入 / A0101" muted />
            </Field>
            <Field label="规则来源">
              <TextInput value="组件模板复制应用" />
            </Field>
            <Field label="下发数据科目">
              <TextInput value={component?.dataAccount ?? "请选择数据科目"} />
            </Field>
          </div>
        </section>

        <section className="mb-4 rounded border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-200 bg-blue-50 px-3 py-2">
            <div className="text-xs font-semibold text-blue-900">分摊条件</div>
            <ActionButton>
              <Plus className="h-3.5 w-3.5" />
              条件
            </ActionButton>
          </div>
          <div className="p-3">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-2 py-2 text-left font-medium">字段</th>
                  <th className="px-2 py-2 text-left font-medium">值</th>
                  <th className="px-2 py-2 text-left font-medium">备注</th>
                  <th className="px-2 py-2 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["产品科目", "开鑫贷", "限定当前负责产品"],
                  ["口径范围", "预算数", "用于预测月份"],
                ].map((item) => (
                  <tr key={item[0]} className="border-t border-slate-100">
                    <td className="px-2 py-2 text-slate-700">{item[0]}</td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <span className="rounded border border-slate-200 bg-white px-2 py-1 text-slate-700">{item[1]}</span>
                        <button className="text-blue-700">选择</button>
                      </div>
                    </td>
                    <td className="px-2 py-2 text-slate-500">{item[2]}</td>
                    <td className="px-2 py-2 text-center">
                      <X className="mx-auto h-3.5 w-3.5 text-rose-500" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-200 bg-blue-50 px-3 py-2">
            <div className="text-xs font-semibold text-blue-900">引用配置</div>
            <ActionButton>
              <Link2 className="h-3.5 w-3.5" />
              选择来源
            </ActionButton>
          </div>
          <div className="p-3">
            <div className="grid gap-2">
              {[
                ["规模来源", "A1208 自持日均余额", "0.50", "账户余额"],
                ["利率参数", "CUSTOMER_RATE 对客利率", "0.30", "账户参数"],
                ["调整参数", "OVERDUE_90_RATIO 逾期90+占比", "0.20", "账户风险参数"],
              ].map((item) => (
                <div key={item[0]} className="grid grid-cols-[1.1fr_1.5fr_80px_1fr_42px] items-center gap-2 rounded border border-slate-200 bg-white p-2 text-xs">
                  <span className="text-slate-600">{item[0]}</span>
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600">{item[1]}</span>
                  <span className="rounded border border-slate-200 bg-white px-2 py-1 text-right text-slate-700">{item[2]}</span>
                  <button className="text-blue-700">查看动因</button>
                  <X className="h-3.5 w-3.5 text-rose-500" />
                </div>
              ))}
              <div className="text-right text-[11px] text-slate-500">已输入比例合计：1.00</div>
            </div>
          </div>
        </section>
      </div>
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3">
        <ActionButton>
          <ArrowLeft className="h-3.5 w-3.5" />
          上一步
        </ActionButton>
        <div className="flex items-center gap-2">
          <ActionButton>
            <Save className="h-3.5 w-3.5" />
            保存草稿
          </ActionButton>
          <ActionButton tone="primary">
            <ArrowRight className="h-3.5 w-3.5" />
            下一步
          </ActionButton>
        </div>
      </div>
    </div>
  );

  if (mode === "modal") {
    return (
      <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/30 p-6">
        <div className="h-[82vh] w-[980px] max-w-full overflow-hidden rounded border border-slate-200 bg-white shadow-2xl">{content}</div>
      </div>
    );
  }
  if (mode === "bottom") {
    return <div className="h-[360px] border-t border-slate-200">{content}</div>;
  }
  return <div className="h-full border-l border-slate-200">{content}</div>;
}

function VariantA({
  product,
  selectedRow,
  selectedComponent,
  onSelectRow,
  onSelectComponent,
  onSelectProduct,
}: {
  product: Product;
  selectedRow: string;
  selectedComponent: string;
  onSelectRow: (id: string) => void;
  onSelectComponent: (id: string) => void;
  onSelectProduct: (code: string) => void;
}) {
  const component = rows.flatMap((row) => row.components).find((item) => item.id === selectedComponent) ?? rows[0].components[0];
  return (
    <div className="grid h-full grid-cols-[240px_minmax(0,1fr)_420px] bg-white">
      <ProductRail selectedCode={product.code} onSelect={onSelectProduct} />
      <div className="flex min-w-0 flex-col">
        <WorkbenchHeader product={product} />
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <FileSpreadsheet className="h-4 w-4 text-blue-600" />
            产品试算表
            <span className="text-slate-400">默认按报告科目汇总，展开维护计算组件</span>
          </div>
          <ActionButton>
            <Plus className="h-3.5 w-3.5" />
            新增计算组件
          </ActionButton>
        </div>
        <TrialTable selectedRow={selectedRow} selectedComponent={selectedComponent} onSelectRow={onSelectRow} onSelectComponent={onSelectComponent} />
      </div>
      <RuleConfigurator component={component} />
    </div>
  );
}

function VariantB({
  product,
  selectedRow,
  selectedComponent,
  onSelectRow,
  onSelectComponent,
  onSelectProduct,
}: {
  product: Product;
  selectedRow: string;
  selectedComponent: string;
  onSelectRow: (id: string) => void;
  onSelectComponent: (id: string) => void;
  onSelectProduct: (code: string) => void;
}) {
  const component = rows.flatMap((row) => row.components).find((item) => item.id === selectedComponent) ?? rows[0].components[0];
  return (
    <div className="flex h-full flex-col bg-white">
      <WorkbenchHeader product={product} />
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2">
        <ProductRail selectedCode={product.code} onSelect={onSelectProduct} compact />
      </div>
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto]">
        <div className="overflow-auto p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-800">Excel 式预算组件表</div>
            <div className="flex gap-2">
              <ActionButton>
                <Table2 className="h-3.5 w-3.5" />
                字段
              </ActionButton>
              <ActionButton tone="primary">
                <Plus className="h-3.5 w-3.5" />
                新增组件
              </ActionButton>
            </div>
          </div>
          <div className="rounded border border-slate-200">
            <TrialTable selectedRow={selectedRow} selectedComponent={selectedComponent} onSelectRow={onSelectRow} onSelectComponent={onSelectComponent} dense />
          </div>
        </div>
        <RuleConfigurator component={component} mode="bottom" />
      </div>
    </div>
  );
}

function VariantC({
  product,
  selectedComponent,
  onSelectComponent,
  onSelectProduct,
}: {
  product: Product;
  selectedComponent: string;
  onSelectComponent: (id: string) => void;
  onSelectProduct: (code: string) => void;
}) {
  const component = rows.flatMap((row) => row.components).find((item) => item.id === selectedComponent) ?? rows[0].components[0];
  return (
    <div className="relative flex h-full flex-col bg-slate-50">
      <WorkbenchHeader product={product} />
      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)] gap-4 p-4">
        <div className="rounded border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-3 py-3">
            <div className="text-xs font-semibold text-slate-800">产品与配置状态</div>
            <div className="mt-2 flex h-8 items-center gap-2 rounded border border-slate-200 px-2 text-xs text-slate-400">
              <Search className="h-3.5 w-3.5" />
              搜索产品/科目
            </div>
          </div>
          <div className="p-2">
            <ProductRail selectedCode={product.code} onSelect={onSelectProduct} compact />
          </div>
          <div className="border-t border-slate-200 p-3">
            <div className="mb-2 text-xs font-medium text-slate-700">配置完整度</div>
            {[
              ["公式已配置", "75%"],
              ["引用已绑定", "68%"],
              ["已下发试算", "52%"],
            ].map((item) => (
              <div key={item[0]} className="mb-2">
                <div className="mb-1 flex justify-between text-[11px] text-slate-500">
                  <span>{item[0]}</span>
                  <span>{item[1]}</span>
                </div>
                <div className="h-1.5 rounded bg-slate-100">
                  <div className="h-1.5 rounded bg-blue-500" style={{ width: item[1] }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="min-w-0 overflow-auto rounded border border-slate-200 bg-white">
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-slate-800">报告科目组件看板</div>
                <div className="mt-1 text-xs text-slate-500">按科目块查看组件，点击组件进入规则配置窗口</div>
              </div>
              <ActionButton tone="primary">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                批量下发
              </ActionButton>
            </div>
          </div>
          <div className="grid gap-3 p-4 xl:grid-cols-2">
            {rows.map((row) => (
              <div key={row.id} className="rounded border border-slate-200 bg-white">
                <div className="border-b border-slate-100 bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-semibold text-slate-800">{row.name}</div>
                      <div className="mt-0.5 font-mono text-[11px] text-slate-400">{row.reportCode}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-slate-900">{formatAmount(row.annual)}</div>
                      <div className="text-[11px] text-slate-400">全年试算</div>
                    </div>
                  </div>
                </div>
                <div className="space-y-2 p-3">
                  {row.components.length === 0 ? (
                    <button className="flex h-16 w-full items-center justify-center gap-2 rounded border border-dashed border-slate-300 text-xs text-slate-500 hover:bg-slate-50">
                      <Plus className="h-3.5 w-3.5" />
                      添加计算组件
                    </button>
                  ) : (
                    row.components.map((line) => (
                      <button
                        key={line.id}
                        onClick={() => onSelectComponent(line.id)}
                        className={`w-full rounded border p-2 text-left ${
                          selectedComponent === line.id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-slate-800">{line.name}</span>
                          <StatusPill status={line.status} />
                        </div>
                        <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                          <Database className="h-3 w-3" />
                          {line.dataAccount}
                        </div>
                        <div className="mt-1 truncate font-mono text-[11px] text-slate-400">{line.formula}</div>
                      </button>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <RuleConfigurator component={component} mode="modal" />
    </div>
  );
}

const variantLabels: Record<VariantKey, string> = {
  A: "A | 三栏工作台",
  B: "B | 表格优先",
  C: "C | 看板+配置窗口",
};

function getInitialVariant(): VariantKey {
  if (typeof window === "undefined") return "A";
  const value = new URLSearchParams(window.location.search).get("variant");
  return value === "B" || value === "C" ? value : "A";
}

function PrototypeSwitcher({ current, onChange }: { current: VariantKey; onChange: (variant: VariantKey) => void }) {
  const variants: VariantKey[] = ["A", "B", "C"];
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const idx = variants.indexOf(current);
      const next = event.key === "ArrowRight" ? variants[(idx + 1) % variants.length] : variants[(idx - 1 + variants.length) % variants.length];
      onChange(next);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [current, onChange, variants]);

  if (import.meta.env.PROD) return null;
  const idx = variants.indexOf(current);
  const prev = variants[(idx - 1 + variants.length) % variants.length];
  const next = variants[(idx + 1) % variants.length];
  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-white shadow-xl">
      <button onClick={() => onChange(prev)} className="rounded-full p-1 hover:bg-white/10" title="上一个方案">
        <ArrowLeft className="h-4 w-4" />
      </button>
      <span className="min-w-[150px] text-center">{variantLabels[current]}</span>
      <button onClick={() => onChange(next)} className="rounded-full p-1 hover:bg-white/10" title="下一个方案">
        <ArrowRight className="h-4 w-4" />
      </button>
    </div>
  );
}

export function ProductBudgetWorkbenchPrototypeContent() {
  const [variant, setVariant] = useState<VariantKey>(() => getInitialVariant());
  const [selectedProductCode, setSelectedProductCode] = useState(products[0].code);
  const [selectedRow, setSelectedRow] = useState(rows[0].id);
  const [selectedComponent, setSelectedComponent] = useState(rows[0].components[0].id);
  const selectedProduct = useMemo(
    () => products.find((product) => product.code === selectedProductCode) ?? products[0],
    [selectedProductCode],
  );

  const changeVariant = (next: VariantKey) => {
    setVariant(next);
    const url = new URL(window.location.href);
    url.searchParams.set("variant", next);
    window.history.replaceState({}, "", url.toString());
  };

  return (
    <div className="bb-page relative min-h-[720px] overflow-hidden p-0">
      <div className="bb-status-banner bb-status-banner-warning absolute right-4 top-3 z-30 flex items-center gap-1 px-2 py-1 text-[11px]">
        <Layers3 className="h-3.5 w-3.5" />
        原型页面，仅保留为设计对照；正式入口已使用统一工作台
      </div>
      {variant === "A" ? (
        <VariantA
          product={selectedProduct}
          selectedRow={selectedRow}
          selectedComponent={selectedComponent}
          onSelectRow={setSelectedRow}
          onSelectComponent={setSelectedComponent}
          onSelectProduct={setSelectedProductCode}
        />
      ) : variant === "B" ? (
        <VariantB
          product={selectedProduct}
          selectedRow={selectedRow}
          selectedComponent={selectedComponent}
          onSelectRow={setSelectedRow}
          onSelectComponent={setSelectedComponent}
          onSelectProduct={setSelectedProductCode}
        />
      ) : (
        <VariantC
          product={selectedProduct}
          selectedComponent={selectedComponent}
          onSelectComponent={setSelectedComponent}
          onSelectProduct={setSelectedProductCode}
        />
      )}
      <PrototypeSwitcher current={variant} onChange={changeVariant} />
    </div>
  );
}
