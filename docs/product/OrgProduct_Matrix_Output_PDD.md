# 机构及产品 · 矩阵输出报表（总册）

| 项目 | 说明 |
|------|------|
| **文档版本** | v1.2 |
| **适用范围** | 预测输出 **模式 B**：矩阵输出（多种 `layout_mode`，见 §0） |
| **已收录模板** | ① 风险驱动表 ② 税前利润分解 ③ **指标×机构×时间**（§4，待命名） |
| **相关文档** | [`OrgProduct_Naming_Glossary.md`](OrgProduct_Naming_Glossary.md)（**术语表**）、[`OrgProduct_RollingForecast_Calculation_PDD.md`](OrgProduct_RollingForecast_Calculation_PDD.md)（§3 菜单与阶段 0→2 顺序） |

> 原 [`OrgProduct_RiskDriver_Matrix_Output_PDD.md`](OrgProduct_RiskDriver_Matrix_Output_PDD.md) 内容已并入本文 §2；后续以**本总册**为准。

---

## 0. 一张图分清四种「表」

> 标准中文名、需求代号与发需求模板见 **[`OrgProduct_Naming_Glossary.md`](OrgProduct_Naming_Glossary.md)**（A=单机构指标表，B/C/D=矩阵报表）。

```text
┌─────────────────────────────────────────────────────────────────┐
│ A. 指标表（维护用 · 机构及产品指标）                              │
│    行 = 指标    列 = 时间（仅一个机构）                           │
│    例：B01 企业金融业务状况表                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ B. 矩阵 ①  行=机构      列=版本 × 多指标   （风险驱动表）          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ C. 矩阵 ②  行=机构      列=仅版本         （税前利润分解）        │
│            整张表一个指标                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ D. 矩阵 ③  行=指标      列=机构 × 时间     （你问的这种）          │
│    例：同一套科目，横向对比 A01/B01/… 的 25实际/26预算/26预测      │
└─────────────────────────────────────────────────────────────────┘
```

| 类型 | 是否矩阵报表 | 是否做成「指标表」 |
|------|-------------|-------------------|
| A 指标表 | 否（数据源） | **是**（维护科目与公式） |
| B / C / D | **是**（输出模板） | **否**（只引用 A 的取数结果） |

**统一结论**：B、C、D 都用 **矩阵输出模板** + 同一套 `run` 引擎；差别在 `layout_mode`（§1.2）。  
**D 与 A 的区别**：A 是「一个机构一张纵表」；D 是「多个机构并排到列上的对比视图」，仍是**输出**，不是新的指标维护结构。

---

## 1. 统一处理框架（B / C / D 共用）

### 1.1 数据流（不变）

```text
各主体指标表 + 数据录入 + 预测输出（单表跑批）
              ↓ 按单元格 source 引用
矩阵模板 run → 二维结果 → 页面展示 / Excel 导出
```

### 1.2 模板核心字段

| 字段 | 说明 |
|------|------|
| `template_id` | 如 `risk_driver_matrix`、`pretax_profit_breakdown` |
| `layout_mode` | `version_x_metrics`（①）· `single_metric`（②）· `metrics_x_entity_time`（③） |
| `unit` | 如 亿元 |
| `column_groups[]` | 25年实际 / 26年预算 / 26年预测（两种模板都有） |
| `column_metrics[]` | **仅①需要**；②可省略或仅含 1 个虚拟列 `value` |
| `primary_metric` | **仅②需要**：整张表取的指标，如 `税前利润` + 指标 code |
| `rows[]` | 行定义（见 §1.3） |

### 1.3 行类型（两种模板共用 · 关键）

| row_type | 显示示例 | 是否在机构及产品树 | 取数方式 |
|----------|----------|-------------------|----------|
| `group` | `1.个金群`、`2.企金群` | 是（二级） | **不取数**，仅展示层级/缩进 |
| `entity` | `A01 泛微粒贷`、`B01 企业金融` | 是 | 同一指标 → `{entity}/{表}/{primary_metric}@{版本}` |
| `metric_line` | `减：返税收入`、`减：冲销利润分享` | **否** | **指标表取数** → 固定 `source_ref`（多在 AA/全行损益表） |
| `subtotal` | 可选：某群小计 | 否 | `SUM` 上方 entity 行，或单独 source |
| `total` | `AA 税前利润` | 是（一级） | 引用 AA 该指标，或 `SUM` 以上各行（由业务定） |
| `section` | `附1：账面数据` | 否 | 仅①风险驱动表用，分区标题 |

**你关心的「几行不是机构及产品里的」** → 一律用 **`metric_line`**，在模板里写清 `source_ref`，**不要**硬塞进机构树。

### 1.4 单元格引用（与单表公式一致）

```text
{机构代码}/{指标表名}/{指标代码}@{版本组}
```

| 版本组 | 含义 |
|--------|------|
| `y25_actual` | 25年实际 |
| `y26_budget` | 26年预算 |
| `y26_forecast` | 26年预测（滚动预测跑批后全年口径） |

### 1.5 引擎逻辑（伪代码 · 一套代码两种模板）

```text
for each row in template.rows:
  if row.type in (group, section): emit label only
  if row.type == entity:
    for each column_group:
      value = resolve(primary_metric or column_metric, row.entity_code, column_group)
  if row.type == metric_line:
    for each column_group:
      value = resolve(row.source_ref, column_group)   # 不经过 entity_code
  if row.type == total / subtotal:
    value = resolve(row.source_ref) OR sum(children rows)
emit matrix
```

---

## 2. 模板① 风险驱动表（`layout_mode = version_x_metrics`）

多指标矩阵：列 = **版本组 ×（贷款日均、风险成本、风险成本率）**；行 = 机构 + 附1 账面 + 附2 代偿。

| 列 | 类型 |
|----|------|
| 贷款日均、风险成本 | 引用 |
| 风险成本率 | 表内算：`风险成本 / 贷款日均`（同行、同版本组） |

表样、行分区、R0 清单见原风险驱动表设计（主表 9 行 + 附1 + 附2）。`template_id = risk_driver_matrix`。

---

## 3. 模板② 税前利润分解表（`layout_mode = single_metric`）

### 3.1 业务表样（与你截图一致）

| 机构或产品码 | 机构或产品名称 | 25年实际 | 26年预算 | 26年预测 |
|--------------|----------------|----------|----------|----------|
| A | 1.个金群 | | | |
| A01 | 1.1泛微粒贷 | ● | ● | ● |
| A02 | 1.2微账户 | ● | ● | ● |
| … | … | | | |
| B | 2.企金群 | | | |
| B01 | 2.1企业金融 | ● | ● | ● |
| B02 | 2.2金融市场 | ● | ● | ● |
| C / D / E / F | 数字金融 / 国际 / 导流 / 司库… | | | |
| （空） | 减：返税收入 | ● | ● | ● |
| （空） | 减：冲销利润分享 | ● | ● | ● |
| （空） | 减：冲销超额拨备 | ● | ● | ● |
| AA | 税前利润 | ● | ● | ● |

- **整张表一个指标**：`税前利润`（分解行展示的是同一指标在不同「行语义」下的口径，或调整项指标）。
- **列**：只有时间版本，没有「贷款日均 / 风险成本」那种副列。

### 3.2 行怎么配

| 块 | row_type | 说明 |
|----|----------|------|
| 个金群、企金群… | `group` | 对应树上级 `A`、`B`…，只显示不加总（或可选展示群合计） |
| A01、B01… | `entity` | `entity_code` = 树 code；单元格自动取 **primary_metric** |
| 减：返税收入 等 | `metric_line` | **不在机构树**；每列 `source_ref` 指向全行/司库等指标，例：`AA/损益表/AA.xx@y26_forecast` |
| AA 税前利润 | `total` | 优先 `AA/损益表/{税前利润code}@版本`；或与上面 entity 行 + 调整行按业务公式汇总 |

### 3.3 `primary_metric` 与调整行

```json
{
  "template_id": "pretax_profit_breakdown",
  "template_name": "税前利润分解表",
  "layout_mode": "single_metric",
  "unit": "亿元",
  "primary_metric": {
    "name": "税前利润",
    "default_table": "损益表",
    "metric_code": "AA.??.??"
  },
  "column_groups": [
    { "group_id": "y25_actual", "label": "25年实际", "year": 2025, "data_kind": "actual" },
    { "group_id": "y26_budget", "label": "26年预算", "year": 2026, "data_kind": "budget" },
    { "group_id": "y26_forecast", "label": "26年预测", "year": 2026, "data_kind": "forecast" }
  ],
  "rows": [
    { "row_id": "g_a", "row_type": "group", "entity_code": "A", "display_name": "1.个金群" },
    { "row_id": "e_a01", "row_type": "entity", "entity_code": "A01", "display_name": "1.1泛微粒贷" },
    { "row_id": "m_tax_refund", "row_type": "metric_line", "display_name": "减：返税收入",
      "cells": {
        "y26_forecast": { "source": "AA/损益表/AA.??.??@y26_forecast" }
      }
    },
    { "row_id": "t_aa", "row_type": "total", "entity_code": "AA", "display_name": "税前利润" }
  ]
}
```

- **entity 行**：未写 `cells` 时，引擎用 `primary_metric` + `entity_code` 自动解析。
- **metric_line 行**：必须写 `source_ref`（或按版本写 `cells`），因为**不能**从机构树推导机构 code。

### 3.4 矩阵 ① / ② 对比

|  | ① 风险驱动表 | ② 税前利润分解表 |
|--|-------------|-----------------|
| `layout_mode` | `version_x_metrics` | `single_metric` |
| 列 | 3 指标 × 3 版本 | 仅 3 版本 |
| 行主体 | 产品 + 附表 | 群 + 产品 + 调整项 + AA 合计 |
| 非机构行 | `special` / 附表 | **`metric_line`**（减：返税…） |
| 表内列公式 | 风险成本率 | 一般无（除非合计行 SUM） |

---

## 4. 模板③ 指标 × 机构 × 时间（`layout_mode = metrics_x_entity_time`）

### 4.1 表样（概念）

```text
指标层级 | 指标代码 | 指标名称 | 科目性质 │ A01·25实际 │ A01·26预算 │ A01·26预测 │ B01·25实际 │ … │
```

- **行**：与指标表相同——科目树的一串指标（可引用同一张「全行对比表」指标清单）。
- **列**：**机构（或产品）** × **版本/时间** 两级表头（与 ① 把「指标」放在列上正好对调）。

### 4.2 是不是矩阵报表？

**是。** 属于矩阵模板 **③**，不是第四种维护模型。

| 维度 | 指标表 A | 矩阵 ③ D |
|------|----------|-----------|
| 看谁 | 单机构纵向 | **多机构横向对比** |
| 行 | 指标 | 指标（行定义可复用指标树） |
| 列 | 时间 | **机构 × 时间** |
| 配置 | 机构及产品指标 | 矩阵模板：`row_metrics[]` + `column_entities[]` + `column_groups[]` |

### 4.3 配置要点

```json
{
  "template_id": "metric_compare_by_entity",
  "layout_mode": "metrics_x_entity_time",
  "metric_source": { "table_scope": "AA", "table_name": "损益表", "metric_tree": "import_from_snapshot" },
  "column_entities": [
    { "entity_code": "A01", "label": "泛微粒贷" },
    { "entity_code": "B01", "label": "企业金融" }
  ],
  "column_groups": [
    { "group_id": "y25_actual", "label": "25年实际", "year": 2025, "data_kind": "actual" },
    { "group_id": "y26_forecast", "label": "26年预测", "year": 2026, "data_kind": "forecast" }
  ]
}
```

**单元格**（引擎展开，不必手写每格）：

```text
cell(指标 i, 机构 e, 版本 v) = resolve( e / {表} / {指标i.code} @ v )
```

- 指标行仍可在 **指标表** 维护层级、性质、公式；跑批仍按**各机构**单表执行；矩阵 ③ 只做 **拼装展示**。
- 若某格要「非标准机构」（同 ② 的 `metric_line`），可在行上用 `metric_row` + 固定 `source_ref`（少数例外）。

### 4.4 与 ①② 及透视模块的关系

| 需求 | 建议 |
|------|------|
| 固定版式、常导出的管理报表 | 矩阵 ③ 模板 + 预测输出 |
| 临时拖拽、多维探索 | 继续用现有 **多维分析 / 透视** |
| 单机构编报 | 仍用 **指标表 + 数据录入**（A） |

### 4.5 四种 layout 一览

| layout_mode | 行 | 列 |
|-------------|----|----|
| `version_x_metrics` | 机构 | 版本 × 多指标 |
| `single_metric` | 机构（+ metric_line） | 版本 |
| **`metrics_x_entity_time`** | **指标** | **机构 × 版本** |
| （非矩阵）指标表 | 指标 | 时间（单机构） |

---

## 5. 系统放哪、和指标表的关系

| 问题 | 答案 |
|------|------|
| 做成指标表吗？ | **否**（A 类仍是指标表；B/C/D 是矩阵模板） |
| 模板配置放哪？ | **预算数据输入 → 预测规则 → 矩阵报表模板**（见 Rolling PDD §3） |
| 运行放哪？ | **预测输出** → 模式 B → 选模板（①②③）→ 运行 / 导出 |
| 机构树作用？ | 只驱动 `group` / `entity` 行；`metric_line` 不靠树，靠 `source_ref` |
| 指标表作用？ | 提供 **metric_code** 与单表跑批结果；矩阵只引用 |
| 一张源表叫「风险驱动表」？ | 可与矩阵模板同名不同义：源数据=指标表；输出=矩阵报表 |

**API（规划，两模板共用）**

| 方法 | 路径 |
|------|------|
| GET | `/api/org-product-matrix/templates` |
| POST | `/api/org-product-matrix/run`（`template_id` + 版本 + 滚动月） |
| POST | `/api/org-product-matrix/export` |

---

## 6. 实施顺序（建议）

| 顺序 | 内容 |
|------|------|
| 1 | 夯实单机构 **指标表 + 数据录入 + 预测输出（模式 A）** |
| 2 | 矩阵引擎 R1：`layout_mode` + `row_type` + `run` + Excel |
| 3 | 先做 **② 税前利润分解**（列少、易验证）或先做 **① 风险驱动**（你已出表样） |
| 4 | 前端预测输出：Tab「指标表输出」/「矩阵报表」下拉选模板 |

### R0 待填（模板② 税前利润）

- [ ] `primary_metric` 在 AA（及 A01、B01…）损益表上的 **指标代码**
- [ ] 三行「减：…」各自的 **source_ref**（机构多为 AA 或司库 F）
- [ ] AA 税前利润行：取数还是 **SUM(以上行)**？
- [ ] 各 `group` / `entity` 与机构树 code 终稿（A、A01、B01、C01…）

---

## 7. 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-05-27 | 风险驱动表单页 |
| v1.1 | 2026-05-27 | 总册：统一框架 + 模板② 税前利润分解（单指标矩阵） |
| v1.2 | 2026-05-27 | 模板③ 行=指标、列=机构×时间 |
