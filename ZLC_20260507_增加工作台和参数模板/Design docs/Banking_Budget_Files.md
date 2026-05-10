# Banking Budget 项目文件总览

本文用于快速理解本工作区的目录结构、关键文件职责和模块调用关系。  
目标是：**看一遍就能知道项目架构与实现思路**。

> 说明：为保证可读性，本文聚焦“项目自有文件（first-party）”。`node_modules/`、`dist/`、`backend/.venv/` 属于依赖/构建产物，不逐文件解释。

---

## 0. 本轮更新摘要（2026-05-07）— ZLC

- `backend/app/routers/forecast_workbench.py`：[接口][界面] 新增预测预算工作台概览接口，汇总预测行、绑定关系、参数模板与版本上下文。
- `backend/app/init_db.py`：[数据] 新增 `forecast_workbench_layout`、`forecast_line_binding` 两张工作台配置表，并补充开鑫贷/小小账户模板种子与关键参数默认项。
- `backend/app/schemas.py`：[接口] 新增预测预算工作台概览、预测行、绑定关系等返回模型。
- `backend/app/main.py`：[接口] 注册预测预算工作台路由并补充接口权限控制。
- `src/lib/api.ts`：[接口][界面] 新增预测预算工作台 DTO，供前端页面读取概览与绑定信息。
- `src/app/components/ForecastWorkbenchContent.tsx`：[界面] 新增预测预算工作台页面，展示模板分组、绑定概览与右侧预测行绑定明细。
- `src/app/components/NavigationTree.tsx`：[界面] 在“预算数据输入”下新增“预测预算工作台”入口，并将原“预算基础数据维护”重命名为“预测结果明细台账”。
- `src/app/components/WorkArea.tsx`：[界面] 挂载预测预算工作台页面，并同步欢迎区与预算输入说明文案。
- `Design docs/Banking_Budget_System_PDD.md`：[PDD] 同步预算输入模块拆分、工作台持久化表与工作簿1模板预置说明。

---

## 0. 本轮更新摘要（2026-05-06）— ZLC

- `backend/app/init_db.py`：[数据] 为 `data_account` 增加 `product_codes` 兼容迁移，支撑数据科目“多产品 / 全部产品 / 公司级”范围表达。
- `backend/app/schemas.py`：[接口][数据] 扩展数据科目与产品科目模型，新增 `product_codes`、`parent_code`、`level` 等字段与导入统计结构。
- `backend/app/main.py`：[接口][数据] 调整数据科目产品范围读取与预算汇总侧兼容逻辑，适配新的产品范围表达。
- `backend/app/routers/data_accounts.py`：[接口][数据] 改造数据科目查询、新增、修改、导出与导入接口，支持多产品绑定及产品范围迁移预览/执行。
- `backend/app/budget_input_import.py`：[接口][数据] 调整预算导入主数据校验与写入逻辑，区分新增/覆盖结果并兼容新的产品范围字段。
- `backend/app/routers/report_catalog.py`：[接口][数据] 将产品科目维护与导入改为支持 `parent_code + level` 的多层结构，并提供覆盖/新增两种导入模式。
- `src/lib/api.ts`：[接口][界面] 同步前端 DTO，补充 `product_codes`、`parent_code`、`level` 等字段供页面联动。
- `src/app/components/DataProductContent.tsx`：[界面] 产品科目维护页升级为多层结构编辑，并新增导入模式切换。
- `src/app/components/ProductMultiSelectDialog.tsx`：[界面] 新增分层多选产品弹窗，支持父级展开到叶子、全部产品选择与多产品回显。
- `src/app/components/DataAccountContent.tsx`：[界面] 数据科目维护页改造为支持“多产品 / 全部产品 / 未分配”范围选择，并联动后端 `product_codes`。
- `src/app/components/ExcelUploadDialog.tsx`：[界面] 通用 Excel 导入弹窗新增“新增/更新”与“覆盖”模式、导入统计与结果提示。
- `src/app/components/BudgetInputExcelUploadDialog.tsx`：[界面] 预算基础数据导入结果补充新增/覆盖/失败统计与颜色说明，修复上传反馈体验。

---

## 0. 本轮更新摘要（2026-04-28）

- `backend/app/agent_graph.py`：移除确认正文中的“透视建议：...”追加逻辑，透视说明改由前端卡片统一展示。
- `backend/app/agent_product_intent.py`：锁定维度区块改为紧凑排版，移除多余空行与结尾重复提示语。
- `src/app/components/PivotTableContent.tsx`：多年度对比透视不再清空 `pivot_search_text`，锁定科目 code 可在搜索框保留。
- `src/app/components/NavigationTree.tsx`：导航“数据透视图”更名为“多年度数据透视图”；“智能分析报告”“智能演示PPT”置灰但保持可点击。

---

## 1. 全局架构（先看这个）

### 1.1 前后端关系

- 前端：`src/`（React + Vite + TypeScript + Tailwind）
- 后端：`backend/app/`（FastAPI + LangGraph + SQLite）
- 知识库：`knowledge_base/`（语义、指标、同义词、记忆、模板 + generated 配置）

### 1.2 主要调用链

1. 用户在 `ChatBot.tsx` 提问  
2. 前端调用 `POST /api/agent/chat`（`src/lib/api.ts`）  
3. 后端 `backend/app/main.py` -> `AgentGraphService.chat()`（`agent_graph.py`）  
4. Agent 根据意图：澄清 / 规划 / SQL 执行 / 透视建议  
5. 返回 `reply`、`reply_options`、`result_preview`、`pivot_suggestion` 等  
6. 前端渲染消息，必要时打开并配置当前年度透视页或多年度对比透视页

### 1.3 运行配置

- 前端开发服务与代理：`vite.config.ts`（`/api` 代理到 `127.0.0.1:8000`）
- 后端运行参数：`backend/app/config.py`（预算年、会话/跨域、DeepSeek、data 目录）
- Agent 阈值与策略：`knowledge_base/generated/agent_runtime_config.json`

---

## 2. 顶层目录与文件

### 2.1 设计文档（PDD）

- `Banking_Budget_Agent_PDD.md`：Agent 设计与需求基线（含双透视协同）
- `Banking_Budget_System_PDD.md`：系统级设计说明
- `Banking_Budget_Rules_PDD.md`：业务规则与约束
- `Banking_Budget_Database_PDD.md`：数据库设计说明
- `Banking_Budget_Database_ERD.md`：数据库 ERD 文档
- `Banking_Budget_multi_user.md`：内网多用户改造路线

### 2.2 前端工程配置

- `package.json`：前端脚本与依赖（`dev/build/preview`）
- `package-lock.json`：依赖锁定
- `vite.config.ts`：Vite 配置、`@` 别名、`/api` 代理
- `tsconfig.json`、`tsconfig.node.json`：TypeScript 配置
- `tailwind.config.cjs`：Tailwind 配置
- `postcss.config.cjs`：PostCSS 配置
- `index.html`：前端入口 HTML
- `.gitignore`：Git 忽略规则

### 2.3 主要目录

- `src/`：当前生效的前端代码
- `backend/`：后端 API 与 Agent 逻辑
- `knowledge_base/`：知识库与生成配置
- `src_from_Figma/`：Figma 导出参考代码（平行参考）
- `data/`：运行时 SQLite 数据目录（默认）

---

## 3. backend/ 目录说明

### 3.1 backend 根目录

- `backend/requirements.txt`：后端 Python 依赖
- `backend/.env`：本地环境变量（如 DeepSeek Key）
- `backend/scripts/build_knowledge_base.py`：构建知识库 generated 文件

### 3.2 backend/app 核心文件

- `backend/app/main.py`  
  FastAPI 入口，定义路由与接口编排（chat、feedback、file parse、数据接口等）。

- `backend/app/schemas.py`  
  Pydantic 请求/响应模型，包括 `AgentChatResponse`、`pivot_suggestion` 等结构。

- `backend/app/agent_graph.py`  
  Agent 核心逻辑：意图识别、澄清、SQL 规划执行、回复选项、透视建议、记忆写入。

- `backend/app/agent_query.py`  
  只读 SQL 执行器与安全护栏。

- `backend/app/agent_memory.py`  
  对话记忆写入与反馈更新。

- `backend/app/knowledge_base.py`  
  知识库加载与检索服务。

- `backend/app/deepseek_client.py`  
  DeepSeek 调用封装（超时、重试）。

- `backend/app/init_db.py`  
  SQLite 初始化与建表逻辑。

- `backend/app/db_paths.py`  
  数据库文件路径解析（`common.db`、`budget_{year}.db`、`compare.db`）。

- `backend/app/config.py`  
  后端配置（`data_dir`、预算年、用户、CORS、模型配置）。

- `backend/app/audit.py`  
  操作审计日志写入。

- `backend/app/formula_refs.py`  
  公式参考内容。

- `backend/app/budget_input_import.py`  
  预算基础数据 Excel 导入核心逻辑（模板解析、月份窗口与主数据校验、公式锁定拦截、导入评估结果结构）。

- `backend/app/__init__.py`  
  Python 包标识文件。

---

## 4. src/ 前端目录说明

### 4.1 入口与全局

- `src/main.tsx`：React 挂载入口
- `src/vite-env.d.ts`：Vite 类型声明
- `src/lib/api.ts`：统一 API 调用与 DTO 类型定义
- `src/styles/index.css`：全局样式入口
- `src/styles/tailwind.css`：Tailwind 样式入口
- `src/styles/theme.css`：主题样式
- `src/styles/fonts.css`：字体定义

### 4.2 应用骨架（src/app）

- `src/app/App.tsx`：三栏布局、标签页管理、聊天面板、透视表打开入口

### 4.3 业务组件（src/app/components）

- `Header.tsx`：顶部系统信息栏
- `StatusBar.tsx`：底部状态栏
- `NavigationTree.tsx`：左侧导航树
- `WorkArea.tsx`：中间工作区容器
- `TabViews.tsx`：标签页视图映射
- `treeEditRules.ts`：树编辑规则定义

- `ChatBot.tsx`：智能体聊天 UI（历史、语音、上传、选项按钮、透视联动）
- `PivotTableContent.tsx`：当前年度多版本透视页（字段拖拽、筛选、持久化、Agent 建议应用）
- `PivotChartContent.tsx`：多年度数据透视图页面（柱状/折线/饼图等）

- `BudgetInputContent.tsx`：预算录入页面
- `BudgetInputExcelUploadDialog.tsx`：预算录入专用 Excel 导入弹窗（下载模板、上传预览、导入并下载评估结果文件）
- `DataAccountContent.tsx`：数据科目维护
- `DataDepartmentContent.tsx`：部门维度维护
- `DataProductContent.tsx`：产品维度维护
- `DataReportContent.tsx`：报表维度与关系维护

- `AnalysisReportContent.tsx`：分析报告页
- `AnalysisPPTContent.tsx`：分析演示页

- `ExcelUploadDialog.tsx`：Excel 上传弹窗
- `FormulaEditorDialog.tsx`：公式编辑弹窗
- `ProductSelectorDialog.tsx`：产品选择弹窗

- `figma/ImageWithFallback.tsx`：图片降级组件

### 4.4 通用 UI 组件库（src/app/components/ui）

这组是项目内的通用 UI primitive（按钮、弹窗、表格、表单等），用于统一交互和样式。  
完整文件列表：

- `accordion.tsx`
- `alert-dialog.tsx`
- `alert.tsx`
- `aspect-ratio.tsx`
- `avatar.tsx`
- `badge.tsx`
- `breadcrumb.tsx`
- `button.tsx`
- `calendar.tsx`
- `card.tsx`
- `carousel.tsx`
- `chart.tsx`
- `checkbox.tsx`
- `collapsible.tsx`
- `command.tsx`
- `context-menu.tsx`
- `dialog.tsx`
- `drawer.tsx`
- `dropdown-menu.tsx`
- `form.tsx`
- `hover-card.tsx`
- `input-otp.tsx`
- `input.tsx`
- `label.tsx`
- `menubar.tsx`
- `navigation-menu.tsx`
- `pagination.tsx`
- `popover.tsx`
- `progress.tsx`
- `radio-group.tsx`
- `resizable.tsx`
- `scroll-area.tsx`
- `select.tsx`
- `separator.tsx`
- `sheet.tsx`
- `sidebar.tsx`
- `skeleton.tsx`
- `slider.tsx`
- `sonner.tsx`
- `switch.tsx`
- `table.tsx`
- `tabs.tsx`
- `textarea.tsx`
- `toggle-group.tsx`
- `toggle.tsx`
- `tooltip.tsx`
- `use-mobile.ts`
- `utils.ts`

---

## 5. knowledge_base/ 目录说明

### 5.1 顶层

- `knowledge_base/README.md`：知识库总说明
- `knowledge_base/API_QUICKSTART.md`：API 快速说明

### 5.2 01_data_semantics（语义层）

- `01_data_semantics/README.md`
- `01_data_semantics/data_dictionary_seed.csv`
- `01_data_semantics/data_dictionary_template.csv`
- `01_data_semantics/dimension_mapping_template.json`
- `01_data_semantics/field_table_name_mapping_zh.json`
- `01_data_semantics/version_seed.csv`
- `01_data_semantics/period_seed.csv`
- `01_data_semantics/dept_product_mapping_seed.csv`
- `01_data_semantics/report_data_mapping_seed.csv`

作用：定义字段语义、中文映射、维度关系，是 SQL 中文化和意图理解基础。

### 5.3 02_metric_definitions（指标口径）

- `02_metric_definitions/README.md`
- `02_metric_definitions/metric_catalog_seed.yaml`
- `02_metric_definitions/metric_catalog_template.yaml`

作用：定义同比/环比/预实等指标口径和计算语义。

### 5.4 03_conversation_memory（经验记忆）

- `03_conversation_memory/README.md`
- `03_conversation_memory/conversation_memory_schema.json`
- `03_conversation_memory/memory_record_seed.jsonl`
- `03_conversation_memory/memory_record_template.jsonl`
- `03_conversation_memory/memory_runtime.jsonl`

作用：沉淀历史对话经验、反馈与运行记忆。

### 5.5 04_term_synonyms（术语同义词）

- `04_term_synonyms/README.md`
- `04_term_synonyms/synonyms_seed.csv`
- `04_term_synonyms/synonyms_template.csv`

作用：银行预算术语归一（口语 -> 规范词），提升意图召回。

### 5.6 05_analysis_templates（分析模板）

- `05_analysis_templates/README.md`
- `05_analysis_templates/analysis_template_library.md`

作用：分析表达模板与报告风格约束。

### 5.7 generated（运行生成与配置）

- `generated/README.md`
- `generated/kb_build_report.json`
- `generated/intent_router_config.json`
- `generated/intent_router_trace.jsonl`
- `generated/agent_runtime_config.json`

作用：构建产物 + Agent 可调配置 + 路由可观测 trace。

---

## 6. src_from_Figma/（参考代码）

该目录用于保存 Figma 导出的参考实现，不是当前主运行入口。  
主要包含：

- `src_from_Figma/app/App.tsx`
- `src_from_Figma/app/components/*`（Header、WorkArea、ChatBot、导航、弹窗等）
- `src_from_Figma/app/components/ui/*`（48 个通用 UI 文件）
- `src_from_Figma/app/components/figma/ImageWithFallback.tsx`
- `src_from_Figma/styles/index.css`
- `src_from_Figma/styles/tailwind.css`
- `src_from_Figma/styles/theme.css`

建议：新开发以 `src/` 为准，`src_from_Figma/` 仅作对照或迁移参考。

---

## 7. 核心实现逻辑（快速理解）

### 7.1 Agent 核心

- 意图识别：规则 + 语义检索 + LLM 仲裁（可配置）
- 查询流程：澄清槽位 -> 规划 SQL -> 确认执行 -> 结果分析
- 透视协同：可返回 `reply_options`（SQL / 透视表 / 两者）与 `pivot_suggestion`
- 确认文案优化：锁定维度块紧凑展示；透视解释只在“管衡推荐透视视角”卡片出现一次
- 可观测性：意图 trace 输出到 `intent_router_trace.jsonl`

### 7.2 聊天与透视联动

- 聊天消息支持操作按钮；
- 打开透视表（当前年度或多年度对比）时可带建议字段配置；
- 多年度对比透视应用建议时保留搜索框预填 code（`pivot_search_text`）；
- 透视页监听事件并应用行/列/页/值与筛选；
- 配置会写入本地存储，跨页面切换可保留。

### 7.3 会话与历史

- 聊天会话持久化（折叠展开不丢）；
- 历史会话支持首次/最后时间与恢复继续。

---

## 8. 建议阅读顺序（10分钟上手）

1. `Banking_Budget_Agent_PDD.md`（需求与目标）
2. `src/app/App.tsx`（前端总装配）
3. `src/app/components/ChatBot.tsx`（交互主入口）
4. `backend/app/main.py`（API 路由）
5. `backend/app/agent_graph.py`（Agent 核心逻辑）
6. `src/app/components/PivotTableContent.tsx`（当前年度透视实现；多年度对比透视同模式扩展）
7. `knowledge_base/generated/agent_runtime_config.json`（阈值调优入口）

---

## 9. 维护原则

- 新增功能优先补充到 `Agent PDD` + 本文，再落代码。
- 所有判定阈值优先收敛到 `agent_runtime_config.json`，避免散落硬编码。
- 业务词汇先更新 `synonyms_seed.csv`，再验证意图 trace。
- 结构性调整完成后，更新本文对应章节，保持可交接性。
