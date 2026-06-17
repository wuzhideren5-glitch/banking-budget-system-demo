from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

class RuntimeMetricRefRow(BaseModel):
    data_acct_code: str
    data_acct_name: str
    metric_node_code: str | None = None
    metric_node_name: str | None = None
    scope_type: str | None = None
    scope_code: str | None = None
    budget_formula: str | None = None
    actual_formula: str | None = None
    need_calc: int = 0
    formula_calc_mode: int = Field(default=0, ge=0, le=3)
    allow_manual_entry: int = Field(default=1, ge=0, le=1)
    budget_rule_code: str | None = None
    budget_rule_config_json: str | None = None
    value_type: str
    remark: str | None = None
    product_name: str | None = None
    has_budget_data_records: bool = False
    budget_data_ref_count: int = 0
    metric_binding_ref_count: int = 0
    org_product_metric_ref_count: int = 0

    @computed_field
    @property
    def metric_code(self) -> str:
        return self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str:
        return self.data_acct_name

    @computed_field
    @property
    def product_display(self) -> str:
        scope = (self.scope_code or "").strip().upper()
        if scope == "CORP":
            return "全行"
        if self.product_name:
            return f"{scope}-{self.product_name}" if scope else self.product_name
        return scope or "未绑定范围"


class BudgetOutputDisplayCandidateDto(BaseModel):
    candidate_key: str | None = None
    data_acct_code: str
    data_acct_name: str
    metric_node_code: str
    metric_node_name: str
    scope_type: str
    scope_code: str
    scope_name: str | None = None
    value_type: str
    source_type: str = "org_product_runtime_ref"
    source_label: str = "机构及产品指标编码"
    source_ref: str | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None
    selected: bool = False

    @computed_field
    @property
    def metric_code(self) -> str:
        return self.org_product_metric_code or self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str:
        return self.org_product_metric_name or self.data_acct_name


class BudgetOutputDisplayConfigItemDto(BaseModel):
    row_key: str
    display_view: str
    parent_row_key: str | None = None
    data_acct_code: str | None = None
    data_acct_name: str | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None
    row_type: str
    display_name: str
    metric_node_code: str | None = None
    metric_node_name: str | None = None
    source_scope_type: str | None = None
    source_scope_code: str | None = None
    scope_name: str | None = None
    value_type: str | None = None
    level: int = 1
    sort_order: int = 0
    is_active: int = 1

    @computed_field
    @property
    def metric_code(self) -> str | None:
        return self.org_product_metric_code or self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str | None:
        return self.org_product_metric_name or self.data_acct_name


class BudgetOutputDisplayConfigResponse(BaseModel):
    items: list[BudgetOutputDisplayConfigItemDto] = Field(default_factory=list)
    candidates: list[BudgetOutputDisplayCandidateDto] = Field(default_factory=list)


class BudgetOutputDisplayConfigImportResponse(BaseModel):
    mode: str
    saved_rows: int
    metric_rows: int
    group_rows: int


class BudgetOutputDisplayConfigCreate(BaseModel):
    data_acct_code: str | None = None
    display_name: str | None = None
    parent_row_key: str | None = None
    insert_after_row_key: str | None = None
    display_view: str = "TOTAL"
    sort_order: int | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None


class BudgetOutputDisplayConfigUpdate(BaseModel):
    data_acct_code: str | None = None
    display_name: str | None = None
    sort_order: int | None = None
    is_active: int | None = Field(default=None, ge=0, le=1)


class BudgetSubjectCatalogRow(BaseModel):
    id: int
    parent_id: int | None = None
    level_number: int
    level_label: str
    subject_name: str
    manage_department: str | None = None
    formula_text: str | None = None
    sort_order: int = 0
    is_leaf: bool = False


class BudgetSubjectCatalogCreate(BaseModel):
    parent_id: int | None = None
    subject_name: str
    manage_department: str | None = None
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
    manage_department: str | None = None
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
    import_kind: str = "current_year_actual"
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
    data_date: str = ""
    period_ym: str
    org_code: str = ""
    org_name: str = ""
    dep_code: str = ""
    dep_name: str = ""
    subject_code: str = ""
    subject_name: str = ""
    journal_name: str = ""
    serial_no: str = ""
    line_desc: str = ""
    fee_type_code: str = ""
    fee_type_name: str = ""
    bi_ai_source_code: str = ""
    bi_ai_source_name: str = ""
    manage_department_code: str = ""
    owner_name_raw: str
    monthly_caliber: str = ""
    owner_name_mapped: str | None = None
    budget_subject_raw: str
    budget_subject_mapped: str | None = None
    fee_major_mapped: str = ""
    fee_category_mapped: str = ""
    budget_release_caliber_mapped: str = ""
    manage_department2: str = ""
    special_control_tag: str = ""
    amount: float
    match_status: str
    match_note: str | None = None


class ExpenseActualImportManageDepartmentWarning(BaseModel):
    period_ym: str = ""
    owner_name_raw: str = ""
    budget_subject_mapped: str = ""
    budget_release_caliber_mapped: str = ""
    import_manage_department: str
    mapping_manage_department: str
    message: str


class ExpenseActualImportPreviewResponse(BaseModel):
    file_name: str
    row_count: int
    periods: list[str]
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    preview_rows: list[ExpenseActualImportPreviewRow]
    unmatched_preview_rows: list[ExpenseActualImportPreviewRow]
    manage_department_warnings: list[ExpenseActualImportManageDepartmentWarning] = Field(default_factory=list)


class ExpenseActualImportApplyResponse(BaseModel):
    batch_id: int
    import_kind: str = "current_year_actual"
    file_name: str
    import_mode: str
    row_count: int
    periods: list[str]
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    note: str | None = None
    manage_department_warnings: list[ExpenseActualImportManageDepartmentWarning] = Field(default_factory=list)


class ExpenseBudgetEntryPreviewRow(BaseModel):
    owner_name_raw: str
    owner_name_mapped: str | None = None
    budget_subject_raw: str
    budget_subject_mapped: str | None = None
    amount: float
    match_status: str
    match_note: str | None = None


class ExpenseBudgetEntryPreviewResponse(BaseModel):
    file_name: str
    budget_year: int
    amount_unit: str
    row_count: int
    matched_rows: int
    unmatched_rows: int
    preview_rows: list[ExpenseBudgetEntryPreviewRow]
    unmatched_preview_rows: list[ExpenseBudgetEntryPreviewRow]


class ExpenseBudgetEntryApplyResponse(BaseModel):
    batch_id: int
    budget_year: int
    file_name: str
    import_mode: str
    amount_unit: str
    row_count: int
    matched_rows: int
    unmatched_rows: int
    note: str | None = None


class ExpenseBudgetEntryBatchRow(BaseModel):
    id: int
    budget_year: int
    file_name: str
    import_mode: str
    total_rows: int
    matched_rows: int
    unmatched_rows: int
    created_at: str
    note: str | None = None


class ExpenseBudgetEntryRow(BaseModel):
    id: int
    batch_id: int
    budget_year: int
    owner_name_raw: str
    owner_name_mapped: str | None = None
    budget_subject_raw: str
    budget_subject_mapped: str | None = None
    amount: float
    adjustment_amount: float = 0.0
    adjusted_amount: float
    match_status: str
    match_note: str | None = None


class ExpenseBudgetEntryUpdateRequest(BaseModel):
    amount: float | None = None
    adjustment_amount: float | None = None


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


class BudgetFactPeriod(BaseModel):
    period_id: int
    month_label: str
    month_index: int
    editable: bool = True


class BudgetFactVersionOption(BaseModel):
    version_id: int
    version_name: str
    version_date_time: str | None = None
    current_month: int = 1


class BudgetSummaryRowDto(BaseModel):
    metric_level1: str | None = None
    metric_level2: str | None = None
    metric_level3: str | None = None
    metric_level4: str | None = None
    metric_level5: str | None = None
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
    value_source: str | None = None
    update_time: str | None = None


class BudgetSummaryExportPivotRequest(BaseModel):
    row_field_ids: list[str] = Field(default_factory=list)
    column_field_ids: list[str] = Field(default_factory=list)
    page_field_ids: list[str] = Field(default_factory=list)
    page_selections: dict[str, str] = Field(default_factory=dict)
    show_row_total: bool = True
    show_column_total: bool = True
    pivot_search_text: str = ""


class BudgetSummaryAggregateRequest(BaseModel):
    row_field_ids: list[str] = Field(default_factory=list)
    column_field_ids: list[str] = Field(default_factory=list)
    page_field_ids: list[str] = Field(default_factory=list)
    page_selections: dict[str, str] = Field(default_factory=dict)
    pivot_search_text: str = ""


class CompareSummaryRowDto(BaseModel):
    show_level: int
    data_file_id: int
    source_year: int
    source_version_id: int
    source_version_name: str | None = None
    metric_level1: str | None = None
    metric_level2: str | None = None
    metric_level3: str | None = None
    metric_level4: str | None = None
    metric_level5: str | None = None
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
    value_source: str | None = None
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


class BudgetOutputVersionDto(BaseModel):
    key: str
    label: str
    source: Literal["editable", "show", "budget", "forecast"]
    show_level: int | None = None
    year: int
    version_id: int
    version_name: str
    current_month: int
    selected_by_default: bool = False


class BudgetOutputProductNodeDto(BaseModel):
    product_code: str
    product_name: str
    parent_code: str | None = None
    level: int = 1
    children: list["BudgetOutputProductNodeDto"] = Field(default_factory=list)


class BudgetOutputReportNodeDto(BaseModel):
    row_key: str
    display_name: str
    parent_row_key: str | None = None
    level: int
    is_summary: bool = False
    is_minus: bool = False
    children: list["BudgetOutputReportNodeDto"] = Field(default_factory=list)


class BudgetOutputVersionMetricDto(BaseModel):
    annual_value: float = 0
    budget_value: float = 0
    variance_to_budget: float = 0
    monthly_values: list[float] = Field(default_factory=list)
    monthly_budget_values: list[float] = Field(default_factory=list)
    monthly_actual_values: list[float] = Field(default_factory=list)


class BudgetOutputReportRowDto(BaseModel):
    row_key: str
    display_name: str
    data_acct_code: str | None = None
    data_acct_name: str | None = None
    org_product_ref: str | None = None
    org_product_entity_code: str | None = None
    org_product_table_name: str | None = None
    org_product_metric_code: str | None = None
    org_product_metric_name: str | None = None
    metric_node_code: str | None = None
    metric_node_name: str | None = None
    source_scope_type: str | None = None
    source_scope_code: str | None = None
    source_scope_name: str | None = None
    budget_formula: str | None = None
    actual_formula: str | None = None
    formula_calc_mode: int = 0
    allow_manual_entry: int = 1
    value_type: str | None = None
    row_type: str = "METRIC"
    level: int
    parent_row_key: str | None = None
    is_summary: bool = False
    is_minus: bool = False
    values_by_version: dict[str, BudgetOutputVersionMetricDto] = Field(default_factory=dict)

    @computed_field
    @property
    def metric_code(self) -> str | None:
        return self.org_product_metric_code or self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str | None:
        return self.org_product_metric_name or self.data_acct_name


class BudgetOutputProductBlockDto(BaseModel):
    product_code: str
    product_name: str
    descendant_product_codes: list[str] = Field(default_factory=list)
    rows: list[BudgetOutputReportRowDto] = Field(default_factory=list)
    formula_dependency_rows: list[BudgetOutputReportRowDto] = Field(default_factory=list)


class BudgetOutputDisplayReportResponse(BaseModel):
    title: str
    unit_label: str = "元"
    available_years: list[int] = Field(default_factory=list)
    selected_year: int
    budget_version_id: int | None = None
    forecast_version_ids: list[int] = Field(default_factory=list)
    versions: list[BudgetOutputVersionDto] = Field(default_factory=list)
    selected_show_levels: list[int] = Field(default_factory=list)
    product_tree: list[BudgetOutputProductNodeDto] = Field(default_factory=list)
    report_tree: list[BudgetOutputReportNodeDto] = Field(default_factory=list)
    product_overview_tree: list[BudgetOutputReportNodeDto] = Field(default_factory=list)
    product_detail_tree: list[BudgetOutputReportNodeDto] = Field(default_factory=list)
    selected_products: list[BudgetOutputProductNodeDto] = Field(default_factory=list)
    total_rows: list[BudgetOutputReportRowDto] = Field(default_factory=list)
    total_formula_dependency_rows: list[BudgetOutputReportRowDto] = Field(default_factory=list)
    product_blocks: list[BudgetOutputProductBlockDto] = Field(default_factory=list)
    product_overview_blocks: list[BudgetOutputProductBlockDto] = Field(default_factory=list)
    product_detail_blocks: list[BudgetOutputProductBlockDto] = Field(default_factory=list)
    note: str = ""


class GlobalRefreshAnnualStatus(BaseModel):
    data_file_name: str
    year: int
    refresh_time_a: str | None = None


class GlobalRefreshStatusResponse(BaseModel):
    annual_items: list[GlobalRefreshAnnualStatus] = Field(default_factory=list)
    compare_refresh_time_b: str | None = None
    next_planned_refresh_time_c: str | None = None


class ChartMetricTreeNodeDto(BaseModel):
    metric_node_code: str
    metric_node_name: str
    is_summary: bool
    children: list["ChartMetricTreeNodeDto"] = Field(default_factory=list)


class ChartVersionItemDto(BaseModel):
    show_level: int
    data_file_id: int
    data_file_name: str
    year: int
    version_id: int
    version_name: str
    current_month: int


class ChartVersionOptionsResponseDto(BaseModel):
    options: list[ChartVersionItemDto] = Field(default_factory=list)


class ChartVersionSelectionDto(BaseModel):
    show_level: int
    data_file_id: int
    version_id: int


class ChartStackedRequestDto(BaseModel):
    metric_node_code: str
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

    metric_node_code: str
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


class OrgProductRuntimeProductRow(BaseModel):
    product_code: str
    product_name: str
    parent_code: str | None = None
    level: int | None = 1
    remark: str | None = None


class DeptAccountRow(BaseModel):
    dept_code: str
    dept_name: str
    entity_name: str = "微众银行"
    parent_code: str | None = None
    level: int
    is_leaf: bool


class DeptAccountCreate(BaseModel):
    dept_code: str
    dept_name: str
    entity_name: str = "微众银行"
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
    entity_name: str | None = None
    parent_code: str | None = None
    level: int | None = None
    is_leaf: bool | None = None


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
    pivot_search_text：仅机构及产品指标 code，由前端透视搜索框作 OR 过滤。"""

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


# ── 模拟测算模块 ──


class SimulationBaselineRequestItem(BaseModel):
    indicator_code: str
    product_code: str | None = None


class SimulationBaselineRow(BaseModel):
    indicator_code: str
    indicator_name: str
    product_code: str | None = None
    product_name: str | None = None
    value_type: str
    baseline_value: float
    source_data_acct_codes: list[str] = Field(default_factory=list)
    source_org_product_refs: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def source_metric_codes(self) -> list[str]:
        metric_codes = []
        for source_ref in self.source_org_product_refs:
            parts = str(source_ref or "").split(":")
            if len(parts) >= 3 and parts[2]:
                metric_codes.append(parts[2])
        return metric_codes or self.source_data_acct_codes


class SimulationInputItem(BaseModel):
    indicator_code: str
    product_code: str | None = None
    simulate_value: float


class SimulationResultRow(BaseModel):
    metric_group: str
    indicator_code: str
    indicator_name: str
    value_type: str
    baseline_2025: float
    baseline_2026: float
    simulation_2026: float


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


class SmartReportAIBlock(BaseModel):
    block_id: str
    block_type: str
    text: str = ""
    metrics: list[dict] = Field(default_factory=list)
    analysis_rule_nl: str | None = None
    structured_plan: dict = Field(default_factory=dict)
    confidence: float = 0.0


class SmartReportAIInspectionIssue(BaseModel):
    issue_type: str
    text: str
    suggested_action: str = ""
    candidates: list[dict] = Field(default_factory=list)
    rule_preview: str | None = None


class SmartReportAIInspectionResponse(BaseModel):
    filename: str
    model: str
    summary: str = ""
    blocks: list[SmartReportAIBlock] = Field(default_factory=list)
    issues: list[SmartReportAIInspectionIssue] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    raw_text_excerpt: str = ""
    warnings: list[str] = Field(default_factory=list)


class SmartReportBlueprintSaveRequest(BaseModel):
    blueprint_name: str
    inspection: SmartReportAIInspectionResponse

    @field_validator("blueprint_name")
    @classmethod
    def blueprint_name_required(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("蓝图名称不能为空")
        return text


class SmartReportBlueprintRow(BaseModel):
    blueprint_id: int
    blueprint_name: str
    source_filename: str
    status: str = "draft"
    issue_count: int = 0
    block_count: int = 0
    output_file_path: str | None = None
    last_generated_at: str | None = None
    created_at: str
    updated_at: str


class SmartReportBlueprintDetail(SmartReportBlueprintRow):
    inspection: SmartReportAIInspectionResponse


class SmartReportBlueprintPreviewResponse(BaseModel):
    blueprint_id: int
    preview_text: str
    issue_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SmartReportBlueprintGenerateResponse(BaseModel):
    blueprint_id: int
    output_filename: str
    download_url: str
    generated_at: str


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

    @computed_field
    @property
    def metric_code(self) -> str:
        return self.data_acct_code

    @computed_field
    @property
    def metric_name(self) -> str | None:
        return self.data_acct_name

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


class SmartPptSceneRow(BaseModel):
    scene_id: int
    scene_code: str
    scene_name: str
    scene_type: str = "board"
    description: str | None = None
    slide_template_json: dict = Field(default_factory=dict)
    default_params_json: dict = Field(default_factory=dict)
    sort_order: int = 0
    status: str = "active"
    created_at: str
    updated_at: str


class SmartPptChartConfigRow(BaseModel):
    config_id: int
    config_code: str
    chart_type: str
    metric_config_json: dict = Field(default_factory=dict)
    visual_config_json: dict = Field(default_factory=dict)
    remark: str | None = None
    created_at: str
    updated_at: str


class SmartPptSlidePreviewRow(BaseModel):
    slide_index: int
    slide_type: str
    title: str
    subtitle: str | None = None
    chart_type: str | None = None
    chart_title: str | None = None
    narrative: str | None = None
    metric_cards: list[dict] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    table_rows: list[list[str]] = Field(default_factory=list)


class SmartPptSceneDetailResponse(BaseModel):
    scene: SmartPptSceneRow
    slide_previews: list[SmartPptSlidePreviewRow] = Field(default_factory=list)


class SmartPptGenerateRequest(BaseModel):
    scene_id: int
    instance_name: str | None = None
    params: dict = Field(default_factory=dict)


class SmartPptPreviewRequest(BaseModel):
    scene_id: int
    params: dict = Field(default_factory=dict)
    slide_index: int | None = None


class SmartPptPreviewResponse(BaseModel):
    scene: SmartPptSceneRow
    slide_previews: list[SmartPptSlidePreviewRow] = Field(default_factory=list)


class SmartPptGenerateResponse(BaseModel):
    instance_id: int
    output_filename: str
    download_url: str
    generated_at: str
    slide_previews: list[SmartPptSlidePreviewRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SmartPptInstanceRow(BaseModel):
    instance_id: int
    scene_id: int
    scene_name: str | None = None
    instance_name: str
    parameter_values: dict = Field(default_factory=dict)
    generation_status: str
    output_file_path: str | None = None
    error_message: str | None = None
    last_generated_at: str | None = None
    created_at: str
    updated_at: str


class SmartPptTemplateObjectRow(BaseModel):
    object_id: str
    shape_id: int | None = None
    shape_name: str | None = None
    object_type: str
    text_excerpt: str | None = None
    chart_type: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None


class SmartPptTemplateSlideReportRow(BaseModel):
    slide_index: int
    title: str | None = None
    object_count: int = 0
    text_count: int = 0
    table_count: int = 0
    chart_count: int = 0
    picture_count: int = 0
    group_count: int = 0
    other_count: int = 0
    objects: list[SmartPptTemplateObjectRow] = Field(default_factory=list)


class SmartPptTemplateInspectResponse(BaseModel):
    template_file_name: str
    slide_count: int
    slide_width: int
    slide_height: int
    object_count: int = 0
    text_count: int = 0
    table_count: int = 0
    chart_count: int = 0
    picture_count: int = 0
    group_count: int = 0
    other_count: int = 0
    slides: list[SmartPptTemplateSlideReportRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SmartPptTemplateBindingConfigRow(BaseModel):
    object_id: str
    slide_index: int
    object_type: str
    binding_type: str = "ignore"
    target_key: str | None = None
    data_source: str | None = None
    chart_config_code: str | None = None
    metric_code: str | None = None
    org_product_metric_ref: str | None = None
    org_product_metric_name: str | None = None
    org_product_data_acct_code: str | None = None
    prompt: str | None = None
    enabled: bool = True
    notes: str | None = None


class SmartPptTemplateBindingConfigRequest(BaseModel):
    template_file_name: str
    bindings: list[SmartPptTemplateBindingConfigRow] = Field(default_factory=list)


class SmartPptTemplateBindingConfigResponse(BaseModel):
    template_file_name: str
    bindings: list[SmartPptTemplateBindingConfigRow] = Field(default_factory=list)
    updated_at: str | None = None


class SmartPptTemplateChartBlockRow(BaseModel):
    block_id: str
    block_name: str
    section: str | None = None
    slide_index: int
    chart_object_id: str
    chart_type: str | None = None
    nearby_title_object_id: str | None = None
    nearby_title: str | None = None
    default_chart_config_code: str | None = None
    binding: SmartPptTemplateBindingConfigRow


class SmartPptTemplateChartBlockResponse(BaseModel):
    template_file_name: str
    blocks: list[SmartPptTemplateChartBlockRow] = Field(default_factory=list)


class SmartPptTemplateGenerateRequest(BaseModel):
    template_file_name: str
    bindings: list[SmartPptTemplateBindingConfigRow] | None = None
    params: dict = Field(default_factory=dict)
    max_slides: int | None = None


class SmartPptTemplateGenerateResponse(BaseModel):
    output_filename: str
    download_url: str
    generated_at: str
    applied_count: int = 0
    slide_count: int = 0
    warnings: list[str] = Field(default_factory=list)
