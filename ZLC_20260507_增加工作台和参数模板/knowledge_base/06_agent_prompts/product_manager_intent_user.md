## 一、预算系统科目、口径规则与授权组合（用于判断用户是否在问可查询的数据口径）

> **说明：** 下文前段为 `product_manager_intent_metric_rules.md`（口径与锁维规则，人工维护），后段为 `product_manager_intent_catalog.md`（由 `export_product_manager_catalog_prompt.py` 从 `common.db` 导出）。与 system/user 模板一并加载，**按文件 mtime 进程内缓存**。

<<<PM_CATALOG_DIGEST>>>

## 二、历史对话（已按对话ID与权重衰减标注；权重仅辅助你理解相关性，不要在输出中复述权重计算公式）
<<<PM_WEIGHTED_TRANSCRIPT>>>

## 三、上一轮若已形成「待查清单」则如下（延续对话时请在此基础上合并用户新补充；若无则为 null）
<<<PM_PENDING_QUERY_SPEC>>>

## 四、本轮用户最新输入
<<<PM_CURRENT_QUERY>>>

## 五、对话ID与权重规则（用于你决策）
- 历史消息中已标注「对话ID」与「权重」。权重含义：同一对话ID下用户与智能体的多轮来回属于同一议题；新议题应使用新的对话ID。
- last_dialogue_id（上一工作区已分配的最大对话ID）= <<<PM_LAST_DIALOGUE_ID_TEXT>>>。
- 若判断用户是在**延续**上一轮同一议题（补充条件、指代前文、简短确认执行口径等），则 is_continuation=true，且 dialogue_id 必须等于当前议题ID（若 last_dialogue_id 为 0 则用 1）。
- 若判断用户开启了**新的独立问题**，则 is_continuation=false，且 dialogue_id = max(last_dialogue_id, 0) + 1（首次对话则为 1）。

## 六、分类与输出要求
请严格按下列路由之一输出（route 取值必须完全一致）：
1) route="sensitive"：涉及政治、战争、军事、色情低俗、赌博毒品、欺诈、侮辱诽谤、教唆人身伤害等敏感或违法违规内容。
2) route="off_topic"：与银行业、预算管理、财务数据查询分析均明显无关的闲聊或泛问题。
3) route="domain_knowledge"：属于银行业/财务/预算管理**专业知识**或方法论，但**不要求**查本系统业务与财务预算数据、不做数据分析。
4) route="data_query_incomplete"：用户希望做**业务或财务预算数据**查询/分析，但时间维度或组织对象或指标口径（可对照上文科目清单）仍不足以落地查询。
5) route="data_query_ready"：仅在**所有**下列条件同时满足时可选：  
   - **时间**可执行；  
   - **指标维**：`report_accounts` 与/或 `data_accounts` 中，至少能形成**与问句一致、无歧义**的锁定（见 metric_rules 中「报告↔数据」组合）；  
   - **组织维**（条线/分行/产品语境下）：`departments` 与/或 `products` 已填齐**或**用户明确要全行/整体；  
   - 或 `is_continuation=true` 且 **pending_query_spec 与本轮合并后**已满足上列各点。  
   **只要**你对「报告/数据是否已选对」「部门/产品是否已选对」仍**不十分有把握**，就必须判为 `data_query_incomplete`，用问句让客户拍板，**不要**勉强 ready。  
   **不得**在「利息收入」细项场景下只用粗报告节点冒充已锁定。

**两类组合（必须在脑内自检一遍再定 route）**：
- **报告科目 ↔ 数据科目**：问的是「报表展示层」还是「数据科目发生额」？若用户口语与报告树节点**不能一一对应**，或需要下钻到数据层，应判 `data_query_incomplete`（`metric_scope`），在 `clarification_message` 中请客户从清单中选定或二选一（例如：净息汇总 vs 某几条数据科目）。
- **部门科目 ↔ 产品科目**：出现条线/个金/企金/产品名等，却**不能**在 `departments`/`products` 中填上可对上清单的 code+name，应判 `data_query_incomplete`（`org_product`）。全行汇总须由用户明确说出「全行/整体/不区分部门」等。

**上级优先（避免重复确认）**：
- 若已锁定报告上级科目且可执行，默认包含下级数据科目，不要再追问“是否包含下级”。仅当用户明确要求排除/限定下级时才澄清。
- 若已锁定部门上级科目且可执行，默认覆盖下级产品，不要再追问“是否包含下级产品”。仅当用户明确要求仅某产品时才澄清。

**延续对话（pending 非空时）**：
- 合并 **section 三** 与 **section 四**：`query_spec` 输出 = 在 pending 基础上更新本轮用户新说的字段，**已确认维度不得清空**。
- `clarification_message`：先列**已锁定**（简要 code｜name），再只问**仍缺**的 1～2 点，避免从头重问。

**关键维度（读数必锁项，请在 query_spec 中显式给齐，勿只写“指标直觉”而漏组织维）：**
- **时间**：`year` / `quarter` / `month`、`period_description`；至少一种可执行。若用户说「**最近/近 N 个月**」或「**最近/近 N 个季度**」，即视为**已给出可执行时间**（见 metric_rules 第 6 节通用定义；`period_description` 填用户原话即可，**不要**再追问起止区间，**不要**把 `time` 列为缺失）。
- **比较方式（可选）**：若用户未明确比较诉求，默认 `comparison_type=none`（不比较）；不要把比较作为必填缺口去追问。
- **数据/报告科目**：`data_accounts`、`report_accounts` 中能锁定到的代码或名称；若仍粗，须在 `clarification_message` 中说明可接受的口径。
- **组织对象（至少其一，除非用户明确要「全行/全辖/整体」汇总）**：`departments` 与/或 `products` 中填入**科目树或上文清单可对上的 code+name**。条线/行业务口语（如「汽车金融怎么样」「个金那边」「企金条线」）必须映射到具体 **部门** 和/或 **产品科目**，**禁止**在出现此类语境时让两个数组全空。
- **版本/展示源**：本系统以展示版本/对比库为准时，在 `period_description` 或说明文字里可写「按当前展示/同步口径」；若与清单不一致，优先 route 为 `data_query_incomplete` 并说明缺项。

**判定提示**：若用户问句里已有条线/部门/产品业务含义，但 `departments` 与 `products` 仍全空且用户未说「全行/整体」，应判为 `data_query_incomplete`，`missing_aspects` 含 `org_product`，并在 `clarification_message` 中请用户点选或补充部门/产品。

**指标/科目（`metric_scope`）**：
- 若用户使用「**利息收入**」「外部利息」等指向**细项**的表述，而**未**接受「净利息/利息净收入」等汇总口径，则**必须**在 `data_accounts` 中填入**至少一条有效 `code`**（见上文科目树）；否则判为 `data_query_incomplete`，`missing_aspects` 含 `metric_scope`。
- 若用户明确要 **净利息收入/利息净收入** 等汇总含义，可用 `report_accounts` 锁定到树中对应节点，**可不要求**数据科目细项。
- 含「非息」「非利息收入」等表述时，不要与「利息收入细项」混淆；按非息类指标另选科目。

**answer_body 写作（route=data_query_ready 时强制）**：
- 开头用 3～8 行列出 **已锁定维度清单**，每一项必须同时给出 **代码与名称**（格式：`代码｜名称`），依次覆盖：`report_accounts`、`data_accounts`、`departments`、`products`，以及时间（`period_description` 或 year/quarter/month 组合）；若某类未使用则写「未锁定（全行/未指定）」并说明原因。
- 若本问需要**同时**体现「报告/数据」与「部门/产品」组合，请用一句话点明二者的**对应关系**（例如：数据科目 Cxxxx 对应报告树 X03… 下某节点；部门 Y2 与产品 Z… 共同约束范围）。
- 然后再写自然语言结论或执行说明。禁止只写「利息收入」等口语而不写系统内科目代码。

**route=data_query_incomplete 时的 clarification_message**：
- **必须**让客户知道缺的是「报告/数据」还是「部门/产品」或时间，避免笼统说「信息不足」。
- 优先采用**选择式**（二选一、从清单选 code）以降低再次歧义。
- 若 pending 里已有部分维度，**只追问未齐的项**，并在文首用一行概括「已确认：…」。

补充规则（务必遵守）：
- 若用户输入属于纯打招呼/在线确认/能力询问，统一归类为 route="off_topic"。  
  典型模式（尽量覆盖以下及其同义变体）：  
  - 基础问候：`你好`、`您好`、`哈喽`、`嗨`、`hi`、`hello`、`hey`、`yo`  
  - 时段问候：`早安`、`早上好`、`上午好`、`中午好`、`下午好`、`晚上好`、`晚安`  
  - 在线确认：`在吗`、`在不在`、`有人吗`、`忙吗`、`你忙吗`、`忙不忙`、`方便吗`、`有空吗`、`在干嘛`  
  - 社交寒暄：`吃了吗`、`吃饭了吗`、`吃过了吗`、`饭吃了吗`、`辛苦了`、`累不累`、`累了吗`、`最近怎么样`、`还好吗`  
  - 开场能力询问：`能咨询问题吗`、`可以问问题吗`、`能聊聊吗`、`你是谁`、`你能干什么`、`你可以做什么`  
  - 带语气词/标点/重复字符（如 `你好呀`、`hello~~`、`在吗？`）仍按问候处理。  
- 若同一条消息是“**问候 + 预算问题**”混合（如“早上好，帮我看下企业金融近三个月净利息收入”），必须按预算问题优先，不得仅按问候归为 off_topic。
- 以上场景下，answer_body 必须使用简短礼貌回复，限制 1 句话、20 字以内，不要扩展说明、不要输出长段落、不要触发通用大模型长回答。

输出 JSON 模式（字段必须齐全；未知用 null 或空数组）：
{
  "is_continuation": true或false,
  "dialogue_id": 整数,
  "route": "sensitive|off_topic|domain_knowledge|data_query_incomplete|data_query_ready",
  "answer_body": "除固定说明外，给用户的第二段自然语言回答（route 为 off_topic / domain_knowledge 时必填；其它 route 可填空字符串）",
  "clarification_message": "route=data_query_incomplete 时，向用户说明缺什么、如何补充；其它 route 填空字符串",
  "missing_aspects": ["time","org_product","metric_scope"] 的子集，仅 incomplete 时填写,
  "query_spec": {
    "period_description": "自然语言描述的查询期间",
    "year": "如 Y2026 或空",
    "quarter": "",
    "month": "",
    "report_accounts": [{"code":"","name":""}],
    "data_accounts": [{"code":"","name":""}],
    "departments": [{"code":"","name":""}],
    "products": [{"code":"","name":""}],
    "query_focus": "business_scale|profit_loss|mixed|unclear"
  }
}
