# 分析模板库

## 模板 A：预算 vs 实际执行分析

### 适用场景

- 用户要求分析某时间段预算执行偏差。

### 输入变量

- 时间范围：`{time_period}`
- 对象范围：`{scope}`
- 粒度：`{granularity}`
- 指标：`{metric_name}`
- 关键结果：`{key_result_table}`

### 输出模板

1. 数据事实：在 `{time_period}` 内，`{scope}` 的 `{metric_name}` 表现为 `{fact_summary}`。
2. 结构拆解：从 `{granularity}` 视角看，主要贡献来自 `{top_drivers}`，主要拖累来自 `{down_drivers}`。
3. 原因判断：结合历史经验与口径规则，可能原因包括 `{possible_causes}`。
4. 建议动作：建议优先执行 `{action_1}`、`{action_2}`，并在下期关注 `{monitoring_items}`。

---

## 模板 B：同比/环比趋势分析

### 适用场景

- 用户要求看趋势变化、拐点或异常波动。

### 输入变量

- 对比类型：`{comparison_type}`
- 目标指标：`{metric_name}`
- 序列数据：`{trend_series}`
- 异常点：`{anomaly_points}`

### 输出模板

1. 趋势结论：`{metric_name}` 在 `{time_period}` 呈现 `{trend_direction}`。
2. 关键拐点：在 `{anomaly_points}` 出现明显波动，变化幅度 `{change_rate}`。
3. 解释假设：可能受到 `{hypothesis_list}` 影响，建议结合业务事件进一步核验。
4. 后续建议：补充查看 `{next_slice}` 维度，验证 `{validation_goal}`。

---

## 模板 C：多维透视结果解读

### 适用场景

- 用户要求按部门/产品/科目交叉分析差异。

### 输入变量

- 行维度：`{pivot_rows}`
- 列维度：`{pivot_columns}`
- 页维度：`{pivot_pages}`
- 前 N 项：`{top_n_items}`

### 输出模板

1. 总览：当前透视配置为行 `{pivot_rows}`、列 `{pivot_columns}`、页 `{pivot_pages}`。
2. 重点发现：前 N 项中，`{top_n_items}` 对整体差异贡献最大。
3. 风险提示：`{risk_items}` 存在持续偏离目标的风险。
4. 处理建议：建议对 `{focus_scope}` 启动专项分析，必要时回到 Agent 澄清更多背景条件。
