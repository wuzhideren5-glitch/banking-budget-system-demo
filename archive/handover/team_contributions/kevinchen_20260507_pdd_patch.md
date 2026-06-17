# PDD 章节补丁 — kevinchen — 2026-05-07

> 历史归档说明：本文件是同事提交包原始补丁，不代表当前运行 schema。旧 `driver_*` 表和旧预算驱动页面已退休；当前取数和配置以标准数据科目指标树、数据科目维护表、费用预测逻辑配置和模拟测算接口为准。

> 请主合并人使用 /merge-release 将此补丁内容合入正式 PDD。

---

## System PDD 建议新增 (§0.8)

- 新增"**预算预测驱动因素模块**"，为预算编制提供参数化预测入口：
  - 用户可在"预算预测驱动"页面按产品、按月填入关键业务驱动参数（如日均余额、利率等），系统自动按预设公式链计算出对应的预算结果科目（如利息收入）。
  - 驱动参数按业务分类组织为分类-指标-产品的三级树形结构，共涵盖 5 大业务分类（存贷款规模、利率价格、中间收入、费用支出、其他参数），14 个核心驱动指标。
  - 支持 Excel 模板下载 → 离线填报 → 上传导入的工作流，导入后自动触发预算公式重算与汇总刷新，所见即所得。
  - 导入结果以表格形式展示每个月、每个产品的计算结果值，便于业务人员快速校验核对。
- 预算预测驱动模块独立于现有"预算基础数据录入"页面，定位为**业务驱动型预算编制**的快捷通道，适合月末预测、情景模拟等场景。
- 本模块涉及后端 4 个接口（分类树查询、模板下载、Excel 导入、JSON 导入）、前端 1 个独立页面。

> 插入位置：System PDD 的 `## 0.7` 之后，新增 `## 0.8 本轮需求变更（2026-05-07）— kevinchen` 小节。

---

## Database PDD 建议新增 (§0.3)

### 驱动参数配置表（common.db）

新增三张配置表，均位于 `common.db`（跨年度共享），用于定义"哪些驱动参数可以输入、参数的产品范围是什么"：

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `driver_category` | 驱动因素业务分类 | `category_code`（主键）、`category_name`、`sort_order` |
| `driver_indicator` | 驱动指标定义 | `indicator_code`（主键）、`category_code`（外键→driver_category）、`indicator_name`、`value_type`（数值/百分比）、`data_acct_code`（关联数据科目）、`has_product_detail`（是否按产品明细输入）、`has_monthly_detail`（是否按月输入） |
| `driver_product` | 指标-产品绑定关系 | `indicator_code`（外键→driver_indicator）、`product_code`（外键→product_type）、UNIQUE(indicator_code, product_code) |

种子数据：
- 5 个分类：存款规模、贷款规模、利率价格、中间业务收入、费用支出
- 14 个指标：涵盖存款日均余额、贷款日均余额、利率、手续费率、费用率等
- 产品绑定：所有 `has_product_detail=1` 的指标自动绑定全部"贷"类产品

### 驱动参数输入数据（budget_{year}.db）

驱动参数的**实际输入值**不单独建表，而是直接写入预算基础数据表 `budget_data`：
- 每条驱动输入对应一行 `version='driver'`、`data_acct_code` 取指标关联的数据科目、`product_code` 取具体产品、`month_01~month_12` 存储月度值。
- 公式计算结果也写入 `budget_data`（`version='driver'`），由导入流程自动触发 `recalculate_accounts()` 执行。
- 计算结果同步反映到 `budget_summary`（导入后自动重建）。

> 插入位置：Database PDD `## 0.2` 之后，新增 `## 0.3 本轮同步说明（2026-05-07）— kevinchen` 小节。

---

## Agent PDD 建议新增

- 本次无 Agent 变更，无需更新。

---

## 补充说明

- 启动后需确保 `common.db` 中有 `driver_category`、`driver_indicator`、`driver_product` 三张表及种子数据（`init_db.py` 自动执行建表与播种）。
- 后端新增依赖 `openpyxl`（Excel 读写），需确认 `requirements.txt` 已包含。
- 前端无需新增 npm 依赖，仅新增纯逻辑页面组件。
- 如果接手方看到页面导入后计算值与预期不符，当前应运行 `apps/api/test_metric_formula_e2e.py` 验证标准指标公式链路；本历史补丁中的旧驱动页面验证脚本名已失效。
