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
    product_code: str | None = None
    applies_to_all_products: int = 0
    budget_formula: str | None = None
    actual_formula: str | None = None
    need_calc: int = 0
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
        if int(self.applies_to_all_products or 0) == 1:
            return "适用所有产品科目"
        if self.product_code and self.product_name:
            return f"{self.product_code}-{self.product_name}"
        if self.product_code:
            return self.product_code
        return ""


class DataAccountCreate(BaseModel):
    data_acct_code: str
    data_acct_name: str
    product_code: str | None = None
    applies_to_all_products: bool = False
    budget_formula: str | None = None
    actual_formula: str | None = None
    value_type: str = "金额"
    remark: str | None = None

    @field_validator("data_acct_code")
    @classmethod
    def code_fmt(cls, v: str) -> str:
        v = v.strip()
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
        pc = self.product_code.strip() if self.product_code else ""
        if self.applies_to_all_products:
            if pc:
                raise ValueError("选择「适用所有产品科目」时不应再指定产品代码")
        else:
            if not pc:
                raise ValueError("请选择具体产品科目，或选择「适用所有产品科目」")
        return self


class DataAccountUpdate(BaseModel):
    data_acct_code: str | None = None
    data_acct_name: str | None = None
    product_code: str | None = None
    applies_to_all_products: bool | None = None
    budget_formula: str | None = None
    actual_formula: str | None = None
    value_type: str | None = None
    remark: str | None = None
    confirm_product_scope_migration: bool | None = None
    expected_delete_count_total: int | None = None

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
    remark: str | None = None


class ProductTypeCreate(BaseModel):
    product_code: str
    product_name: str
    remark: str | None = None

    @field_validator("product_code")
    @classmethod
    def code_fmt(cls, v: str) -> str:
        v = v.strip()
        import re

        if not re.match(r"^Z\d{4}$", v):
            raise ValueError("产品代码须为 Z + 4 位数字")
        return v

    @field_validator("product_name")
    @classmethod
    def name_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("产品名称不能为空")
        return v.strip()


class ProductTypeUpdate(BaseModel):
    product_name: str | None = None
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
    entity_name: str = ""


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
