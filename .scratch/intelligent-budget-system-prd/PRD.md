Status: ready-for-agent

# PRD: 智能预算管理系统整体建设

| 项目 | 说明 |
| --- | --- |
| 文档版本 | v1.0 |
| 编制日期 | 2026-06-13 |
| 文档定位 | 作为智能预算管理系统的项目级 PRD，承接会议纪要、口述需求、新增需求规格说明书、现有 PDD 和当前代码仓库事实 |
| 适用范围 | 财务预算管理条线、业务产品部门、部门费用预算管理、信息技术部 |
| 当前代码边界 | 当前前端入口为 `apps/web`，后端入口为 `apps/api`；本文不恢复旧入口、旧表和旧工作台 |

## Problem Statement

当前预算系统已经形成较多功能模块，包括机构及产品、机构及产品指标、机构及产品数据录入、预算展示报表、部门费用预测、费用预算执行报表、多维分析、智能报告、智能 PPT、模拟测算和智能预算模拟等能力。但从业务使用和项目汇报角度看，系统仍存在几个核心问题：

1. 功能入口较多，预算管理和部门费用预算管理的边界需要进一步讲清楚。
2. 指标体系是系统核心，但业务上容易把“机构及产品”“机构及产品指标”“运行引用”“展示表”“预算事实”混在一起理解。
3. 当前数据来源以 Excel 为主，预算底稿、业务报送、管会下载报表、BI 报表等来源不同，缺少一个清晰的数据接入和沉淀说明。
4. 前端展示和报表结构仍存在混乱感，展示表、取数口径、分类行、指标行、导出结构之间的关系需要重新定义。
5. AI 功能已经出现在智能报告、智能 PPT、Agent、智能预算模拟等模块，但必须建立在稳定数据底座和指标口径之上，不能把 AI 放在基础流程之前。
6. 现有需求材料有的偏口述，有的偏理想化，有的偏技术 PDD，缺少一份可以作为项目整体建设依据的 PRD。

本 PRD 的目标不是从零重写系统，而是在当前代码仓库和当前 PDD 基础上，补写一份业务可读、技术可落地、后续可拆 issue 的项目级产品需求文档。

## Solution

建设一套以“机构及产品指标体系”为核心底座的智能预算管理系统。

系统整体分为两条业务主线和两类支撑能力：

1. **经营预算主线**
   - 围绕机构、产品、指标、预算/实际/预测数据、预算展示报表、模拟测算和智能分析形成闭环。

2. **部门费用预算主线**
   - 围绕部门科目、部门预算科目、BI 映射、费用执行明细导入、部门费用预测、费用预算执行报表和投入产出专题形成闭环。

3. **数据与指标底座**
   - 统一承接 Excel、业务报送、管会下载报表、BI 报表等外部数据。
   - 通过机构及产品表、机构及产品指标表、预算事实表、费用私有表和汇总读模型，形成可计算、可汇总、可追溯的数据资产。

4. **智能分析与汇报输出**
   - 在数据和指标稳定后，提供 Agent 查询、智能分析报告、智能演示 PPT、智能预算模拟等能力。
   - AI 负责解释、分析、方案生成辅助和汇报草稿，不直接绕过确认流程写入正式预算事实。

系统建设应采用分阶段方式推进：

1. 第一阶段：梳理业务流程、数据流和指标体系，稳定 Excel 数据接入、指标定位、预算事实沉淀和基础报表输出。
2. 第二阶段：统一前端展示、报表结构、导入流程和跑批刷新机制，提升可用性和可追溯性。
3. 第三阶段：增强智能报告、智能 PPT、Agent 分析和智能预算模拟能力。
4. 第四阶段：探索管会系统等标准化数据源对接，但该能力不作为第一阶段强依赖。

## Current System Alignment

本 PRD 必须与当前代码仓库事实保持一致。

### 当前已存在的业务入口

当前前端工作台已经包含以下模块：

1. **预算管理**
   - 规则配置台：机构及产品、机构及产品指标。
   - 预算数据输入：机构及产品数据录入、机构及产品预测输出。
   - 预算输出报表展示：预算展示报表。
   - 模拟测算模块：模拟测算（正算）、模拟测算（倒算）、智能预算模拟。

2. **部门费用预算管理模块**
   - 部门科目维护。
   - 部门预算科目维护。
   - BI 映射维护。
   - 预算录入。
   - 费用执行明细导入。
   - 费用预测逻辑配置。
   - 部门费用预测。
   - 费用预算执行报表。
   - 业务支出成本收入比实际导入。
   - 业务支出成本收入比维护。
   - 投入产出专题概览。

3. **多维分析工具**
   - 当前可编辑年度多版本透视报表。
   - 多年度对比透视报表。
   - 多年度数据透视图。
   - 智能分析报告。
   - 智能演示 PPT。

4. **系统配置中心**
   - 用户和权限管理。
   - 系统设定控制。
   - 数据同步管理。
   - 预算事实刷新跑批。
   - Agent 对话测试。

### 当前必须遵守的核心口径

1. **机构及产品指标体系是唯一主指标体系**
   - 机构及产品指标是预算指标、公式和录入口径的唯一配置入口。
   - `data_account`、`data_account_metric_node`、`data_account_metric_binding` 只作为运行引用和事实写入合同，不再作为第二套指标配置入口。

2. **机构及产品数据录入是唯一用户侧预算事实录入口**
   - 已确认的机构产品指标单元格通过预算同步服务解析绑定。
   - 正式写入年度预算事实时必须通过 BudgetDataWriter。
   - 不恢复旧预算录入页面、旧 `/api/budget-input/*` 或旧预算 Excel 导入链路。

3. **预算展示表只负责展示结构**
   - 预算展示表不重新定义指标体系。
   - 分类展示行只用于报表层级和分组。
   - 指标取数行必须绑定正式指标或运行引用。
   - 删除展示行不应误删底层指标或预算事实。

4. **部门费用是独立业务闭环**
   - 费用执行明细通过费用执行明细导入进入系统。
   - BI 映射维护是费用实际数据进入费用预算执行报表和部门费用预测的关键前置。
   - 费用预测规则、费用预测表、费用预算执行报表使用费用私有表和费用读模型，不应混成经营预算主数据。

5. **AI 能力必须建立在正式数据和正式口径之上**
   - Agent、智能报告、智能 PPT、智能预算模拟读取当前预算汇总、对比读模型、机构及产品指标体系和预算事实。
   - AI 不直接修改正式预算事实。
   - 涉及写入、放宽约束、形成正式报告或预算版本时，需要用户确认。

## Goals

1. 明确系统作为智能预算管理系统的整体业务框架。
2. 明确经营预算和部门费用预算两条主线的功能边界。
3. 明确数据来源、数据接入、数据存储、预算事实和报表输出的完整链路。
4. 明确机构及产品表、机构及产品指标表、运行引用、预算事实和展示表之间的关系。
5. 明确 Excel 当前接入、标准报表导入、未来系统对接的阶段路线。
6. 明确前端展示治理方向，减少页面和表格混乱。
7. 明确 AI 能力的建设阶段、应用边界和确认机制。
8. 为后续拆分开发 issue、测试验收和领导汇报提供项目级依据。

## Non-Goals

1. 不恢复旧产品预算工作台。
2. 不恢复旧 `report_account` / `report_data_mapping`。
3. 不恢复旧 `driver_*` 表或旧预测工作台。
4. 不建立第二套指标配置体系。
5. 不建立第二套预算事实写入入口。
6. 不让 AI 直接绕过规则、权限和确认流程写入正式预算数据。
7. 不把管会系统直连作为第一阶段必须完成内容。
8. 不把 UI 做成 BI 大屏、宣传页或卡片堆叠式驾驶舱。

## Users And Roles

1. **预算管理人员**
   - 维护机构及产品、指标、公式、预算版本。
   - 导入或录入预算、实际、预测数据。
   - 查看预算展示报表、透视分析和智能报告。

2. **业务产品部门**
   - 提供业务报送报表和预算底稿。
   - 维护或确认产品相关预算数据。
   - 查看产品维度预算结果、预测输出和模拟测算方案。

3. **部门费用管理人员**
   - 维护部门科目、部门预算科目和 BI 映射。
   - 导入费用执行明细。
   - 编制部门费用预测并查看费用预算执行报表。

4. **管理层和汇报使用者**
   - 查看固定报表、灵活查询、智能报告、智能 PPT。
   - 使用智能预算模拟查看多套经营方案。

5. **系统管理员**
   - 管理用户、权限、年度库、版本、系统配置和数据同步。
   - 负责数据安全、审计和运行状态监控。

6. **开发和测试人员**
   - 根据 PRD、PDD、数据库设计和当前代码边界进行增量开发。
   - 验证外部行为、数据链路、报表一致性和权限审计。

## Data Sources

### 当前阶段数据来源

当前阶段系统主要承接 Excel 文件。原因是预算底稿、业务报送和部分外部报表仍以表格方式流转，短期内难以全部改造成系统接口。

1. **预算底稿**
   - 来自预算编制过程中的线下工作材料。
   - 通过 Excel 上传进入系统。
   - 系统根据机构、产品、指标、期间、版本进行识别和导入。

2. **业务报送报表**
   - 当前仍主要以 Excel 形式提交。
   - 短期内无法快速改造成系统化报送。
   - 系统需要支持模板识别、指标匹配、异常提示和导入追溯。

3. **管会等 P0301 报表**
   - 当前可先通过管会系统下载标准报表，再以文件方式导入。
   - 后续可建立固定解析规则和指标映射关系。
   - 管会系统直接对接存在跨环境审批、数据安全和合规难度，应作为后续阶段推进。

4. **BI 系统报表**
   - 主要服务部门费用预算管理模块。
   - 用于费用执行明细、部门预算初始化、费用实际数等场景。
   - 进入系统后需要通过 BI 映射维护转换为系统内预算科目和部门口径。

### 后续阶段数据来源

1. 管会系统标准报表下载导入。
2. 管会系统接口或数据同步。
3. BI 系统固定报表导入。
4. 其他财务、绩效、业务系统数据源。

后续系统对接必须先明确跨系统审批、数据权限、字段口径、数据频率、同步方式和审计要求。

## Data Intake And Storage Flow

系统的数据接入不应停留在“保存 Excel 附件”。外部数据进入系统后，需要转换为可计算、可汇总、可追溯的系统数据。

### 通用数据接入流程

```text
外部 Excel / 标准报表
  -> 文件上传
  -> 文件类型识别
  -> 表头和模板解析
  -> 机构/产品/部门/科目/指标匹配
  -> 数据校验和异常提示
  -> 用户预览和确认
  -> 写入原始导入记录或业务私有表
  -> 形成预算事实、费用事实或业务读模型
  -> 报表展示 / 透视分析 / 智能分析
```

### 数据分层

1. **原始文件层**
   - 保存上传文件、来源类型、上传人、上传时间和文件版本。
   - 用于追溯数据来源。

2. **导入批次层**
   - 每次上传形成导入批次。
   - 记录成功行、失败行、未匹配行、异常原因和处理状态。

3. **映射匹配层**
   - 根据系统主数据匹配机构、产品、指标、部门、预算科目、BI 科目。
   - 对未匹配内容进行提示，不允许静默入库。

4. **业务事实层**
   - 经营预算事实进入年度库预算事实表。
   - 部门费用执行明细进入费用执行明细 Adapter。
   - 费用预测、成本收入比、投入产出专题等使用各自私有表。

5. **汇总读模型层**
   - 基于正式事实生成预算汇总、预算透视、多年度对比、费用预算执行报表等读模型。
   - 报表、导出和智能分析应读取同一套结果口径。

## Metric System Requirements

### 机构及产品表

机构及产品表用于维护预算管理对象，回答“预算数据属于哪个机构、哪个产品、哪个业务单元”。

主要要求：

1. 支持机构、产品、业务单元的层级维护。
2. 支持新增、修改、停用和层级调整。
3. 支持作为预算录入、指标配置、报表展示和多维分析的对象范围。
4. 支持后续权限、版本和数据归属控制。
5. 产品名称和层级应作为系统唯一产品主数据来源，不恢复旧产品科目维护入口。

### 机构及产品指标表

机构及产品指标表用于维护各机构或产品下的预算指标，回答“这个对象下看哪些指标、指标如何计算、汇总和展示”。

主要要求：

1. 支持按机构或产品维护指标清单。
2. 支持指标名称、指标编码、指标层级、展示顺序、数值类型、启停状态。
3. 支持预算公式、实际公式、预测口径和汇总规则。
4. 支持共性指标复用和个性化指标保留。
5. 支持 Excel 导入时的指标匹配。
6. 支持预算事实写入时的指标定位。
7. 支持预算展示报表、智能报告、模拟测算、费用预测指标表达式等读取同一套指标口径。

### 为什么采用机构及产品 + 机构及产品指标两张核心表

会议和需求材料中反复提到，个性化指标大于共性指标。若使用一张全局统一指标树，会出现大量空值指标、冗余指标、跨产品公式难维护和导入匹配歧义。

拆成两张表的目的：

1. 先确定预算对象，再确定该对象下的指标。
2. 不同机构和产品可以保留自己的个性化指标。
3. 共性指标可以复用，但不强迫所有产品使用同一模板。
4. Excel 导入时先匹配对象，再匹配指标，降低同名指标歧义。
5. 报表、透视、模拟测算和智能分析可以基于同一套指标主键。

### 指标分类与处理口径

指标不应只按名称维护，还应按业务属性管理：

1. **余额类**
   - 反映时点余额。
   - 年度口径通常取年末或指定月份，不应简单累加。

2. **日均类**
   - 反映期间平均水平。
   - 年日均、月日均等加工应尽量在数据层或规则层处理，避免报表公式过度嵌套。

3. **损益类**
   - 反映收入、支出、利润等期间发生额。
   - 年度口径通常可由月度数据汇总。

4. **比例类**
   - 反映比率、占比、收益率等。
   - 必须明确分子、分母、期间和展示口径。

### 实际数、预算数和预测数

系统需要区分实际数、预算数和预测数：

1. 实际数来自管会报表、业务报送、BI 报表或其他确认来源。
2. 预算数来自预算编制、预算底稿或用户录入。
3. 预测数来自滚动预测、部门费用预测、模拟测算或智能预算模拟。
4. 同一指标可存在预算公式和实际公式。
5. 报表展示时需要按月份、期间和版本选择对应口径。
6. 能由月度数据汇总得到年度结果的，不应为所有场景重复建立年度指标。

## Functional Requirements

### 1. 预算规则配置

预算规则配置是经营预算主线的底座。

#### 1.1 机构及产品维护

1. 用户可以维护机构、产品和业务单元层级。
2. 用户可以新增、修改、停用、排序和调整层级。
3. 系统应避免产品主数据和旧产品入口重复维护。
4. 产品层级应被预算录入、指标配置、报表展示、模拟测算共享。

#### 1.2 机构及产品指标维护

1. 用户可以为机构或产品维护独立指标表。
2. 用户可以配置指标层级、指标编码、指标名称、数值类型、启停状态和排序。
3. 用户可以配置预算公式、实际公式和汇总规则。
4. 用户可以维护横向汇总、纵向汇总和逻辑码。
5. 系统需要把已确认指标同步到运行引用，供预算事实、公式、展示和分析使用。

#### 1.3 规则配置拆分

原有“规则控制配置台”应按职责拆为：

1. 基础档案：机构、产品、部门、预算科目、期间、版本。
2. 规则配置：汇总规则、年度化规则、取数规则、启停规则、跑批规则。
3. 指标配置：机构及产品指标、指标公式、实际/预测口径、指标分类。

### 2. 预算数据输入

预算数据输入负责把预算、实际和预测数据进入系统。

#### 2.1 机构及产品数据录入

1. 用户按机构、产品、指标、期间、版本录入或导入数据。
2. 页面应接近 Excel 高密度录入体验。
3. 可录入项和计算项应区分展示。
4. 公式项原则上不应被用户直接覆盖，除非业务规则允许并留痕。
5. 用户确认后，系统通过正式写入服务进入预算事实。

#### 2.2 Excel 导入

1. 支持预算底稿、业务报送报表、管会下载报表等 Excel 上传。
2. 支持模板解析、指标定位、数据预览、异常提示和确认导入。
3. 支持未匹配机构、产品、指标、期间、版本的提示。
4. 导入后可追溯来源文件、导入批次和原始行。
5. 不允许未经校验直接入库。

#### 2.3 机构及产品预测输出

1. 支持按机构、产品和指标输出预测结果。
2. 支持预算数、实际数、预测数分月展示。
3. 支持导出用于业务复核和汇报。

### 3. 跑批处理与预算事实刷新

跑批处理负责把录入、导入、公式、汇总和读模型统一刷新。

1. 支持用户按年度、版本和范围触发预算事实刷新跑批。
2. 跑批应包括公式重算、指标树横向/纵向汇总、预算汇总和透视聚合重建。
3. 跑批结果应显示状态、耗时、异常数量和失败原因。
4. 跑批应记录历史和审计日志。
5. 跑批不应成为新的人工录入口。

### 4. 预算展示报表

预算展示报表是经营预算输出的固定报表入口。

#### 4.1 报表视图

预算展示报表至少包含：

1. 全行总表。
2. 分产品概览。
3. 单产品明细。

#### 4.2 展示表职责

1. 展示表只定义报表结构和展示行。
2. 分类行只展示层级，不直接取数。
3. 指标行必须绑定正式指标或运行引用。
4. 展示名称可以业务化，但底层取数口径必须稳定。
5. 在线展示和 Excel 导出应保持结构一致。

#### 4.3 报表能力

1. 支持版本、期间、机构、产品筛选。
2. 支持展开收起月度列和层级行。
3. 支持金额单位、百分比和空值展示规范。
4. 支持数据追溯到来源指标、预算事实和导入来源。
5. 支持 Excel 导出。

### 5. 部门费用预算管理

部门费用预算管理模块作为独立业务主线，不应被混入经营预算指标体系，但可以共享系统基础能力和部分指标来源。

#### 5.1 部门科目维护

1. 支持维护费用责任部门、主体、事业群和费用归属部门。
2. 支持部门层级、启停状态和费用归属关系。

#### 5.2 部门预算科目维护

1. 支持维护部门预算科目树。
2. 支持科目层级、预算科目名称、启停状态和排序。
3. 费用预测和费用预算执行报表应读取同一套部门预算科目。

#### 5.3 BI 映射维护

1. 支持 BI 科目到预算科目的映射。
2. 支持归口管理部门到费用归属部门的映射。
3. 未匹配项应提示并允许业务补充映射。

#### 5.4 费用执行明细导入

1. 支持本年实际、上年实际、本年预算等 BI 报表导入。
2. 导入后形成费用执行明细 Adapter。
3. 费用预算执行报表和部门费用预测应优先读取当前已确认导入数据。

#### 5.5 费用预测逻辑配置与部门费用预测

1. 支持按费用责任部门、事业群或预算科目编制费用预测。
2. 支持规则参数、指标表达式变量、人工覆盖和重算。
3. 指标表达式可引用机构及产品指标运行引用，但进入计算前必须解析为正式运行口径。
4. 支持导入、导出和追踪测算依据。

#### 5.6 费用预算执行报表

1. 支持查询模式、月报格式、部门模式和科目模式。
2. 支持本年实际、去年同期、年度预算、预算执行率、同比、环比。
3. 支持按主体、事业群、费用归属部门、预算科目和月份筛选。
4. 支持 Excel 导出。

### 6. 多维分析工具

多维分析工具读取已经形成的结果口径，不承担主数据维护职责。

1. 当前年度多版本透视读取预算汇总读模型。
2. 多年度对比透视读取多年度对比读模型。
3. 多年度数据透视图基于汇总数据生成图形分析。
4. 智能分析报告读取正式数据和口径生成文字分析。
5. 智能演示 PPT 读取正式数据、图表配置和模板生成演示材料。

### 7. 智能能力

AI 能力分阶段建设。

#### 7.1 第一阶段不前置 AI

第一阶段重点是数据、指标、录入、报表和跑批。基础没有稳定前，不应把 AI 预测、自动方案生成作为主流程依赖。

#### 7.2 Agent 分析

1. 支持预算查询、口径解释、透视建议和业务问答。
2. 对缺少时间、版本、机构、产品、指标等条件的问题进行澄清。
3. 只读查询优先，高风险写入需要确认和审计。

#### 7.3 智能分析报告和智能 PPT

1. 根据正式预算数据生成分析说明。
2. 支持预算数、预测数、实际数差异分析。
3. 支持异常点、重点机构和重点产品说明。
4. 支持生成汇报材料草稿。
5. 生成结果需要展示数据来源和分析依据。

#### 7.4 智能预算模拟

1. 支持用户输入领导自然语言目标。
2. AI 将目标解析为结构化约束，用户确认后进入求解。
3. 后端算法基于正式指标、运行引用和预算事实生成方案。
4. AI 负责方案命名、解释和协商话术，不决定最终数值和排名。
5. 不恢复旧 `driver_*` 表，不建立第二套公式体系。

### 8. 系统配置与权限

1. 支持用户和角色管理。
2. 支持权限控制和最小权限原则。
3. 支持年度库、版本、展示版本和编辑版本管理。
4. 支持系统数据同步和运行状态查看。
5. 所有关键配置变更、预算事实写入、导入应用和跑批操作应留痕。

## Workflow

### 经营预算主流程

```text
机构及产品维护
  -> 机构及产品指标维护
  -> Excel / 业务报送 / 管会报表接入
  -> 指标定位与数据校验
  -> 机构及产品数据录入确认
  -> 预算事实写入
  -> 公式重算与横纵向汇总
  -> 预算展示报表
  -> 多维透视 / 智能报告 / 智能 PPT / 智能预算模拟
```

### 部门费用预算主流程

```text
部门科目维护
  -> 部门预算科目维护
  -> BI 映射维护
  -> 费用执行明细导入
  -> 费用预测逻辑配置
  -> 部门费用预测
  -> 费用预算执行报表
  -> 投入产出专题 / 成本收入比分析
```

### 数据流主线

```text
数据来源
  -> 导入批次
  -> 映射匹配
  -> 业务事实
  -> 汇总读模型
  -> 报表 / 透视 / 智能分析 / 导出
```

## User Stories

1. As a 预算管理人员, I want to maintain 机构及产品 as the only product and object master data, so that product names and hierarchy do not drift across pages.
2. As a 预算管理人员, I want to maintain indicators under specific institutions and products, so that personalized indicators can exist without forcing every product into one global template.
3. As a 预算管理人员, I want common indicators to be reusable, so that repeated metric setup is reduced while business differences remain.
4. As a 预算管理人员, I want Excel data to be matched by institution, product, metric, period, and version, so that imported values enter the correct budget context.
5. As a 预算管理人员, I want unmatched Excel rows to be visible before import, so that data is not silently lost or misclassified.
6. As a 预算管理人员, I want uploaded files and import batches to be traceable, so that every number can be explained later.
7. As a 预算管理人员, I want 机构及产品数据录入 to behave like a dense Excel-style grid, so that online entry fits current budgeting habits.
8. As a 预算管理人员, I want calculation indicators to be separated from manual entry indicators, so that users do not overwrite formula results by mistake.
9. As a 预算管理人员, I want confirmed data to enter budget facts through the official writer, so that formula recalculation and audit rules are consistently applied.
10. As a 预算管理人员, I want the budget refresh batch to rebuild formula results and summaries, so that reports and pivot tables use the latest official result.
11. As a 预算主管, I want a fixed budget display report, so that management reports have stable layout and stable口径.
12. As a 预算主管, I want report category rows to be visibly different from data rows, so that blank grouping rows are not mistaken for zero-valued metrics.
13. As a 预算主管, I want report numbers to trace back to metrics and facts, so that I can explain source and calculation path.
14. As a 业务产品部门用户, I want product-level budget and forecast output, so that my product's budget result can be reviewed independently.
15. As a 业务产品部门用户, I want product-specific indicators to be preserved, so that my product is not forced into irrelevant common metrics.
16. As a 部门费用管理人员, I want BI mappings to be maintained before importing expense actuals, so that BI reports can become usable expense data.
17. As a 部门费用管理人员, I want expense actual import preview and error details, so that mapping problems are fixed before正式入库.
18. As a 部门费用管理人员, I want department expense forecast rules to support parameters and metric variables, so that forecast logic can be configured rather than hard-coded.
19. As a 部门费用管理人员, I want manual overrides to be marked and traceable, so that forecast adjustments are auditable.
20. As a 部门费用管理人员, I want expense budget execution reports to support multiple views, so that I can review by department, subject, month, and owner.
21. As a 管理层用户, I want fixed reports and flexible analysis to coexist, so that standard reporting and ad hoc questions are both supported.
22. As a 管理层用户, I want intelligent reports to explain budget, forecast, and actual differences, so that meeting materials can be prepared faster.
23. As a 管理层用户, I want intelligent budget simulation to generate multiple方案 under a leadership target, so that decisions are supported by data and constraints.
24. As a 系统管理员, I want users, permissions, years, versions, and display slots to be managed centrally, so that the system can be used in a controlled internal environment.
25. As a 系统管理员, I want all critical changes to be audited, so that budget data changes are traceable.
26. As a 开发人员, I want the PRD to respect current modules and retired boundaries, so that future development does not accidentally restore old tables or pages.
27. As a 测试人员, I want clear acceptance criteria for import, matching, facts, reports, and AI confirmation, so that test cases can validate business outcomes.

## Implementation Decisions

1. Keep `apps/web` and `apps/api` as the current implementation surfaces.
2. Keep the current navigation split: 预算管理、部门费用预算管理模块、多维分析工具、系统配置中心、帮助与使用说明.
3. Treat 机构及产品指标 as the single maintenance surface for budget metrics, formulas, and metric hierarchy.
4. Treat 机构及产品数据录入 as the single user-facing budget fact entry surface.
5. Continue using BudgetDataWriter as the owner of annual budget fact writes.
6. Continue using budget summary and pivot aggregate read models for reports and analysis.
7. Treat budget display configuration as a report layout structure, not a metric master data table.
8. Treat department expense modules as a separate expense-budget loop with private tables and read models.
9. Keep BI mapping as the bridge between BI reports and department expense budget口径.
10. Keep intelligent reports, intelligent PPT, Agent, and intelligent budget simulation as consumers of official data and口径.
11. Do not restore retired tables or retired front-end entry points.
12. Build future work as incremental module improvements rather than a full rewrite.

## Testing Decisions

1. Tests should verify external business behavior, not implementation details.
2. Excel import tests should cover template parsing, mapping, unmatched rows, preview, confirmation, and batch traceability.
3. Metric tests should cover personalized indicators, common indicator reuse, indicator enable/disable, formula configuration, and horizontal/vertical rollup.
4. Budget fact tests should verify that confirmed data writes through the official writer and respects version, period, product, metric, and budget/actual口径.
5. Budget refresh tests should verify formula recalculation, rollup generation, summary rebuild, and audit records.
6. Budget display tests should verify category rows, metric rows, row binding, report views, and Excel export consistency.
7. Department expense tests should cover BI mapping, expense actual import, expense forecast rules, manual overrides, and expense execution report views.
8. AI tests should mock model responses and verify confirmation gates, source traceability, and no direct unauthorized writes.
9. Frontend tests should cover dense table behavior, import preview flows, report display consistency, and no incoherent overlap on common desktop widths.
10. Regression tests should include current modules already present in the repository instead of inventing unrelated demo surfaces.

## Acceptance Criteria

1. PRD, System PDD, Database PDD and current system map do not conflict on core concepts.
2. 经营预算 and 部门费用预算 are clearly separated in navigation and documentation.
3. 机构及产品 and 机构及产品指标 are documented as the metric and object base.
4. Excel data source, upload, mapping, validation, confirmation, storage and traceability are documented end to end.
5. Budget display table is documented as report layout only.
6. AI capability is documented as second-stage enhancement based on stable data and indicators.
7. Retired tables and retired pages are explicitly out of scope.
8. Future implementation can be split into independent issues by module.

## Open Questions

1. 预算底稿、业务报送、管会下载报表的标准模板是否需要分别定义字段级格式。
2. 管会 P0301 报表与机构及产品指标的映射是否先做半自动导入，还是先人工维护映射表。
3. 预算展示报表的三类视图是否需要增加领导专用简表。
4. 机构及产品指标中共性指标复用的配置方式，是批量复制、引用模板，还是功能族治理。
5. 实际数和预测数是否需要在所有指标上都维护两套公式，还是只对部分指标开放。
6. AI 生成报告是否需要正式审批流，还是先作为草稿导出。
7. 管会系统对接的合规审批和跨环境方案由哪个团队牵头。

## Out of Scope

1. 本 PRD 不定义详细数据库字段，以 Database PDD 为准。
2. 本 PRD 不定义每个 API 的请求响应字段，以后续接口设计或现有路由为准。
3. 本 PRD 不要求第一阶段完成管会系统直连。
4. 本 PRD 不要求第一阶段实现全部 AI 能力。
5. 本 PRD 不要求一次性重构所有前端页面。
6. 本 PRD 不恢复历史归档方案。

## Further Notes

1. 本 PRD 是“补写项目级 PRD”，用于把现有系统、会议纪要和新增需求材料统一到同一条业务主线上。
2. 后续如果拆 issue，建议按以下工作区拆分：
   - 数据来源与 Excel 导入治理。
   - 机构及产品指标体系治理。
   - 预算展示表结构治理。
   - 前端表格与页面统一治理。
   - 部门费用预算闭环治理。
   - 智能报告与智能演示输出治理。
   - 智能预算模拟增强。
3. 任何新增功能都应先说明自己属于经营预算、部门费用预算、多维分析、系统配置或智能能力中的哪一类。
