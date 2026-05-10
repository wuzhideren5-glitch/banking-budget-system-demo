from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

BudgetInputImportCellStatus = Literal["empty", "inserted", "updated", "skipped", "error"]


class ProductScopeMigrationFileItem(BaseModel):
    file_name: str
    file_year: int | None = None
    rows_to_insert: int = 0
    rows_to_delete: int = 0


class ProductScopeMigrationPreviewResponse(BaseModel):
    data_acct_code: str
    affects_all_budget_files: bool = True
    files: list[ProductScopeMigrationFileItem] = Field(default_factory=list)
    total_rows_to_insert: int = 0
    total_rows_to_delete: int = 0
    message: str = ""


class DataAccountRow(BaseModel):
    data_acct_code: str
    data_acct_name: str
    metric_group_code: str | None = None
    metric_group_name: str | None = None
    product_code: str | None = None  # 废弃，保留兼容
    product_codes: str | None = None  # 逗号分隔多产品，NULL/空=''=所有产品/公司级/指定产品
    budget_formula: str | None = None
    actual_formula: str | None = None
    need_calc: int = 0
    budget_rule_code: str | None = None
    budget_rule_config_json: str | None = None
    value_type: str
    remark: str | None = None
    product_name: str | None = None
    has_budget_data_records: bool = False
    budget_data_ref_count: int = 0
    report_mapping_ref_count: int = 0
    migration_inserted_total: int | None = None
    migration_deleted_total: int | None = None
    migration_files: list[ProductScopeMigrationFileItem] | None = None

    @computed_field
    @property
    def product_display(self) -> str:
        # 三态：'all'=全部产品, ''=公司级, 'Z01,Z02'=指定产品
        _pcs = self.product_codes
        if _pcs is None or str(_pcs).upper().strip() == 'ALL':
            return "适用所有产品科目"
        if str(_pcs).strip() == "":
            return "公司级科目"
        # 逗号分隔显示
        codes = [c.strip() for c in _pcs.split(",") if c.strip()]
        if not codes:
            return "适用所有产品科目"
        if len(codes) == 1:
            return codes[0]
        return f"{codes[0]} 等{len(codes)}个产品"


class DataAccountCreate(BaseModel):
    data_acct_code: str | None = None
    data_acct_name: str
    metric_node_code: str | None = None
    scope_code: str | None = None
    metric_binding_code: str | None = None
    metric_group_code: str | None = None
    metric_group_name: str | None = None
    product_code: str | None = None  # 废弃，保留兼容
    product_codes: list[str] | None = None  # None/[]=所有产品, ['Z01']=指定产品
    budget_formula: str | None = None
    actual_formula: str | None = None
    budget_rule_code: str | None = None
    budget_rule_config_json: str | None = None
    value_type: str = "金额"
    remark: str | None = None

    @field_validator("data_acct_code")
    @classmethod
    def code_fmt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        import re

        if not re.match(r"^[A-Z]\d{4}$", v):
            raise ValueError("科目代码须为 1 位大写字母 + 4 位数字")
        return v

    @field_validator("value_type")
    @classmethod
    def vt(cls, v: str) -> str:
        allowed = {"金额", "百分比", "户数"}
        if v not in allowed:
            raise ValueError("数值类型须为：金额、百分比、户数")
        return v

    @model_validator(mode="after")
    def product_scope(self) -> DataAccountCreate:
        # product_codes: None/[] = 所有产品, 有值 = 指定产品(空字符串需前端传['']表示公司级)
        self.product_code = None
        return self


class DataAccountUpdate(BaseModel):
    data_acct_code: str | None = None
    data_acct_name: str | None = None
    metric_group_code: str | None = None
    metric_group_name: str | None = None
    product_code: str | None = None  # 废弃，保留兼容
    product_codes: list[str] | None = None  # None/[]=所有产品, 有值=指定产品, ['']=公司级
    budget_formula: str | None = None
    actual_formula: str | None = None
    budget_rule_code: str | None = None
    budget_rule_config_json: str | None = None
    value_type: str | None = None
    remark: str | None = None
    confirm_product_scope_migration: bool | None = None
    expected_delete_count_total: int | None = None

    @model_validator(mode="after")
    def product_scope(self) -> DataAccountUpdate:
        self.product_code = None
        return self

    @field_validator("data_acct_code")
    @classmethod
    def code_fmt(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        import re

        if not re.match(r"^[A-Z]\d{4}$", v):
            raise ValueError("科目代码须为 1 位大写字母 + 4 位数字")
        return v

    @field_validator("value_type")
    @classmethod
    def vt(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"金额", "百分比", "户数"}
        if v not in allowed:
            raise ValueError("数值类型须为：金额、百分比、户数")
        return v


class DataAccountMetricNodeRow(BaseModel):
    node_code: str
    node_name: str
    parent_code: str | None = None
    level: int
    node_type: str
    sort_order: int = 0
    is_active: int = 1
    remark: str | None = None


class DataAccountMetricBindingRow(BaseModel):
    binding_code: str
    metric_node_code: str
    metric_node_name: str | None = None
    scope_type: str
    scope_code: str
    product_code: str | None = None
    product_name: str | None = None
    data_acct_code: str
    data_acct_name: str | None = None
    sort_order: int = 0
    is_active: int = 1
    remark: str | None = None


class DataAccountMetricTreeResponse(BaseModel):
    nodes: list[DataAccountMetricNodeRow] = Field(default_factory=list)
    bindings: list[DataAccountMetricBindingRow] = Field(default_factory=list)


class AssumptionParameterRow(BaseModel):
    parameter_code: str
    parameter_name: str
    category: str
    value_type: str
    scope_type: str
    time_granularity: str
    apply_products: str | None = None
    input_mode: str = "manual"
    value_formula: str | None = None
    source_data_code: str | None = None
    default_unit: str | None = None
    is_enabled: bool = True
    remark: str | None = None
    create_time: str
    update_time: str


class AssumptionParameterCreate(BaseModel):
    parameter_code: str
    parameter_name: str
    category: str
    value_type: str = "金额"
    scope_type: str = "global"
    time_granularity: str = "monthly"
    apply_products: str | None = None
    input_mode: str = "manual"
    value_formula: str | None = None
    source_data_code: str | None = None
    default_unit: str | None = None
    remark: str | None = None

    @field_validator("parameter_code")
    @classmethod
    def assumption_code_fmt(cls, v: str) -> str:
        v = v.strip().upper()
        import re

        if not re.match(r"^[A-Z][A-Z0-9_]{1,39}$", v):
            raise ValueError("参数编码须以大写字母开头，仅支持大写字母、数字和下划线")
        return v


class AssumptionParameterUpdate(BaseModel):
    parameter_code: str | None = None
    parameter_name: str | None = None
    category: str | None = None
    value_type: str | None = None
    scope_type: str | None = None
    time_granularity: str | None = None
    apply_products: str | None = None
    input_mode: str | None = None
    value_formula: str | None = None
    source_data_code: str | None = None
    default_unit: str | None = None
    is_enabled: bool | None = None
    remark: str | None = None


class AssumptionValueRow(BaseModel):
    parameter_code: str
    budget_year: int
    version_id: int
    scenario_code: str = "BASE"
    product_scope_key: str = ""
    product_code: str | None = None
    month_index: int
    value: float
    update_time: str


class AssumptionValueUpsertItem(BaseModel):
    parameter_code: str
    month_index: int = Field(ge=0, le=12)
    value: float
    product_scope_key: str = ""
    product_code: str | None = None
    scenario_code: str = "BASE"


class AssumptionValueBatchUpsert(BaseModel):
    budget_year: int
    version_id: int
    items: list[AssumptionValueUpsertItem]
    fill_from_month: int | None = Field(default=None, ge=1, le=12)
    fill_to_month: int | None = Field(default=None, ge=1, le=12)


class AssumptionRuleTemplateRow(BaseModel):
    rule_code: str
    rule_name: str
    rule_type: str
    config_json: str
    is_enabled: bool = True
    remark: str | None = None
    create_time: str
    update_time: str


class AssumptionRuleTemplateUpdate(BaseModel):
    rule_name: str | None = None
    config_json: str | None = None
    is_enabled: bool | None = None
    remark: str | None = None


class AssumptionImpactItem(BaseModel):
    rule_code: str | None = None
    rule_name: str | None = None
    data_acct_code: str | None = None
    data_acct_name: str | None = None
    match_source: str


class AssumptionImpactResponse(BaseModel):
    parameter_code: str
    parameter_name: str | None = None
    items: list[AssumptionImpactItem]


class ForecastWorkbenchSummary(BaseModel):
    layout_count: int = 0
    binding_count: int = 0
    bound_line_count: int = 0
    unbound_line_count: int = 0
    data_account_count: int = 0
    parameter_count: int = 0
    template_count: int = 0


class ForecastWorkbenchBindingRow(BaseModel):
    id: int
    line_code: str
    binding_type: str
    binding_code: str
    binding_name: str | None = None
    binding_role: str = ""
    sort_order: int = 0
    remark: str | None = None


class ForecastWorkbenchLineRow(BaseModel):
    line_code: str
    line_name: str
    line_group: str
    line_category: str
    display_mode: str = "detail"
    sort_order: int = 0
    is_enabled: bool = True
    binding_hint: str | None = None
    remark: str | None = None
    binding_count: int = 0
    bindings: list[ForecastWorkbenchBindingRow] = Field(default_factory=list)


class ForecastWorkbenchOverviewResponse(BaseModel):
    budget_year: int
    version_id: int
    version_name: str
    current_month: int = 1
    summary: ForecastWorkbenchSummary
    lines: list[ForecastWorkbenchLineRow] = Field(default_factory=list)


class BudgetSubjectCatalogRow(BaseModel):
    id: int
    parent_id: int | None = None
    level_number: int
    level_label: str
    subject_name: str
    formula_text: str | None = None
    sort_order: int = 0
    is_leaf: bool = False


class BudgetSubjectCatalogCreate(BaseModel):
    parent_id: int | None = None
    subject_name: str
    formula_text: str | None = None

    @field_validator("subject_name")
    @classmethod
    def budget_subject_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("预算科目名称不能为空")
        return text


class BudgetSubjectCatalogUpdate(BaseModel):
    subject_name: str | None = None
    formula_text: str | None = None

    @field_validator("subject_name")
    @classmethod
    def budget_subject_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        text = v.strip()
        if not text:
            raise ValueError("预算科目名称不能为空")
        return text


class ExpenseActualImportBatchRow(BaseModel):
    id: int
    file_name: str
    import_mode: str
    periods: list[str]
    total_rows: int
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    created_at: str
    note: str | None = None


class ExpenseActualImportPreviewRow(BaseModel):
    period_ym: str
    owner_name_raw: str
    owner_name_mapped: str | None = None
    budget_subject_raw: str
    budget_subject_mapped: str | None = None
    amount: float
    match_status: str
    match_note: str | None = None


class ExpenseActualImportPreviewResponse(BaseModel):
    file_name: str
    row_count: int
    periods: list[str]
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    preview_rows: list[ExpenseActualImportPreviewRow]
    unmatched_preview_rows: list[ExpenseActualImportPreviewRow]


class ExpenseActualImportApplyResponse(BaseModel):
    batch_id: int
    file_name: str
    import_mode: str
    row_count: int
    periods: list[str]
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    note: str | None = None


class SessionInfo(BaseModel):
    user_id: int
    software_version: str
    budget_year: int
    version_id: int
    version_name: str
    version_date_time: str
    user_display_name: str
    user_role: str
    permission_type: int = 3
    first_login_required: bool = False
    db_connected: bool = True
    last_global_calc_refresh_time: str | None = None


class VersionSnapshotItem(BaseModel):
    label: str
    budget_year: int
    version_id: int
    version_name: str
    current_month: int = 1


class VersionSnapshotResponse(BaseModel):
    items: list[VersionSnapshotItem] = Field(default_factory=list)


class LoginRequest(BaseModel):
    user_name: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    need_change_password: bool
    user_name: str
    permission_type: int


class FirstLoginPasswordChangeRequest(BaseModel):
    new_password: str


class BudgetInputPeriod(BaseModel):
    period_id: int
    month_label: str
    month_index: int
    editable: bool = True


class BudgetInputRow(BaseModel):
    report_path: list[str]
    report_code: str | None = None
    data_acct_code: str
    data_acct_name: str
    value_type: str
    calc_formula: str | None = None
    formula_locked: bool = False
    formula_errors: list[str | None] = Field(default_factory=list)
    values: list[float]
    total: float


class BudgetInputLoadResponse(BaseModel):
    budget_year: int
    version_id: int
    current_month: int = 1
    budget_actual: int
    product_code: str
    periods: list[BudgetInputPeriod]
    rows: list[BudgetInputRow]


class BudgetInputCellUpsert(BaseModel):
    data_acct_code: str
    product_code: str
    period_id: int
    version_id: int
    budget_actual: int
    value: float

    @field_validator("budget_actual")
    @classmethod
    def budget_actual_flag(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("budget_actual 必须为 0（预算）或 1（实际）")
        return v


class BudgetInputBatchUpsert(BaseModel):
    items: list[BudgetInputCellUpsert]


class BudgetInputWriteResult(BaseModel):
    saved: int


class BudgetInputImportMonthResult(BaseModel):
    month: int
    value_text: str = ""
    status: BudgetInputImportCellStatus = "empty"
    reason: str | None = None


class BudgetInputImportResultRow(BaseModel):
    sheet_name: str
    excel_row: int
    data_acct_code: str
    product_code: str
    months: list[BudgetInputImportMonthResult]
    note: str = ""


class BudgetInputImportResponse(BaseModel):
    budget_year: int
    version_id: int
    current_month: int
    rows: list[BudgetInputImportResultRow]
    saved_cells: int = 0


class BudgetSummaryRebuildResult(BaseModel):
    version_id: int
    current_month: int = 1
    rebuilt_rows: int
    rule_message: str = ""


class BudgetSummaryRowDto(BaseModel):
    report_level1: str | None = None
    report_level2: str | None = None
    report_level3: str | None = None
    report_level4: str | None = None
    report_level5: str | None = None
    dept_level1: str | None = None
    dept_level2: str | None = None
    dept_level3: str | None = None
    data_code_name: str
    product_code_name: str | None = None
    year: str
    month: str
    quarter: str
    budget_actual: int
    version_id: int
    version_name: str | None = None
    current_month: int = 1
    rule_message: str | None = None
    value: float
    value_type: str
    update_time: str | None = None


class BudgetSummaryExportPivotRequest(BaseModel):
    row_field_ids: list[str] = Field(default_factory=list)
    column_field_ids: list[str] = Field(default_factory=list)
    page_field_ids: list[str] = Field(default_factory=list)
    page_selections: dict[str, str] = Field(default_factory=dict)
    show_row_total: bool = True
    show_column_total: bool = True


class CompareSummaryRowDto(BaseModel):
    show_level: int
    data_file_id: int
    source_year: int
    source_version_id: int
    source_version_name: str | None = None
    report_level1: str | None = None
    report_level2: str | None = None
    report_level3: str | None = None
    report_level4: str | None = None
    report_level5: str | None = None
    dept_level1: str | None = None
    dept_level2: str | None = None
    dept_level3: str | None = None
    data_code_name: str
    product_code_name: str | None = None
    year: str
    month: str
    quarter: str
    budget_actual: int
    value: float
    value_type: str
    sync_time: str


class CompareSummarySyncResult(BaseModel):
    inserted_rows: int
    selected_versions: int
    trigger_source: str
    message: str
    rule_message: str = ""
    level_rules: list[str] = Field(default_factory=list)


class CompareSyncLatestStatus(BaseModel):
    job_id: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    trigger_source: str | None = None
    status: str | None = None
    message: str | None = None


class GlobalRefreshAnnualStatus(BaseModel):
    data_file_name: str
    year: int
    refresh_time_a: str | None = None


class GlobalRefreshStatusResponse(BaseModel):
    annual_items: list[GlobalRefreshAnnualStatus] = Field(default_factory=list)
    compare_refresh_time_b: str | None = None
    next_planned_refresh_time_c: str | None = None


class ChartReportTreeNodeDto(BaseModel):
    report_acct_code: str
    report_acct_name: str
    is_summary: bool
    children: list["ChartReportTreeNodeDto"] = Field(default_factory=list)


class ChartVersionItemDto(BaseModel):
    data_file_id: int
    data_file_name: str
    year: int
    version_id: int
    version_name: str
    current_month: int


class ChartVersionOptionsResponseDto(BaseModel):
    options: list[ChartVersionItemDto] = Field(default_factory=list)


class ChartVersionSelectionDto(BaseModel):
    data_file_id: int
    version_id: int


class ChartStackedRequestDto(BaseModel):
    report_acct_code: str
    use_all_versions: bool = True
    selected_versions: list[ChartVersionSelectionDto] = Field(default_factory=list)
    single_version_granularity: str = "month"
    stack_mode: str = "absolute"

    @field_validator("single_version_granularity")
    @classmethod
    def granularity_allowed(cls, v: str) -> str:
        text = (v or "").strip().lower()
        if text not in {"month", "quarter"}:
            raise ValueError("single_version_granularity 仅支持 month 或 quarter")
        return text

    @field_validator("stack_mode")
    @classmethod
    def stack_mode_allowed(cls, v: str) -> str:
        text = (v or "").strip().lower()
        if text not in {"absolute", "percent"}:
            raise ValueError("stack_mode 仅支持 absolute 或 percent")
        return text


class ChartBarRequestDto(BaseModel):
    """柱状图：按期间分组；本科目为单系列，下级科目为多系列分组柱。"""

    report_acct_code: str
    bar_compare_scope: str = "self"
    use_all_versions: bool = True
    selected_versions: list[ChartVersionSelectionDto] = Field(default_factory=list)
    single_version_granularity: str = "month"

    @field_validator("bar_compare_scope")
    @classmethod
    def bar_scope_allowed(cls, v: str) -> str:
        text = (v or "").strip().lower()
        if text not in {"self", "children"}:
            raise ValueError("bar_compare_scope 仅支持 self（本科目）或 children（下级科目）")
        return text

    @field_validator("single_version_granularity")
    @classmethod
    def bar_granularity_allowed(cls, v: str) -> str:
        text = (v or "").strip().lower()
        if text not in {"month", "quarter"}:
            raise ValueError("single_version_granularity 仅支持 month 或 quarter")
        return text


class ChartStackedSeriesDto(BaseModel):
    key: str
    label: str
    values: list[float] = Field(default_factory=list)
    value_type: str | None = None


class ChartStackedMatrixRowDto(BaseModel):
    row_label: str
    values: list[float] = Field(default_factory=list)
    value_type: str | None = None


class ChartStackedResolvedVersionDto(BaseModel):
    data_file_id: int
    year: int
    version_id: int
    version_name: str


class ChartStackedResponseDto(BaseModel):
    categories: list[str] = Field(default_factory=list)
    series: list[ChartStackedSeriesDto] = Field(default_factory=list)
    matrix_headers: list[str] = Field(default_factory=list)
    matrix_rows: list[ChartStackedMatrixRowDto] = Field(default_factory=list)
    resolved_versions: list[ChartStackedResolvedVersionDto] = Field(default_factory=list)
    note: str | None = None


class ChartPptSeriesDto(BaseModel):
    name: str
    values: list[float] = Field(default_factory=list)


class ChartPptMatrixRowDto(BaseModel):
    label: str
    values: list[str] = Field(default_factory=list)


class ChartPptExportRequestDto(BaseModel):
    chart_type: str
    title: str
    subtitle: str | None = None
    categories: list[str] = Field(default_factory=list)
    series: list[ChartPptSeriesDto] = Field(default_factory=list)
    matrix_headers: list[str] = Field(default_factory=list)
    matrix_rows: list[ChartPptMatrixRowDto] = Field(default_factory=list)

    @field_validator("chart_type")
    @classmethod
    def chart_type_allowed(cls, v: str) -> str:
        text = (v or "").strip().lower()
        if text not in {"bar", "stacked", "line", "pie", "doughnut"}:
            raise ValueError("chart_type 仅支持 bar/stacked/line/pie/doughnut")
        return text


class SystemDatabaseRow(BaseModel):
    id: int
    data_file_name: str
    year: int
    create_time: str
    file_path: str


class SystemVersionRow(BaseModel):
    version_id: int
    version_name: str
    version_date_time: str
    current_month: int


class EditShowVersionSelection(BaseModel):
    level: int
    data_file_id: int
    version_id: int

    @field_validator("level")
    @classmethod
    def level_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("level 必须在 1-5")
        return v


class EditVersionSelection(BaseModel):
    data_file_id: int
    version_id: int


class EditShowVersionState(BaseModel):
    edit: EditVersionSelection | None = None
    shows: list[EditShowVersionSelection] = Field(default_factory=list)


class EditShowVersionSaveRequest(BaseModel):
    edit: EditVersionSelection | None = None
    shows: list[EditShowVersionSelection] = Field(default_factory=list)


class SystemPeriodYearDto(BaseModel):
    year: int


class SystemDatabaseCreateRequest(BaseModel):
    year: int
    first_version_name: str

    @field_validator("year")
    @classmethod
    def year_range(cls, v: int) -> int:
        if v < 2000 or v > 2999:
            raise ValueError("year 必须是 4 位年份")
        return v

    @field_validator("first_version_name")
    @classmethod
    def first_version_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("first_version_name 不能为空")
        return text


class SystemVersionCreateRequest(BaseModel):
    version_name: str
    parent_version_id: int | None = None
    current_month: int = 1

    @field_validator("version_name")
    @classmethod
    def version_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("version_name 不能为空")
        return text

    @field_validator("current_month")
    @classmethod
    def current_month_range(cls, v: int) -> int:
        if v < 1 or v > 13:
            raise ValueError("current_month 必须在 1-13")
        return v


class SystemVersionPatchRequest(BaseModel):
    """仅允许修改版本名称；版本 ID、创建时间、current_month 不可通过此接口修改。"""

    version_name: str

    @field_validator("version_name")
    @classmethod
    def version_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("version_name 不能为空")
        return text


class SystemUserRow(BaseModel):
    id: int
    user_name: str
    permission_type: int
    first_login_flag: int
    create_time: str
    update_time: str | None = None


class FeishuBindingRow(BaseModel):
    open_id: str
    user_id: int
    user_name: str
    create_time: str


class FeishuBindingUpsertRequest(BaseModel):
    open_id: str
    user_id: int

    @field_validator("open_id")
    @classmethod
    def open_id_strip(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("open_id 不能为空")
        return t


class SystemUserCreateRequest(BaseModel):
    user_name: str
    first_login_password: str
    permission_type: int

    @field_validator("user_name")
    @classmethod
    def user_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("user_name 不能为空")
        return text

    @field_validator("permission_type")
    @classmethod
    def permission_type_range(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("permission_type 必须为 1/2/3")
        return v


class SystemUserUpdateRequest(BaseModel):
    user_name: str | None = None
    permission_type: int | None = None

    @field_validator("user_name")
    @classmethod
    def user_name_optional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        text = v.strip()
        if not text:
            raise ValueError("user_name 不能为空")
        return text

    @field_validator("permission_type")
    @classmethod
    def permission_type_optional(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v not in (1, 2, 3):
            raise ValueError("permission_type 必须为 1/2/3")
        return v


class SystemUserPasswordResetRequest(BaseModel):
    first_login_password: str


class SystemUserFirstLoginFlagRequest(BaseModel):
    first_login_flag: int

    @field_validator("first_login_flag")
    @classmethod
    def first_login_flag_range(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("first_login_flag 必须为 0/1")
        return v


class ProductTypeRow(BaseModel):
    product_code: str
    product_name: str
    parent_code: str | None = None
    level: int | None = 1
    remark: str | None = None


class ProductTypeCreate(BaseModel):
    product_code: str
    product_name: str
    parent_code: str | None = None
    level: int | None = 1
    remark: str | None = None

    @field_validator("product_code")
    @classmethod
    def code_fmt(cls, v: str) -> str:
        v = v.strip()
        import re

        if not re.match(r"^Z\d{4,8}$", v):
            raise ValueError("产品代码须为 Z + 4~8 位数字")
        return v

    @field_validator("product_name")
    @classmethod
    def name_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("产品名称不能为空")
        return v.strip()


class ProductTypeUpdate(BaseModel):
    product_name: str | None = None
    parent_code: str | None = None
    level: int | None = None
    remark: str | None = None


class ReportAccountRow(BaseModel):
    report_acct_code: str
    report_acct_name: str
    parent_code: str | None = None
    is_summary: bool
    is_minus: bool
    level: int
    is_leaf: bool
    remark: str | None = None


class ReportAccountCreate(BaseModel):
    report_acct_code: str
    report_acct_name: str
    parent_code: str | None = None
    is_summary: bool = True
    is_minus: bool = False
    level: int
    is_leaf: bool = False
    remark: str | None = None

    @field_validator("report_acct_code")
    @classmethod
    def report_code_fmt(cls, v: str) -> str:
        v = v.strip()
        import re

        if not re.match(r"^[A-Z]\d+$", v):
            raise ValueError("报告科目代码须为大写字母开头 + 数字")
        return v

    @field_validator("report_acct_name")
    @classmethod
    def report_name_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("报告科目名称不能为空")
        return v.strip()


class ReportAccountUpdate(BaseModel):
    report_acct_name: str | None = None
    parent_code: str | None = None
    is_summary: bool | None = None
    is_minus: bool | None = None
    level: int | None = None
    is_leaf: bool | None = None
    remark: str | None = None


class ReportDataMappingRow(BaseModel):
    report_acct_code: str
    data_acct_code: str


class ReportDataMappingCreate(BaseModel):
    report_acct_code: str
    data_acct_code: str


class DeptAccountRow(BaseModel):
    dept_code: str
    dept_name: str
    parent_code: str | None = None
    level: int
    is_leaf: bool


class DeptAccountCreate(BaseModel):
    dept_code: str
    dept_name: str
    parent_code: str | None = None
    level: int
    is_leaf: bool = False

    @field_validator("dept_code")
    @classmethod
    def dept_code_fmt(cls, v: str) -> str:
        v = v.strip()
        import re

        if not re.match(r"^Y\d+$", v):
            raise ValueError("部门代码须为 Y 开头 + 数字")
        return v

    @field_validator("dept_name")
    @classmethod
    def dept_name_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("部门名称不能为空")
        return v.strip()


class DeptAccountUpdate(BaseModel):
    dept_name: str | None = None
    parent_code: str | None = None
    level: int | None = None
    is_leaf: bool | None = None


class DeptProductMappingRow(BaseModel):
    dept_code: str
    product_code: str


class DeptProductMappingCreate(BaseModel):
    dept_code: str
    product_code: str


class AgentKbContextRequest(BaseModel):
    query: str
    top_k: int = 5


class AgentKbContextResponse(BaseModel):
    query: str
    matches: dict
    analysis_template_excerpt: str


class AgentKbStatsResponse(BaseModel):
    knowledge_base_root: str
    exists: bool
    files: dict
    counts: dict
    build_report: dict


class AgentChatMessage(BaseModel):
    role: str
    content: str
    dialogue_id: int | None = None


class AgentReplyOption(BaseModel):
    """助手给出的可点击后续动作（由前端执行）。"""

    id: str
    label: str


class AgentPivotSuggestion(BaseModel):
    """透视表字段建议（与前端 Pivot 字段 ID 对齐）。
    pivot_search_text：仅报告/数据科目 code，由前端透视搜索框作 OR 过滤。"""

    row_field_ids: list[str] = Field(default_factory=list)
    column_field_ids: list[str] = Field(default_factory=list)
    page_field_ids: list[str] = Field(default_factory=list)
    value_field_ids: list[str] = Field(default_factory=list)
    page_selections: dict[str, str] = Field(default_factory=dict)
    pivot_search_text: str = ""
    explanation: str = ""
    confidence: float = 0.0


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentChatMessage] = Field(default_factory=list)
    top_k: int = 5
    last_dialogue_id: int | None = None
    pending_query_spec: dict | None = None


class AgentChatResponse(BaseModel):
    reply: str
    intent_type: str
    next_action: str
    need_clarification: bool
    missing_slots: list[str]
    clarification_options: dict[str, list[str]] = Field(default_factory=dict)
    assumptions: list[str]
    suggested_sql: str | None = None
    kb_context: dict
    executed: bool = False
    result_row_count: int = 0
    result_preview: list[dict] = Field(default_factory=list)
    memory_id: str | None = None
    reply_options: list[AgentReplyOption] = Field(default_factory=list)
    open_pivot_table: bool = False
    pivot_suggestion: AgentPivotSuggestion | None = None
    dialogue_id: int = 1
    pending_query_spec: dict | None = None


class AgentFeedbackRequest(BaseModel):
    memory_id: str
    satisfied: bool
    comment: str | None = None


class AgentFeedbackResponse(BaseModel):
    updated: bool
    memory_id: str


class AgentFileParseResponse(BaseModel):
    filename: str
    file_type: str
    char_count: int
    summary: str
    key_points: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── 预算预测驱动模块 ──

class DriverCategoryRow(BaseModel):
    category_code: str
    category_name: str
    sort_order: int = 0


class DriverIndicatorRow(BaseModel):
    indicator_code: str
    category_code: str
    indicator_name: str
    value_type: str
    data_acct_code: str | None = None
    has_product_detail: int = 0
    has_monthly_detail: int = 1
    sort_order: int = 0


class DriverProductRow(BaseModel):
    id: int
    indicator_code: str
    product_code: str
    product_name: str | None = None
    sort_order: int = 0
    data_accounts: list["DriverMappedDataAccount"] = Field(default_factory=list)


class DriverMappedDataAccount(BaseModel):
    data_acct_code: str
    data_acct_name: str
    value_type: str
    report_code: str | None = None
    report_path: list[str] = Field(default_factory=list)
    actual_values: list[float] = Field(default_factory=list)
    sort_order: int = 0


class DriverDataAccountOption(BaseModel):
    data_acct_code: str
    data_acct_name: str
    value_type: str
    product_codes: str | None = None
    report_code: str | None = None
    report_path: list[str] = Field(default_factory=list)


class DriverAccountMappingUpsert(BaseModel):
    indicator_code: str
    category_code: str | None = None
    product_code: str
    data_acct_code: str
    sort_order: int = 0


class DriverCategoryTree(BaseModel):
    """前端加载用：分类→指标→产品 的树形结构"""
    category_code: str
    category_name: str
    current_month: int = 1
    sort_order: int = 0
    indicators: list["DriverIndicatorTree"] = Field(default_factory=list)


class DriverIndicatorTree(BaseModel):
    indicator_code: str
    indicator_name: str
    value_type: str
    data_acct_code: str | None = None
    has_product_detail: int = 0
    has_monthly_detail: int = 1
    sort_order: int = 0
    products: list[DriverProductRow] = Field(default_factory=list)


class DriverImportMonthlyItem(BaseModel):
    month: str  # "M01" ~ "M12"
    value: float


class DriverImportRequest(BaseModel):
    """单行导入（前端直接提交），或 Excel 解析后的结构"""
    indicator_code: str
    product_code: str | None = None
    data_acct_code: str | None = None
    monthly_values: list[DriverImportMonthlyItem] = Field(default_factory=list)


class DriverImportResponse(BaseModel):
    version_id: int
    budget_year: int
    saved_cells: int
    summary: dict = Field(default_factory=dict)  # { profit, dividend, retained, ... }
    monthly: list[dict] = Field(default_factory=list)  # [{ month, values... }]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── 智能报告模块 ──

ReportVariableType = Literal["metric", "formula", "calc", "parameter", "text", "table", "chart", "analysis"]


class SmartReportTemplateRow(BaseModel):
    template_id: int
    template_code: str
    template_name: str
    template_type: str = "analysis"
    status: str = "active"
    version_no: int = 1
    remark: str | None = None
    created_at: str
    updated_at: str
    variable_count: int = 0


class SmartReportTemplateCreateResponse(BaseModel):
    template: SmartReportTemplateRow
    placeholders: list[str] = Field(default_factory=list)


class SmartReportTextTemplateCreate(BaseModel):
    template_code: str
    template_name: str
    content: str
    template_type: str = "analysis"
    remark: str | None = None

    @field_validator("template_code", "template_name", "content")
    @classmethod
    def text_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("模板编码、名称和内容不能为空")
        return text


class SmartReportCalcMetricComponent(BaseModel):
    alias: str
    data_acct_code: str
    data_acct_name: str | None = None

    @field_validator("alias", "data_acct_code")
    @classmethod
    def calc_component_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("计算指标组成项不能为空")
        return text


class SmartReportCalcMetricRow(BaseModel):
    metric_code: str
    metric_name: str
    expression: str
    components: list[SmartReportCalcMetricComponent] = Field(default_factory=list)
    value_type: str = "金额"
    format_type: str = "number"
    remark: str | None = None
    created_at: str
    updated_at: str


class SmartReportCalcMetricUpsert(BaseModel):
    metric_code: str
    metric_name: str
    expression: str
    components: list[SmartReportCalcMetricComponent] = Field(default_factory=list)
    value_type: str = "金额"
    format_type: str = "number"
    remark: str | None = None

    @field_validator("metric_code", "metric_name", "expression")
    @classmethod
    def calc_metric_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("计算指标编码、名称和表达式不能为空")
        return text


class SmartReportTemplateVariableRow(BaseModel):
    variable_id: int
    template_id: int
    variable_key: str
    variable_name: str
    variable_type: ReportVariableType
    binding_config: dict = Field(default_factory=dict)
    display_order: int = 0
    created_at: str
    updated_at: str


class SmartReportTemplateVariableUpsert(BaseModel):
    variable_key: str
    variable_name: str | None = None
    variable_type: ReportVariableType | None = None
    binding_config: dict = Field(default_factory=dict)
    display_order: int = 0

    @field_validator("variable_key")
    @classmethod
    def variable_key_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("变量 key 不能为空")
        return text


class SmartReportGenerateRequest(BaseModel):
    template_id: int
    instance_name: str | None = None
    report_id: int | None = None
    parameters: dict = Field(default_factory=dict)
    text_values: dict = Field(default_factory=dict)


class SmartReportPreviewRequest(BaseModel):
    template_id: int
    parameters: dict = Field(default_factory=dict)
    text_values: dict = Field(default_factory=dict)


class SmartReportPreviewResponse(BaseModel):
    preview_text: str
    resolved_values: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SmartReportGenerateResponse(BaseModel):
    instance_id: int
    job_id: int
    output_filename: str
    download_url: str
    generated_at: str
    resolved_values: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SmartReportInstanceRow(BaseModel):
    instance_id: int
    report_id: int | None = None
    template_id: int
    template_name: str | None = None
    instance_name: str
    generation_status: str
    output_file_path: str | None = None
    error_message: str | None = None
    last_generated_at: str | None = None
    last_refresh_at: str | None = None
    created_at: str
    updated_at: str


class DriverImportPreviewRow(BaseModel):
    sheet_name: str
    excel_row: int
    indicator_text: str
    product_text: str
    requested_data_acct_code: str | None = None
    matched_indicator_code: str | None = None
    matched_indicator_name: str | None = None
    matched_product_code: str | None = None
    resolved_data_acct_codes: list[str] = Field(default_factory=list)
    recognized_value_cells: int = 0
    status: str
    message: str | None = None


class DriverImportPreviewResponse(BaseModel):
    row_count: int
    ready_rows: int
    error_rows: int
    preview_rows: list[DriverImportPreviewRow] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
