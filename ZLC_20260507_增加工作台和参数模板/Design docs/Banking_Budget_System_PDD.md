# 银行业务预算管理系统及智能体（AI-Native Budget System）系统设计文档（System PDD）

| 项目 | 说明 |
|------|------|
| **文档版本** | v1.0 |
| **产品定位** | 面向银行业务的财务预算原型系统，集成传统数据编报与 LangGraph 智能体分析，实现 AI 原生的预算管理与测算体验。 |
| **界面主标题（Figma）** | **管衡之家-财务预算智能体**（顶栏与欢迎文案等以 Figma / `src_from_Figma/` 为准）。 |
| **交付范围** | **当前目标版本**：公司内网 **多用户**——通过服务器地址 Web 访问，含登录会话与 **RBAC**；并支持“当前年度多版本透视”与“多年度对比透视（`compare.db`）”。演进路径见 **Rules「范围与演进」** 及本文 **§2.4**（与 Database PDD / ERD 表头 **「交付范围」** 一致）。信息架构、布局、控件与文案仍以 **Figma** 为准。 |
| **数据与编码权威** | **表结构、字段、约束及主数据编码（科目/产品/报告/部门等）以 Database PDD 为唯一权威。** Figma / `src_from_Figma/` 中的编号、表格示例**仅作界面与前端逻辑参考**，持久化与校验必须与 Database PDD 一致。 |

---

## 0.5 本轮需求变更（2026-04-28）

- 多维分析导航项“数据透视图”更名为“多年度数据透视图”。
- 左侧导航“智能分析报告”“智能演示PPT”采用灰色视觉态（功能建设中提示），但保留可点击打开能力。
- Agent 查询确认区的“已锁定查询维度”文案改为紧凑排版，减少空行。
- 透视建议说明从确认正文移除，统一由聊天侧“管衡推荐透视视角”卡片承载，避免重复。
- 多年度对比透视应用建议时，搜索框需保留 `pivot_search_text` 预填（不再被 compare 分支清空）。

## 0.6 本轮需求变更（2026-04-29）

- 新增“**全局自动刷新任务**”：后端每 **10 分钟**检查并执行一次“预算库公式重算 + 预算汇总刷新 + Compare 刷新”链路。
- 自动任务仅在“**至少 1 个有效登录会话**”存在时运行（会话以 `user_sessions.expire_time` 判定有效，过期会话先清理）。
- 每个年度库（`budget_{year}.db`）在 `settings` 表新增并维护键 `global_refresh_time_a`（简称 **A**，该年度库上次全局刷新时间）。
- `compare.db` 新增 `settings` 表并维护键 `global_refresh_time_b`（简称 **B**，Compare 上次全局刷新时间）。
- 自动任务流程（MUST）：
  1. 对每个年度库检查 `budget_data.need_calc=1`，若命中则执行公式重算；
  2. 重算后若该库任一 `budget_data.update_time > A`，则重建该库所有版本的 `budget_summary`，并重写 A；
  3. 若任一年度库 A 晚于 B，则刷新 `compare_budget_summary`，并重写 B。
- 底栏“数据库最后全局计算并刷新时间”统一显示 **B**；若 B 缺失则回退显示当前年度 `budget_summary` 最大 `update_time`。

---

## 0. 文档定位与权威性

### 0.1 四文档分工（阅读顺序建议）

| 文档 | 职责 |
|------|------|
| [**Banking_Budget_Rules_PDD.md**](Banking_Budget_Rules_PDD.md) | **工程底线**（MUST/SHOULD/MUST NOT）：财务单一事实来源、`budget_data`/`budget_summary`/`compare_budget_summary` 口径、`need_calc` 与预聚合、审计、安全与 AI 治理、Excel 血缘、**Figma / `src/` / `src_from_Figma/`**；交付阶段见 Rules **「范围与演进」**。 |
| [**Banking_Budget_Database_PDD.md**](Banking_Budget_Database_PDD.md) | **数据模型（唯一权威）**：表/字段、物理名 snake_case、主数据编码规则、`Period.quarter`、`BudgetData`（**`budget_actual`** 区分预算/实际口径）、`BudgetSummary`、`operation_log`（`common.db`）等；**不以 Figma 示例为准**。 |
| [**Banking_Budget_Database_ERD.md**](Banking_Budget_Database_ERD.md) | **库表关系图**（Mermaid），与 Database PDD 同步。 |
| [**Banking_Budget_Agent_PDD.md**](Banking_Budget_Agent_PDD.md) | **Agent 设计权威文档**：LangGraph 状态机、意图分流（预算查询分析 vs 知识/通用问答）、澄清循环、只读 SQL 安全护栏、短期/长期记忆、六按钮交互规格、管衡人设与话术、评测指标与分期路线。 |
| **本文（System PDD）** | **产品目标、用户场景、功能与体验设计**（PRD + 功能设计）：按 Figma 归纳界面壳层、导航与模块；Agent 记忆与安全交互、Excel 导出惯例、技术路线概括；**不替代** Rules/Database 的条款与表结构。 |
| **Figma** + **`src_from_Figma/`** | **前端界面视觉、布局、交互与前端逻辑**的定稿与只读导出；可交付实现位于 **`src/`**（Rules **E.7**）。**凡与 Figma 不一致的前端表现，以 Figma 为准调整**。**例外**：（1）表头「交付范围」—以内网多用户目标为准；（2）**库表与主数据编码**—以 **Database PDD** 为准，不得以 Figma 示例覆盖。 |

### 0.2 交叉引用与冲突处理

- 工程与数据持久化约束：**以 Rules、Database PDD 为准**；若本文与之冲突，**修订本文**。
- **数据库与主数据编码**：**唯一权威为 Database PDD**；Figma / `src_from_Figma/` 内 mock 数据、示例编号**不定义**持久化契约。
- 界面样式、组件结构、布局比例、导航命名、典型前端流程：**以 Figma / `src_from_Figma/` 为准**；本文对界面作**结构化复述**，便于评审与实现对照。
- Rules 中「参见 System PDD」处，除另有注明外，常指 **§2.2** / **§2.2.1**（业务口径、`need_calc`、**value_type** 小数位）、**§2.3**（Agent）、**§2.5**（Excel 惯例）等对应小节。

### 0.3 本文职责（摘要）

- 描述产品目标、用户场景、功能设计与体验预期（与 Figma 导出对齐）。
- 需要条款级约束时**引用** Rules / Database PDD，避免重复定义已定型内容。
- 后端与实现细节在 **§3** 概括；栈选型与离线约束与 Rules **E.5**、**E.7** 一致。

### 0.4 界面用语与数据实体（避免歧义）

- **产品科目**（Figma 导航）对应库表逻辑实体 **`ProductType`** / 物理表 **`product_type`**（Database PDD）。
- **数据科目 / 报告科目 / 部门科目**与 **`DataAccount`、`ReportAccount`、`DeptAccount`** 等一致；**字段定义、编码规则、校验与持久化**以 **Database PDD** 为准。**各维护页的控件布局、交互、空态与视觉**以 **Figma** 为准。

---

## 1. 产品需求（PRD）

### 1.1 核心目标

1. **类 Excel 的预算编报体验**：高密度表格录入与查询；界面极简紧凑，优先利用 PC 宽屏（**视觉与布局以 Figma 为准**）。
2. **财务智能体（Agent）**：基于 LangGraph 与 Deepseek API，支持同环比、预实对比、滚动预算与复杂测算（目标求解等）；安全与确认流见 **§2.3** 与 Rules **E.3**；**右侧「智能助手」面板布局与按钮以 Figma 为准**。
3. **数据架构**：**`common.db`**（字典、**`operation_log`** 全库审计等）+ **`budget_{year}.db`**（**`version`、`budget_data`、`budget_summary`**）；底层业务数值落在 **`budget_data`**（**`budget_actual`** 区分预算/实际口径），由 **`data_account`**、**`product_type`** 等字典约束颗粒度与公式；**报告科目**、**部门科目**为树状与汇总维度，汇总由引擎计算并落入 **`budget_summary`**（**禁止**用前端自算替代引擎结论，Rules **E.1**、**E.4**）。
4. **大规模字典与效率**：支持 **Tab / 方向键**（Rules **E.6**）及树状映射维护（交互以 Figma 为准）。
5. **版本与留痕**：高频版本迭代；顶栏常驻**软件版本**、**预算年份**、**预算版本号**、**预算版本名称**等（字段布局以 Figma 为准）；变更审计见 Rules **E.2** 与 `operation_log`。

### 1.2 核心用户场景（与左侧导航模块对齐）

- **基础数据维护**：**数据科目维护**、**报告科目维护**、**产品科目维护**、**部门科目维护**（树状映射、**Tree Drag & Drop** 等以 Figma 为准）；规模参考：数据科目约 2000、报告科目约 500、产品约 200、部门约 100；**公式编辑器**、Excel 导入等以各页工具栏为准。
- **预算数据输入**：拆分为两个相邻页面。**预测预算工作台**用于维护预测行、绑定数据科目/假设参数/规则模板的关系，持久化表为 **`forecast_workbench_layout`** 与 **`forecast_line_binding`**；**预测结果明细台账**承接原“预算基础数据维护”，在**当前产品**上下文中，以**报告层级 + 数据科目 + 月度列**（12 个月）为主的类表格填报。**界面「预算值 / 实际值」切换**对应持久化字段 **`budget_actual`**（**`0`**=预算，**`1`**=实际，见 Database PDD）。页面标题需显示**预算年份 + 当前编辑版本号/版本名称**。**报告层级列**为映射/展开后的**视图**，非 `budget_data` 物理列；落库粒度为 **数据科目 × 产品 × 期间 × 版本 × `budget_actual`**（`budget_data.product_code` 与当前所选产品一致；**适用所有产品**类数据科目在字典层为 `data_account.applies_to_all_products=1`，明细仍按产品分行存储）。批量 Excel 导入须满足 Rules **E.5**（导入幂等）。
- **多维分析工具**：**数据透视表-当前年度多版本透视**、**数据透视表-多年度对比透视**、**多年度数据透视图**、**智能分析报告**、**智能演示 PPT**；前者读取 **`budget_summary`**，后者读取 **`compare.db.compare_budget_summary`**，均以预聚合结果与引擎结论为准（Rules **E.1**、**E.4**）。两类透视表界面的「报告科目 / 数据科目」行维度文本应**左侧顶格**显示，不使用层级缩进。
- **系统配置中心**：**用户和权限管理**、**系统设定控制** —界面信息架构与 Figma 一致，并落地用户维护、数据库文件维护、版本管理、编辑版本/展示版本管理等能力（见 **§2.4**）。
- **帮助与使用说明**：**使用说明**、**常见问题**、**联系管理员**（内容与结构以 Figma 为准）。其中若出现 **PDF** 等非 Excel 导出表述，**以产品分期为准**；当前工程验收上 **Excel 导出血缘**以 Rules **E.6** 为准。
- **版本管理**：创建/切换版本、在历史版本上修改等产品行为以 Figma 为准；**凡改必记**（Rules **E.2**）。
- **滚动预算与预实**：按业务规则拼接视图；展示与结论以引擎及 **`BudgetSummary`** 为准。
- **Agent 分析**：口径确认、取数、联动工作区；**高危写库**须 SQL/影响行与确认（Rules **E.3**）。
- **目标求解**：沙箱/临时库迭代；应用前满足版本与审计策略。

---

## 2. 功能设计（FDD）

### 2.1 界面壳层与信息架构（以 Figma 为准）

**总则**：整体为 **顶栏 + 中部可调整宽度的三栏 + 底栏状态栏**（`src_from_Figma/app/App.tsx`）。中部三栏为 **左侧导航**、**中间工作区**、**右侧智能助手**；左右栏可**折叠**为窄条并一键展开；栏宽通过**可拖拽分隔条**调整（如 `react-resizable-panels`）。**配色、间距、字体、组件形态以 Figma / `src_from_Figma/` 为准**；可交付代码在 **`src/`**，**禁止**直接改 **`src_from_Figma/`**（Rules **E.7**）。

**顶栏（Header）** 须体现（具体排布与样式以 Figma 为准）：

- **软件版本**（如 `2026_v2.13` 形式）；
- **预算年份**；
- **预算版本号**（与 `version` 表主键或业务编号映射，以实现为准）；
- **预算版本名称**（与 `Version.version_name` 等一致）；
- **当前用户展示名与角色**（来自登录会话与用户表）。

**左侧导航树**（层级与文案与 Figma `NavigationTree` 一致）：

1. **基础数据维护** → 数据科目维护；报告科目维护；产品科目维护；部门科目维护。  
2. **预算数据输入** → 预测预算工作台；预测结果明细台账。  
3. **多维分析工具** → 数据透视表-当前年度多版本透视；数据透视表-多年度对比透视；多年度数据透视图；智能分析报告；智能演示 PPT（后两项当前为灰色视觉态，保留可点开入口）。
4. **系统配置中心** → 用户和权限管理；系统设定控制。  
5. **帮助与使用说明** → 使用说明；常见问题；联系管理员。  

点击叶子节点在**中间工作区**打开对应 **Tab**（同模块多开策略以实现为准，默认与 Figma 行为一致）。

**中间工作区**：

- **多标签页**：可切换、可关闭；**超过 8 个标签**时出现溢出入口（如下拉「更多」），可将隐藏标签**切换到靠前位置**（与 Figma `WorkArea` 一致）。  
- **无标签时**：显示欢迎区文案（如「欢迎使用银行财务预算管理系统」及引导语，以 Figma 为准）。  
- 各模块内容区：**高密度表格**、树表、筛选器、工具栏、**Tab/方向键**导航（Rules **E.6**）等以各页 Figma 为准。

**右侧智能助手**（`ChatBot`）：

- 标题区：**智能助手**；**新对话**、**历史**（历史在顶栏与底栏快捷区可并存，以 Figma 为准）。  
- 消息区：用户/助手气泡与时间。  
- 输入区：**单行输入**与**展开多行**切换（如 Shift+Enter 换行、Enter 发送）；**发送**按钮。  
- 底部快捷按钮（图标+提示）：**智能提问**、**上传文件**、**语音输入**、**电话交流**、**历史问题** 等 — **以 Figma 为准**。  
- **§2.3** 规定安全与记忆；具体按钮是否接后端以分期实现为准，**布局与命名不改变 Figma 设计**。

**底部状态栏（StatusBar）**：

- 系统运行状态（如「系统就绪」）、**数据库连接状态**、**数据库最后全局计算并刷新时间**（与 **§2.2.2** 计算与预聚合任务一致）、待处理消息提示、在线状态、快捷设置入口等 — **字段与样式以 Figma 为准**。

**系统设定控制（内容范围）**：

- 系统设定控制在当前目标版本为实装页面，采用标签页方式承载：
  - **数据库文件维护**：维护 `data/` 目录下 `budget_{year}.db` 文件，展示年度库 `settings` 信息。
  - **数据库版本管理**：维护版本列表（含当前月份 `current_month`），支持新增/删除与继承。继承父版本时，按 `current_month` 仅迁移允许口径：`X` 月前迁实际、`X` 月及后迁预算；`X=1` 仅预算，`X=13` 仅实际。
  - **当前编辑版本与展示版本管理**：维护 `edit_show_version`，设置唯一编辑版本（`edit_show_sign=0`）与最多5个展示版本（`edit_show_sign=1..5`）。
- 该页面进入时需执行“文件系统与 `common.db.databases` 对齐检查”，发现增删变更需提示并同步。
- 密钥与凭据管理仍遵守 Rules **E.3**。

**Excel 导出**：

- 与在线计算**血缘一致**（Rules **E.6**，不一致为 P0）；**原则上**对公式与汇总结果导出**原生 Excel 公式**；**例外与边界**见 **§2.5**；技术见 **§3.2**。

### 2.2 核心业务与数据口径（对齐 Database PDD / Rules）

- **底层颗粒度**：`data_account`、`product_type`；`budget_data` **含** `product_code`（行级产品维），与「当前产品」及公式重算上下文一致（Database PDD）。
- **树与映射**：`report_account`、`dept_account`、`report_data_mapping`、`dept_product_mapping`；删 `data_account` 前公式引用校验（Rules **E.6**）。
- **期间**：`period` 含 **`quarter`**（`Q1`–`Q4`），初始化静态填充（Database PDD）。
- **预算填报视图 vs 物理行**：**预测结果明细台账**表格中的**报告科目层级**来自 **`report_account` + `report_data_mapping`** 等对数据科目的展开展示；**物理表 `budget_data`** 存储 **`data_acct_code`、`product_code`、`period_id`、`version_id`、`budget_actual`、`value`** 等，**不存报告树列**。界面切换**当前产品**时，展示 **「适用所有产品」** 或 **`product_code` 与该一致**的 `data_account`，以及对应 **`budget_data.product_code`** 的明细行。**预测预算工作台**则只维护预测行布局与绑定关系，不直接替代 `budget_data` 明细存储。
- **明细唯一性**：`budget_data` 联合唯一为 **`(data_acct_code, product_code, period_id, version_id, budget_actual)`**（Rules **E.1**）。**已删除**历史字段 **`data_type`**；**预算/实际**仅由 **`budget_actual`** 表达，并与 Figma「预算值/实际值」一致。
- **`DataAccount.value_type`（数值类型）**：与**数据科目维护**表中的「数值类型」列对应（金额/百分比/户数等），**不是**已废弃的 `budget_data.data_type`。
- **`budget_actual`**：与**预算基础数据录入**页的 **「预算值 / 实际值」** 开关对应：**`0`**=预算口径，**`1`**=实际口径。
- **`need_calc`**：引擎/后台标脏，**无 Figma 控件**；定时重算与「立即计算」消费该字段（Rules **E.1**）。
- **预算/实际月份窗口硬约束**：对任一版本，按 `current_month = X` 约束 `budget_data`：`X` 月前仅允许 `budget_actual=1`（实际），`X` 月及后仅允许 `budget_actual=0`（预算）；`X=1` 仅预算，`X=13` 仅实际。出现违规记录时，服务端需在版本创建继承与预算输入加载环节清理。
- **预聚合**：`budget_summary` 含 **`year`、`month`、`quarter`、`budget_actual`** 及展开列（**无** `data_type`）；大面查询读宽表（Rules **E.4**）。
- **`need_calc` 与重算（依赖传播）**：**字典或公式变更**后须走 `need_calc` 与重算链（Rules **E.1**）。任一 **`budget_data` 行**在**持久化**后若该版本内需参与引擎重算（含手工改值、导入、公式覆盖等），须将**该行** `need_calc` 置为需重算。**依赖链级联（MUST）**：在**同一 `version_id` 下**，凡因上述原因被标脏的行，**必须**按引擎可解析的**公式依赖图**（预算式、实际式及跨科目引用）**级联**将所有**直接或间接依赖**该行的 `budget_data` 行一并标为需重算，直至后台重算或「立即计算」完成并正确清零；**禁止**只标脏源行而遗漏下游公式行。依赖图解析边界（如跨版本、循环检测）以实现为准，且不得违背 Rules **E.1**。
- **精度**：存储与 **`DataAccount.value_type`**、舍入**仅在服务端**统一（Rules **E.1**）；**存储小数位数**以 **§2.2.1** 为准。**展示精度**由系统设置统一，**不得**反向污染存储值（Rules **E.1**）。
- **审计**：变更 `budget_data`、字典、映射、版本等须写入 **`common.db`** 的 **`operation_log`**（按 **`create_time`** 追加；**`action_desc` / JSON 快照**须可还原业务年度与 `version_id` 等），见 Database PDD **§1.9**；`target_table` 为物理表名（Rules **E.2**）。

#### 2.2.1 value_type 与存储小数位（Rules **E.1** 可查证锚点）

`DataAccount.value_type` 为枚举类展示名；**未在下表列出的取值**须在实现中定义小数位并纳入同一可查证配置，**新增或变更**时同步修订本表与 Rules **E.1** 审查。

| `value_type`（示例取值） | 存储小数位数 | 说明 |
|--------------------------|-------------|------|
| **金额** | **2** | 货币金额；写入 `budget_data` /引擎中间结果前按本表舍入。 |
| **百分比** | **4** | 比率类数值（内部以统一比例口径存储，如小数形式）；**界面「百分数」与存储的换算只在服务端做一次**，避免混用口径。 |
| **户数** | **0** | 户次、件数等非货币计数，存储为整数语义（无小数位）。 |

**舍入模式**：同一 `value_type` 内采用**四舍五入**或监管/财务规定的等价模式，须在服务端实现处单一实现、可审计；与上表不一致的特例**不得**静默生效，须先有文档与配置变更。

#### 2.2.2 计算与预聚合（摘要）

- **触发**：后台周期任务 + 用户显式触发。后台周期任务固定 **10 分钟**一轮，且仅在“至少 1 个有效登录会话”时执行；预算输入页采用「页面首次打开 / 页面离开 / 用户点击全局计算」触发刷新，**单元格逐次保存不触发即时全量公式重算**；完成后界面与库一致（Rules **E.4**）。
- **步骤**：更新 `budget_data` → 刷新 `budget_summary`；禁止用前端临时全表聚合替代宽表结论。
- **公式保存触发**：数据科目维护页在预算式/实际式保存成功后，须立即对对应口径触发重算；若目标科目为 `applies_to_all_products=1`，则按产品清单逐一执行同一公式（每个产品使用自身上下文数据）并回写 `budget_data`。
- **公式引用约束**：目标为 `applies_to_all_products=1` 的科目仅可引用同为 `applies_to_all_products=1` 的科目；目标为单产品科目时可引用全部数据科目，但计算读取仍限定在当前产品上下文。
- **跨年**：可多 `budget_{year}.db`；`period_id` 跨库有效性见 Database PDD「跨库逻辑引用」。
- **A/B 水位机制（MUST）**：
  - 年度库 `settings.global_refresh_time_a`（A）：该年度库“最近一次全局汇总刷新”时间；
  - Compare库 `settings.global_refresh_time_b`（B）：最近一次 compare 全量刷新完成时间；
  - 每轮后台任务先做公式重算，再判断 `MAX(budget_data.update_time)` 与 A；仅在数据晚于 A 时重建该年度 `budget_summary` 并更新 A；
  - 比较所有年度 A 与 B，若存在 `A > B`，则触发 compare 全量刷新并更新 B。
- **底栏时间展示口径（MUST）**：底栏“数据库最后全局计算并刷新时间”优先显示 B（compare 全局刷新时间），保证跨年度一致；B 不存在时回退到当前预算库 `budget_summary` 的最大 `update_time`。

### 2.3 智能体（Agent）与安全交互（对齐 Rules **E.3**）

#### 2.3.1 设计边界（宏观）

- Agent 采用 **LangGraph** 进行循环编排，支持**意图识别 → 口径判定 → 澄清追问 → 查询分析 → 用户反馈再迭代**的闭环交互。
- Agent 以预算系统底层数据库为分析基础，优先只读查询与解释；涉及写入或高风险动作时，遵循 Rules **E.3** 的确认与审计要求。
- Agent 对问题进行分流：**预算查询分析类**进入预算流程；**知识性/通用问答类**由大模型先直接回答，再附预算专长说明。
- Agent 同时具备**短期记忆**（本轮会话状态）与**长期记忆**（跨会话经验沉淀）的能力，但长期记忆不得覆盖 Rules 的强约束条款。
- Agent 输出包括：透视分析维度建议、查询结果解读、可视化联动（界面行为以 Figma 为准）；用户可通过“满意/不满意”反馈闭环持续优化。
- Agent 在体验上采用拟人化数字员工“管衡”形象；命名与话术原则在 Agent PDD 定义，System PDD 仅保留宏观能力约束。

#### 2.3.2 详细设计索引

- Agent 的状态机节点、状态字段、Prompt 分层、记忆模型、知识库目录、SQL 安全护栏、字段中文化映射、六按钮交互规格、评测方案与分期路线，统一见 [**Banking_Budget_Agent_PDD.md**](Banking_Budget_Agent_PDD.md)。

### 2.4 权限、用户与内网多用户范围（相对 Figma 的工程例外）

工程阶段划分与 **Rules「范围与演进」** 完全一致，摘要如下：

- **界面**：Figma 含 **「用户和权限管理」**、**「系统设定控制」** 等入口，导航与页面结构保持不变。  
- **当前目标版本（内网多用户）**：实现登录、首次登录改密、会话隔离与权限控制，`operation_log.user_id` 与 `ip_address` 绑定真实访问主体。  
- **角色与权限**：全权管理员拥有权限 1/2/3；数据录入用户拥有权限 1/2；数据浏览用户拥有权限 1。  
- **后续增强版本**：在同一信息架构上扩展审批流和更细粒度权限，不得违背 Rules 字段语义与 **E.2** 可追溯要求；升级前须同步修订 **Rules「范围与演进」** 与本节。

### 2.5 Excel 智能导出与公式血缘（产品惯例）

细化 **Rules E.6** 的验收惯例：

- **总则**：由公式引擎、层级/时间汇总得到的单元格，在**技术上可行时优先**写入 **Excel 原生公式**；「应保留血缘」区域**禁止**仅写与在线无关的死数。在线结果与导出后 Excel **重算结果**须一致，**否则 P0**。
- **范围**：数据科目公式、报告/部门层级汇总、**年/季/月**汇总（与 `quarter` 口径一致）、同表基础区与衍生区混排时的公式链。
- **树形**：优先 **Group & Outline** 对齐在线折叠体验。
- **边界**：超大规模若需「部分公式 + 部分值」折中，须**文档化范围**并经产品认可，且不得削弱核心血缘（Rules **E.6**）。
- **导入模板目录规范（MUST）**：所有“需模板导入”的页面，其模板文件统一放在工作目录根下 **`download_template/`**；前端“下载模板”按钮必须通过后端接口从该目录读取并下发，不得在前端硬编码模板内容。数据科目维护页使用模板标识 **`data_acct_temp`**（后缀由目录中的实际文件决定）。
- **预算输入导入交互规范（MUST）**：预测结果明细台账页采用「下载模板 → 上传预览 → 开始导入并下载结果文件」的弹窗式流程；模板文件为 **`download_template/budget_data_temp.xlsx`**。导入完成后必须返回并下载**在原上传文件上回写评估结果**的工作簿（含颜色与失败原因），避免仅在页面瞬时展示。

---

## 3. 技术路线与前端实现原则

### 3.1 前端（以 Figma 导出为基线）

与 **`src_from_Figma/`** 一致：**React**、**TypeScript**、**Tailwind CSS**、**react-resizable-panels**（可调整分栏）、**lucide-react**（图标）等；构建工具以导出工程为准（常见为 **Vite**）。可交付代码在 **`src/`**（Rules **E.7**）。纯本地、无 CDN（Rules **E.5** SHOULD）。

### 3.2 后端（概括）

FastAPI（或同等）+ 异步 SQLite；表名/字段以 Database PDD 为准；预聚合写入 `budget_summary`；Excel 使用可写公式与分组库（如 `openpyxl` / `XlsxWriter`）满足 Rules **E.6**。

### 3.3 Agent 技术栈（概括）

LangGraph + Deepseek（兼容 OpenAI 协议）；密钥仅环境变量（Rules **E.3**）；分析只读优先，写库走固定接口。

---

## 4. Figma 界面元素与持久化映射（审阅用）

本节将 **`src_from_Figma/`** 主要界面构件与 **Database PDD** 表字段做**对照**，并附 **SQLite** 建表示意（与 PDD 一致；**权威正文仍以 Database PDD 为准**）。主数据**编码样式**以 Database PDD 为准，**勿沿用**导出里过期的 mock 编号。各页映射与 SQL 阅毕后，**§4.8** 提供控件与字段的一行汇总，便于全文核对。

### 4.1 全局壳层

| Figma / 代码 | 含义 | 主要库表 / 字段 |
|--------------|------|-----------------|
| 顶栏 **软件版本** | 应用发布版本号 | 实现配置或静态资源，**非** `version` 表 |
| 顶栏 **预算年份** | 当前打开的编报年度 | 决定加载 **`budget_{year}.db`**；与 `Period.year`（`Y2026`）对应关系见 Database PDD |
| 顶栏 **预算版本号 / 名称** | 当前编报版本 | **`version.version_id`**、**`version.version_name`**（年度库内） |
| 顶栏 **用户 / 角色** | 展示用 | 来自登录会话；审计见 **`operation_log.user_id`**（`common.db`） |
| 底栏 **最后全局计算时间** | 预聚合完成时刻 | 与 **`budget_summary.update_time`** / 任务水位一致，以实现为准 |
| 底栏 **最后全局计算时间（显示口径）** | 全局刷新状态 | 优先显示 **`compare.settings['global_refresh_time_b']`**；缺失时回退 `MAX(budget_summary.update_time)` |
| 左侧导航 | 模块 IA | 无单独表；各叶子对应各维护页所读写的字典或 `budget_*` |

### 4.2 数据科目维护（`DataAccountContent`）

| 界面元素 | 持久化 |
|----------|--------|
| 科目代码 / 名称 | **`data_account.data_acct_code`**、**`data_acct_name`** |
| 预算式 / 实际式 | **`budget_formula`**、**`actual_formula`** |
| 公式编辑器左侧科目树（防错） | 当当前科目 `applies_to_all_products=1` 时，非“适用所有产品”科目灰显且不可拖拽/双击；保存时后端重复校验，禁止绕过前端规则 |
| 归属产品 / **适用所有产品科目** | **`product_code`** → **`product_type`**；**`applies_to_all_products`**（与单产品互斥，见 Database PDD **§1.1**） |
| **数值类型**（金额/百分比/户数） | **`value_type`**（与 §2.2.1 小数位表对应） |
| 备注 | **`remark`** |

### 4.3 报告 / 部门 / 产品科目维护

| 界面 | 主表 |
|------|------|
| 报告科目树、映射拖拽 | **`report_account`**、**`report_data_mapping`** |
| 部门科目树、产品挂载 | **`dept_account`**、**`dept_product_mapping`** |
| 产品科目表 | **`product_type`** |

> **部门-产品映射约束（最新口径）**  
> `dept_product_mapping` 为“部门叶子节点 → 产品”的一对多关系：一个部门叶子可挂接多个产品；同一产品在全表只能映射到一个部门叶子，禁止重复映射到多个部门。

> **强制一致性要求（基础数据维护四界面）**  
> 数据科目维护、报告科目维护、产品科目维护、部门科目维护四个工作界面的展示数据必须来自上述数据库表的实时查询结果；  
> 当底层表为空时，界面必须显示空状态，不得回退到前端内置样例数据（mock/demo）；  
> 界面新增/编辑/删除/映射操作必须通过后端 API 持久化并在刷新后可复现，确保 UI 与底层库的一致性（读写同源、刷新不漂移）。

### 4.4 预测预算工作台与预测结果明细台账（`ForecastWorkbenchContent` / `BudgetInputContent`）

| 界面元素 | 持久化说明 |
|----------|------------|
| 预测预算工作台-预测行布局 | 持久化 **`forecast_workbench_layout`**；保存预测行名称、分组、分类、展示顺序、绑定提示等。MVP 默认按 `工作簿1.xlsx` 的 **开鑫贷 / 小小账户** 主线预置 |
| 预测预算工作台-绑定关系 | 持久化 **`forecast_line_binding`**；支持绑定 **数据科目 / 假设参数 / 规则模板 / 报表科目**，用于将“参数与模板维护”“数据科目维护”集中映射到工作台预测行；允许在过渡期存在 `manual_anchor` 类型占位绑定 |
| **预算值 / 实际值** 切换 | 写入/查询 **`budget_data.budget_actual`**：`0` / `1` |
| 当前产品选择 | 筛选 **`data_account`**（`product_code` 匹配 **或** `applies_to_all_products=1`）；写入/更新明细时带 **`budget_data.product_code`**（与当前产品一致） |
| 报告科目 / 数据科目列 | **视图**：由映射与字典 JOIN 得到；**库内无**「报告列」 |
| 1–12 月列 | 对应 **`period_id`**（`common.db` **`period`**），每月一行 **`budget_data`**（同 `data_acct_code`、`product_code`、`version_id`、`budget_actual`） |
| **全局计算并刷新** | 引擎重算 +刷新 **`budget_summary`**；更新 **`need_calc`** |

### 4.5 多维分析与图表

| 界面 | 数据源 |
|------|--------|
| 数据透视表-当前年度多版本透视 | 读当前编辑年度库 **`budget_summary`** |
| 数据透视表-多年度对比透视 | 读 **`compare.db.compare_budget_summary`** |
| 多年度数据透视图 | 以上两类透视结果的可视化消费（按页面上下文选源） |
| 图表模板（若有） | **`chart_template.config_json`** 等 |

### 4.6 审计日志

所有 **Rules E.2** 覆盖的写路径 → 插入 **`common.db`** **`operation_log`**；**`target_table`** 为 snake_case 表名；快照中须含**业务年度**与 **`version_id`**（若适用）。

### 4.7 SQL 建表示意（SQLite）

以下为**节选**，列名与类型与 Database PDD 对齐，便于审阅；迁移时以 PDD 全文为准。

**`common.db`**

```sql
CREATE TABLE product_type (
  product_code TEXT PRIMARY KEY NOT NULL,
  product_name TEXT NOT NULL,
  remark TEXT
);

CREATE TABLE data_account (
  data_acct_code TEXT PRIMARY KEY NOT NULL,
  data_acct_name TEXT NOT NULL,
  product_code TEXT REFERENCES product_type(product_code),
  applies_to_all_products INTEGER NOT NULL DEFAULT 0 CHECK (applies_to_all_products IN (0, 1)),
  budget_formula TEXT,
  actual_formula TEXT,
  value_type TEXT NOT NULL,
  remark TEXT,
  CHECK (
    (applies_to_all_products = 1 AND product_code IS NULL)
    OR (applies_to_all_products = 0 AND product_code IS NOT NULL)
  )
);

CREATE TABLE period (
  period_id INTEGER PRIMARY KEY AUTOINCREMENT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  year_month TEXT NOT NULL UNIQUE,
  days INTEGER NOT NULL
);

CREATE TABLE operation_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  action_type TEXT NOT NULL,
  action_desc TEXT NOT NULL,
  target_table TEXT,
  affected_rows INTEGER,
  before_data TEXT,
  after_data TEXT,
  ip_address TEXT,
  create_time TEXT
);
-- 其余字典表见 Database PDD §1
```

**`budget_{year}.db`（示例年度库）**

```sql
CREATE TABLE version (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_date_time TEXT NOT NULL,
  version_name TEXT NOT NULL,
  current_month INTEGER NOT NULL
);

CREATE TABLE budget_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data_acct_code TEXT NOT NULL,
  product_code TEXT NOT NULL,
  period_id INTEGER NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  value REAL NOT NULL DEFAULT 0,
  need_calc INTEGER NOT NULL DEFAULT 1,
  create_time TEXT,
  update_time TEXT,
  UNIQUE (data_acct_code, product_code, period_id, version_id, budget_actual)
);

CREATE TABLE budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_level1 TEXT, report_level2 TEXT, report_level3 TEXT, report_level4 TEXT, report_level5 TEXT,
  dept_level1 TEXT, dept_level2 TEXT, dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL, month TEXT NOT NULL, quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL,
  version_id INTEGER NOT NULL REFERENCES version(version_id),
  version_name TEXT,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  update_time TEXT
);
-- 宽表其余约定见 Database PDD §2.4
```

**跨库引用**：`budget_data` 对 `data_account`、`period`、`product_type`（经 `product_code`）为**逻辑引用**（应用层或 `ATTACH`），见 Database PDD「跨库逻辑引用与 SQLite 限制」。

**`compare.db`（多年度对比透视只读库）**

```sql
CREATE TABLE compare_budget_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  show_level INTEGER NOT NULL,
  data_file_id INTEGER NOT NULL,
  source_year INTEGER NOT NULL,
  source_version_id INTEGER NOT NULL,
  source_version_name TEXT,
  report_level1 TEXT, report_level2 TEXT, report_level3 TEXT, report_level4 TEXT, report_level5 TEXT,
  dept_level1 TEXT, dept_level2 TEXT, dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL, month TEXT NOT NULL, quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  sync_time TEXT NOT NULL
);
```

### 4.8 界面控件与持久化字段速查（汇总）

| 用户可见控件 / 概念 | 数据库位置 | 备注 |
|---------------------|------------|------|
| **数据科目维护** — **数值类型** | `data_account.value_type` | 与 **§2.2.1** 小数位表联动；**无** `budget_data` 侧「数据类型」列 |
| **预测结果明细台账** — **预算值 / 实际值** | `budget_data.budget_actual`（预聚合行见 `budget_summary.budget_actual`） | **`0`** = 预算口径，**`1`** = 实际口径 |
| （无直接控件） | `budget_data.need_calc` | 引擎/任务标脏，见 **§2.2**；**不**出现在 Figma 表单列中 |
