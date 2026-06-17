from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import expense_budget_execution_report_resolver as resolver_module


class ExpenseBudgetExecutionReportResolverTests(unittest.IsolatedAsyncioTestCase):
    def test_report_modes_and_perspectives_share_single_contract(self) -> None:
        from app.services import expense_budget_execution_export as export_module
        from app.services import expense_budget_execution_modes as mode_contract

        self.assertIs(resolver_module.DISPLAY_REPORT_MODES, mode_contract.DISPLAY_REPORT_MODES)
        self.assertIs(resolver_module.EXPORT_REPORT_MODES, mode_contract.EXPORT_REPORT_MODES)
        self.assertIs(export_module.EXPORT_REPORT_MODES, mode_contract.EXPORT_REPORT_MODES)
        self.assertIs(resolver_module.REPORT_PERSPECTIVES, mode_contract.REPORT_PERSPECTIVES)
        self.assertIs(export_module.REPORT_PERSPECTIVES, mode_contract.REPORT_PERSPECTIVES)

    def test_report_resolution_plan_centralizes_display_and_export_mode_selection(self) -> None:
        query_selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="query",
            perspective="owner_dept",
        )
        flat_selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="flat",
            perspective="group",
        )
        template_selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="template",
        )
        subject_selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="subject",
        )

        self.assertEqual(
            resolver_module.resolve_expense_budget_execution_report_plan(
                query_selection,
                surface="display",
            ).report_kind,
            "monthly",
        )
        self.assertEqual(
            resolver_module.resolve_expense_budget_execution_report_plan(
                query_selection,
                surface="export",
            ).report_kind,
            "monthly",
        )
        self.assertEqual(
            resolver_module.resolve_expense_budget_execution_report_plan(
                flat_selection,
                surface="export",
            ).report_kind,
            "query",
        )
        self.assertEqual(
            resolver_module.resolve_expense_budget_execution_report_plan(
                template_selection,
                surface="display",
            ).report_kind,
            "template",
        )
        self.assertEqual(
            resolver_module.resolve_expense_budget_execution_report_plan(
                subject_selection,
                surface="export",
            ).report_kind,
            "subject",
        )

    def test_report_resolution_plan_rejects_unknown_surface(self) -> None:
        selection = resolver_module.ExpenseBudgetExecutionReportSelection()

        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "未知费用预算执行报表用途: preview",
        ):
            resolver_module.resolve_expense_budget_execution_report_plan(
                selection,
                surface="preview",
            )

    def test_report_resolution_plan_rejects_unknown_mode(self) -> None:
        selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="legacy",
        )

        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "未知费用预算执行报表模式: legacy",
        ):
            resolver_module.resolve_expense_budget_execution_report_plan(
                selection,
                surface="export",
            )

    def test_report_resolution_plan_rejects_query_perspective_before_runtime_loading(self) -> None:
        selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="query",
            perspective="budget_dept",
        )

        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "perspective 仅支持 entity、group 或 owner_dept",
        ):
            resolver_module.resolve_expense_budget_execution_report_plan(
                selection,
                surface="display",
            )

    async def test_planned_report_payload_rejects_unknown_report_kind(self) -> None:
        selection = resolver_module.ExpenseBudgetExecutionReportSelection()
        plan = resolver_module.ExpenseBudgetExecutionReportResolutionPlan(
            report_kind="legacy-monthly",
        )

        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "未知费用预算执行报表模式: legacy-monthly",
        ):
            await resolver_module.resolve_report_payload_from_plan(
                editable_context_provider=AsyncMock(),
                selection=selection,
                plan=plan,
            )

    def test_monthly_note_parts_centralizes_monthly_scope_note(self) -> None:
        class ScopeContext:
            include_permission_note: bool | None = None

            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                self.include_permission_note = include_permission_note
                return ["当前主体筛选：微众银行。"]

        scope_context = ScopeContext()
        scoped = SimpleNamespace(scope_context=scope_context)

        note_parts = resolver_module.build_monthly_note_parts(
            scoped=scoped,
            actual_source_mode="source",
        )

        self.assertFalse(scope_context.include_permission_note)
        self.assertEqual(
            note_parts,
            [
                "月报格式按费用报表执行模版拆分为多个区块展示，第一部分沿用部门模式的预算科目树。",
                "第二至第五部分按当前筛选范围内数据展示，并默认隐藏全零行。",
                "当前主体筛选：微众银行。",
                "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。",
            ],
        )

    def test_template_note_parts_centralizes_template_scope_note(self) -> None:
        class ScopeContext:
            include_permission_note: bool | None = None

            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                self.include_permission_note = include_permission_note
                return ["当前费用归属部门筛选：产品一室。"]

        scope_context = ScopeContext()
        scoped = SimpleNamespace(scope_context=scope_context)

        note_parts = resolver_module.build_template_note_parts(
            scoped=scoped,
            actual_source_mode="source",
        )

        self.assertFalse(scope_context.include_permission_note)
        self.assertEqual(
            note_parts,
            [
                "部门模式按“部门预算科目”层级展示费用类型，支持逐层展开、收起和右键操作。",
                "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。",
                "当前费用归属部门筛选：产品一室。",
                "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。",
            ],
        )

    def test_subject_note_parts_centralizes_subject_mode_note(self) -> None:
        note_parts = resolver_module.build_subject_note_parts(
            actual_source_mode="source",
        )

        self.assertEqual(
            note_parts,
            [
                "科目模式按表头选定的预算科目，在“部门科目维护树”上展示主体、事业群、费用归属部门的费用分布。",
                "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。",
                "选中父级预算科目时，会自动汇总该科目及全部下级科目金额；科目模式默认不按归口权限隐藏部门节点。",
                "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。",
            ],
        )

    def test_query_response_payload_centralizes_query_envelope_and_body(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="source",
            actual_source_file="runtime-actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        class ScopeContext:
            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                return ["当前主体筛选：微众银行。"]

            def payload_fields(self):
                return {"selected_entity_name": "微众银行"}

        scoped = SimpleNamespace(scope_context=ScopeContext())
        query_report = SimpleNamespace(rows=[{"name": "业务费用", "actual": 12.0}])

        payload = resolver_module.build_query_response_payload(
            runtime=runtime,
            scoped=scoped,
            perspective="entity",
            query_report=query_report,
        )

        self.assertEqual(
            payload,
            {
                "mode": "query",
                "budget_year": 2026,
                "version_id": 5,
                "version_name": "V5",
                "current_month": 4,
                "framework_source_mode": "framework-mode",
                "actual_source_mode": "source",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "runtime-actual.xlsx",
                "selected_entity_name": "微众银行",
                "perspective": "entity",
                "rows": query_report.rows,
                "note": (
                    "当前版本支持按“主体”“事业群”“费用归属部门”三种维度查询；预算部门维度已从报表中移除。 "
                    "当前主体筛选：微众银行。 "
                    "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。"
                ),
            },
        )

    def test_monthly_response_payload_centralizes_monthly_sources_and_body(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="source",
            actual_source_file="runtime-actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        class ScopeContext:
            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                return ["当前主体筛选：微众银行。"]

            def payload_fields(self):
                return {"selected_entity_name": "微众银行"}

        scoped = SimpleNamespace(scope_context=ScopeContext())
        template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="template-current.xlsx",
            previous_actual_source_file="template-prior.xlsx",
            has_imported_previous_actuals=False,
        )
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={},
            previous_actual_source_file="owner-prior.db",
        )
        template_report = SimpleNamespace(subject_tree=[{"id": 1, "label": "业务费用"}])
        monthly_sections = SimpleNamespace(
            business_rows=[{"name": "业务费用"}],
            it_rows=[{"name": "IT费用"}],
            managed_blocks=[{"title": "日常费用"}],
            daily_other_columns=["1月"],
            daily_other_rows=[{"name": "其他"}],
        )

        payload = resolver_module.build_monthly_response_payload(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            owner_prior_actual=owner_prior_actual,
            template_report=template_report,
            monthly_sections=monthly_sections,
        )

        self.assertEqual(
            payload,
            {
                "mode": "query",
                "budget_year": 2026,
                "version_id": 5,
                "version_name": "V5",
                "current_month": 3,
                "framework_source_mode": "framework-mode",
                "actual_source_mode": "source",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "template-current.xlsx",
                "previous_actual_source_file": "owner-prior.db",
                "selected_entity_name": "微众银行",
                "template_title": "2026年3月费用统计表",
                "subject_tree": template_report.subject_tree,
                "monthly_business_rows": monthly_sections.business_rows,
                "monthly_it_rows": monthly_sections.it_rows,
                "monthly_daily_managed_blocks": monthly_sections.managed_blocks,
                "monthly_daily_other_columns": monthly_sections.daily_other_columns,
                "monthly_daily_other_rows": monthly_sections.daily_other_rows,
                "consistency_warnings": [],
                "note": (
                    "月报格式按费用报表执行模版拆分为多个区块展示，第一部分沿用部门模式的预算科目树。 "
                    "第二至第五部分按当前筛选范围内数据展示，并默认隐藏全零行。 "
                    "当前主体筛选：微众银行。 "
                    "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。"
                ),
            },
        )

    def test_monthly_report_consistency_warnings_compare_same_metric_across_reports(self) -> None:
        template_report = SimpleNamespace(
            subject_tree=[
                {
                    "subject_name": "业务费用",
                    "level_number": 1,
                    "current_actual": 100.0,
                    "annual_budget": 200.0,
                    "budget_progress": 0.5,
                    "yoy_change": 10.0,
                    "yoy_rate": 0.1,
                    "month_over_month": 5.0,
                    "month_over_month_rate": 0.05,
                    "last_year_actual": 90.0,
                    "children": [],
                }
            ]
        )
        monthly_sections = SimpleNamespace(
            business_rows=[
                {
                    "subject_name": "业务费用合计",
                    "level": 0,
                    "current_actual": 100.0,
                    "annual_budget": 210.0,
                    "budget_progress": 0.476190,
                    "yoy_change": 10.0,
                    "yoy_rate": 0.1,
                    "month_over_month": 5.0,
                    "month_over_month_rate": 0.05,
                    "last_year_actual": 90.0,
                }
            ],
            it_rows=[],
            managed_blocks=[],
            daily_other_columns=[],
            daily_other_rows=[],
        )

        warnings = resolver_module.build_monthly_report_consistency_warnings(
            template_report=template_report,
            monthly_sections=monthly_sections,
        )

        self.assertEqual(len(warnings), 2)
        self.assertEqual(warnings[0]["metric_name"], "业务费用")
        self.assertIn(warnings[0]["field"], {"annual_budget", "budget_progress"})
        self.assertTrue(any(item["field"] == "annual_budget" for item in warnings))
        self.assertTrue(any(item["field"] == "budget_progress" for item in warnings))

    def test_template_response_payload_centralizes_template_sources_and_body(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="source",
            actual_source_file="runtime-actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        class ScopeContext:
            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                return ["当前费用归属部门筛选：产品一室。"]

            def payload_fields(self):
                return {"selected_owner_dept": "产品一室"}

        scoped = SimpleNamespace(scope_context=ScopeContext())
        template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="template-current.xlsx",
            previous_actual_source_file="template-prior.xlsx",
            has_imported_previous_actuals=True,
        )
        template_report = SimpleNamespace(subject_tree=[{"id": 1, "label": "业务费用"}])

        payload = resolver_module.build_template_response_payload(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            template_report=template_report,
        )

        self.assertEqual(
            payload,
            {
                "mode": "template",
                "budget_year": 2026,
                "version_id": 5,
                "version_name": "V5",
                "current_month": 3,
                "framework_source_mode": "framework-mode",
                "actual_source_mode": "source",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "template-current.xlsx",
                "previous_actual_source_file": "template-prior.xlsx",
                "selected_owner_dept": "产品一室",
                "template_title": "2026年3月费用统计表",
                "subject_tree": template_report.subject_tree,
                "note": (
                    "部门模式按“部门预算科目”层级展示费用类型，支持逐层展开、收起和右键操作。 "
                    "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。 "
                    "当前费用归属部门筛选：产品一室。 "
                    "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。"
                ),
            },
        )

    def test_subject_response_payload_centralizes_subject_source_context_and_body(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="source",
            actual_source_file="runtime-actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        entity_context = SimpleNamespace(
            payload_fields=lambda: {"selected_entity_name": "微众银行"}
        )
        subject_context = SimpleNamespace(entity_context=entity_context)
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={},
            previous_actual_source_file="owner-prior.db",
        )
        subject_report = SimpleNamespace(
            selected_subject_id=12,
            subject_scope_tree=[{"id": "A01", "label": "产品部"}],
            subject_tree=[{"id": 1, "label": "业务费用"}],
        )

        payload = resolver_module.build_subject_response_payload(
            runtime=runtime,
            subject_context=subject_context,
            owner_prior_actual=owner_prior_actual,
            subject_report=subject_report,
        )

        self.assertEqual(
            payload,
            {
                "mode": "subject",
                "budget_year": 2026,
                "version_id": 5,
                "version_name": "V5",
                "current_month": 3,
                "framework_source_mode": "framework-mode",
                "actual_source_mode": "source",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "runtime-actual.xlsx",
                "previous_actual_source_file": "owner-prior.db",
                "selected_entity_name": "微众银行",
                "selected_subject_id": 12,
                "subject_scope_tree": subject_report.subject_scope_tree,
                "subject_title": "2026年3月预算科目报表",
                "subject_tree": subject_report.subject_tree,
                "note": (
                    "科目模式按表头选定的预算科目，在“部门科目维护树”上展示主体、事业群、费用归属部门的费用分布。 "
                    "本年实际取1月至当前月累计实际，本年预算取年度预算总额，去年同期取上一年度同月累计实际。 "
                    "选中父级预算科目时，会自动汇总该科目及全部下级科目金额；科目模式默认不按归口权限隐藏部门节点。 "
                    "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。"
                ),
            },
        )

    def test_query_note_parts_centralizes_query_scope_and_permission_note(self) -> None:
        class ScopeContext:
            include_permission_note: bool | None = None

            def selected_scope_note_parts(self, *, include_permission_note: bool = False):
                self.include_permission_note = include_permission_note
                return ["当前主体筛选：微众银行。"]

        scope_context = ScopeContext()
        scoped = SimpleNamespace(scope_context=scope_context)

        note_parts = resolver_module.build_query_note_parts(
            scoped=scoped,
            actual_source_mode="source",
        )

        self.assertTrue(scope_context.include_permission_note)
        self.assertEqual(
            note_parts,
            [
                "当前版本支持按“主体”“事业群”“费用归属部门”三种维度查询；预算部门维度已从报表中移除。",
                "当前主体筛选：微众银行。",
                "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。",
            ],
        )

    def test_runtime_report_response_payload_centralizes_runtime_envelope_fields(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="runtime-actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        payload = resolver_module.build_runtime_report_response_payload(
            runtime=runtime,
            mode="template",
            current_month=runtime.selected_month,
            actual_source_file="template-current.xlsx",
            previous_actual_source_file="template-prior.xlsx",
            note_parts=["部门模式说明。"],
            context_fields={"selected_entity_name": "微众银行"},
            body_fields={"subject_tree": []},
        )

        self.assertEqual(
            payload,
            {
                "mode": "template",
                "budget_year": 2026,
                "version_id": 5,
                "version_name": "V5",
                "current_month": 3,
                "framework_source_mode": "framework-mode",
                "actual_source_mode": "actual-mode",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "template-current.xlsx",
                "previous_actual_source_file": "template-prior.xlsx",
                "selected_entity_name": "微众银行",
                "subject_tree": [],
                "note": "部门模式说明。",
            },
        )

    def test_query_body_fields_centralizes_query_response_shape(self) -> None:
        query_report = SimpleNamespace(rows=[{"name": "业务费用", "actual": 12.0}])

        body_fields = resolver_module.build_query_body_fields(
            perspective="owner_dept",
            query_report=query_report,
        )

        self.assertEqual(
            body_fields,
            {
                "perspective": "owner_dept",
                "rows": query_report.rows,
            },
        )

    def test_subject_body_fields_centralizes_subject_response_shape(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        subject_report = SimpleNamespace(
            selected_subject_id=12,
            subject_scope_tree=[{"id": "A01", "label": "产品部"}],
            subject_tree=[{"id": 1, "label": "业务费用"}],
        )

        body_fields = resolver_module.build_subject_body_fields(
            runtime=runtime,
            subject_report=subject_report,
        )

        self.assertEqual(
            body_fields,
            {
                "selected_subject_id": 12,
                "subject_scope_tree": subject_report.subject_scope_tree,
                "subject_title": "2026年3月预算科目报表",
                "subject_tree": subject_report.subject_tree,
            },
        )

    def test_template_body_fields_centralizes_template_response_shape(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        template_report = SimpleNamespace(subject_tree=[{"id": 1, "label": "业务费用"}])

        body_fields = resolver_module.build_template_body_fields(
            runtime=runtime,
            template_report=template_report,
        )

        self.assertEqual(
            body_fields,
            {
                "template_title": "2026年3月费用统计表",
                "subject_tree": template_report.subject_tree,
            },
        )

    def test_monthly_body_fields_centralizes_monthly_response_shape(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        template_report = SimpleNamespace(subject_tree=[{"id": 1, "label": "业务费用"}])
        monthly_sections = SimpleNamespace(
            business_rows=[{"name": "业务费用"}],
            it_rows=[{"name": "IT费用"}],
            managed_blocks=[{"title": "日常费用"}],
            daily_other_columns=["预算科目", "本年实际"],
            daily_other_rows=[{"预算科目": "其他"}],
        )

        body_fields = resolver_module.build_monthly_body_fields(
            runtime=runtime,
            template_report=template_report,
            monthly_sections=monthly_sections,
        )

        self.assertEqual(
            body_fields,
            {
                "template_title": "2026年3月费用统计表",
                "subject_tree": template_report.subject_tree,
                "monthly_business_rows": monthly_sections.business_rows,
                "monthly_it_rows": monthly_sections.it_rows,
                "monthly_daily_managed_blocks": monthly_sections.managed_blocks,
                "monthly_daily_other_columns": monthly_sections.daily_other_columns,
                "monthly_daily_other_rows": monthly_sections.daily_other_rows,
                "consistency_warnings": [],
            },
        )

    def test_monthly_previous_actual_source_file_prefers_imported_template_actuals(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={},
            previous_actual_source_file="owner-prior-budget.db",
        )

        imported_template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="current-import.xlsx",
            previous_actual_source_file="prior-import.xlsx",
            has_imported_previous_actuals=True,
        )
        fallback_template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="current-import.xlsx",
            previous_actual_source_file="subject-prior-budget.db",
            has_imported_previous_actuals=False,
        )

        self.assertEqual(
            resolver_module.resolve_monthly_previous_actual_source_file(
                template_actual=imported_template_actual,
                owner_prior_actual=owner_prior_actual,
            ),
            "prior-import.xlsx",
        )
        self.assertEqual(
            resolver_module.resolve_monthly_previous_actual_source_file(
                template_actual=fallback_template_actual,
                owner_prior_actual=owner_prior_actual,
            ),
            "owner-prior-budget.db",
        )

    def test_subject_scope_report_centralizes_subject_read_model_inputs(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        subject_context = SimpleNamespace(
            subject_rows=[{"id": 1, "subject_name": "业务费用"}],
            selected_entity="微众银行",
        )
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={("A01 产品部", "业务费用"): [2.0] + [0.0] * 11},
            previous_actual_source_file="prior-owner.xlsx",
        )
        subject_report = object()

        with patch.object(
            resolver_module,
            "build_subject_report_model",
            return_value=subject_report,
        ) as subject_builder:
            result = resolver_module.build_subject_scope_report(
                runtime=runtime,
                subject_context=subject_context,
                owner_prior_actual=owner_prior_actual,
                selected_subject_id=12,
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, subject_report)
        subject_builder.assert_called_once_with(
            ctx=runtime.ctx,
            parsed=runtime.parsed,
            subject_rows=subject_context.subject_rows,
            actual_by_owner=runtime.actual_by_owner,
            budget_by_owner=runtime.budget_by_owner,
            previous_year_actual_by_owner_subject=owner_prior_actual.previous_year_actual_by_owner_subject,
            current_month=runtime.selected_month,
            selected_entity=subject_context.selected_entity,
            selected_subject_id=12,
            include_zero_rows=True,
            keyword="差旅",
        )

    def test_subject_report_payload_centralizes_subject_read_model_and_response_building(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        subject_context = SimpleNamespace(selected_entity="微众银行")
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={},
            previous_actual_source_file="owner-prior.xlsx",
        )
        subject_mode_context = resolver_module.SubjectModeReportContext(
            runtime=runtime,
            subject=subject_context,
            owner_prior_actual=owner_prior_actual,
        )
        subject_report = object()
        payload = {"mode": "subject", "subject_scope_tree": []}

        with (
            patch.object(
                resolver_module,
                "build_subject_scope_report",
                return_value=subject_report,
            ) as subject_builder,
            patch.object(
                resolver_module,
                "build_subject_response_payload",
                return_value=payload,
            ) as payload_builder,
        ):
            result = resolver_module.build_subject_report_payload(
                subject_mode_context=subject_mode_context,
                selected_subject_id=12,
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, payload)
        subject_builder.assert_called_once_with(
            runtime=runtime,
            subject_context=subject_context,
            owner_prior_actual=owner_prior_actual,
            selected_subject_id=12,
            include_zero_rows=True,
            keyword="差旅",
        )
        payload_builder.assert_called_once_with(
            runtime=runtime,
            subject_context=subject_context,
            owner_prior_actual=owner_prior_actual,
            subject_report=subject_report,
        )

    async def test_subject_report_rejects_non_positive_subject_id_before_runtime_loading(self) -> None:
        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "subject_id 仅支持正整数",
        ):
            await resolver_module.resolve_subject_report(
                editable_context_provider=AsyncMock(),
                keyword="差旅",
                subject_id=0,
            )

    async def test_subject_report_maps_non_numeric_subject_id_to_report_error(self) -> None:
        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "subject_id 仅支持正整数",
        ):
            await resolver_module.resolve_subject_report(
                editable_context_provider=AsyncMock(),
                keyword="差旅",
                subject_id="abc",
            )

    async def test_runtime_context_rejects_invalid_report_month_before_loading_sources(self) -> None:
        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "report_month 仅支持 1-12",
        ):
            await resolver_module.load_report_runtime_context(
                editable_context_provider=AsyncMock(),
                report_month=13,
            )

    async def test_runtime_context_maps_non_numeric_report_month_to_report_error(self) -> None:
        with self.assertRaisesRegex(
            resolver_module.ExpenseBudgetExecutionReportError,
            "report_month 仅支持 1-12",
        ):
            await resolver_module.load_report_runtime_context(
                editable_context_provider=AsyncMock(),
                report_month="abc",
            )

    async def test_display_report_payload_centralizes_router_mode_dispatch(self) -> None:
        editable_context_provider = AsyncMock(return_value=(Path("budget-2026.db"), 2026, 5))
        selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="template",
            keyword="差旅",
            include_zero_rows=True,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
            report_month=3,
        )
        payload = {"mode": "template", "subject_tree": []}

        with (
            patch.object(
                resolver_module,
                "resolve_template_report",
                new=AsyncMock(return_value=payload),
            ) as template_resolver,
            patch.object(
                resolver_module,
                "resolve_subject_report",
                new=AsyncMock(),
            ) as subject_resolver,
            patch.object(
                resolver_module,
                "resolve_monthly_report",
                new=AsyncMock(),
            ) as monthly_resolver,
        ):
            result = await resolver_module.resolve_display_report_payload(
                editable_context_provider=editable_context_provider,
                selection=selection,
            )

        self.assertIs(result, payload)
        template_resolver.assert_awaited_once_with(
            editable_context_provider=editable_context_provider,
            keyword="差旅",
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
            include_zero_rows=True,
            report_month=3,
        )
        subject_resolver.assert_not_awaited()
        monthly_resolver.assert_not_awaited()

    async def test_export_report_payload_centralizes_export_mode_dispatch(self) -> None:
        editable_context_provider = AsyncMock(return_value=(Path("budget-2026.db"), 2026, 5))
        selection = resolver_module.ExpenseBudgetExecutionReportSelection(
            mode="flat",
            perspective="owner_dept",
            keyword="差旅",
            include_zero_rows=True,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )
        payload = {"mode": "query", "rows": []}

        with (
            patch.object(
                resolver_module,
                "resolve_query_report",
                new=AsyncMock(return_value=payload),
            ) as query_resolver,
            patch.object(
                resolver_module,
                "resolve_monthly_report",
                new=AsyncMock(),
            ) as monthly_resolver,
            patch.object(
                resolver_module,
                "resolve_template_report",
                new=AsyncMock(),
            ) as template_resolver,
            patch.object(
                resolver_module,
                "resolve_subject_report",
                new=AsyncMock(),
            ) as subject_resolver,
        ):
            result = await resolver_module.resolve_export_report_payload(
                editable_context_provider=editable_context_provider,
                selection=selection,
            )

        self.assertIs(result, payload)
        query_resolver.assert_awaited_once_with(
            editable_context_provider=editable_context_provider,
            perspective="owner_dept",
            keyword="差旅",
            include_zero_rows=True,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )
        monthly_resolver.assert_not_awaited()
        template_resolver.assert_not_awaited()
        subject_resolver.assert_not_awaited()

    def test_query_rows_report_centralizes_query_read_model_inputs(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(
            subject_rows=[{"id": 1, "subject_name": "业务费用"}],
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        query_report = object()

        with patch.object(
            resolver_module,
            "build_query_report_model",
            return_value=query_report,
        ) as query_builder:
            result = resolver_module.build_query_rows_report(
                runtime=runtime,
                scoped=scoped,
                perspective="owner_dept",
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, query_report)
        query_builder.assert_called_once_with(
            ctx=runtime.ctx,
            subject_rows=scoped.subject_rows,
            actual_by_owner=runtime.actual_by_owner,
            budget_by_owner=runtime.budget_by_owner,
            perspective="owner_dept",
            selected_entity=scoped.selected_entity,
            selected_group=scoped.selected_group,
            selected_owner=scoped.selected_owner,
            keyword="差旅",
            include_zero_rows=True,
            current_month=runtime.current_month,
        )

    def test_query_report_payload_centralizes_query_read_model_and_response_building(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(selected_entity="微众银行")
        query_context = resolver_module.QueryReportContext(
            runtime=runtime,
            perspective="owner_dept",
            scoped=scoped,
        )
        query_report = object()
        payload = {"mode": "query", "rows": [{"name": "业务费用"}]}

        with (
            patch.object(
                resolver_module,
                "build_query_rows_report",
                return_value=query_report,
            ) as query_builder,
            patch.object(
                resolver_module,
                "build_query_response_payload",
                return_value=payload,
            ) as payload_builder,
        ):
            result = resolver_module.build_query_report_payload(
                query_context=query_context,
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, payload)
        query_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            perspective="owner_dept",
            include_zero_rows=True,
            keyword="差旅",
        )
        payload_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            perspective="owner_dept",
            query_report=query_report,
        )

    def test_monthly_sections_report_centralizes_monthly_read_model_inputs(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(
            subject_rows=[{"id": 1, "subject_name": "业务费用"}],
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        business_owner_actual = resolver_module.BusinessOwnerActualContext(
            runtime=runtime,
            current_actual_by_owner_subject={("A01 产品部", "业务费用"): [3.0] + [0.0] * 11},
            previous_year_actual_by_owner_subject={("A01 产品部", "业务费用"): [2.0] + [0.0] * 11},
            current_actual_source_file="business-current.xlsx",
            previous_actual_source_file="business-prior.xlsx",
        )
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={("A01 产品部", "业务费用"): [4.0] + [0.0] * 11},
            previous_actual_source_file="prior-owner.xlsx",
        )
        monthly_sections = object()

        with patch.object(
            resolver_module,
            "build_monthly_report_sections",
            return_value=monthly_sections,
        ) as monthly_builder:
            result = resolver_module.build_monthly_sections_report(
                runtime=runtime,
                scoped=scoped,
                business_owner_actual=business_owner_actual,
                owner_prior_actual=owner_prior_actual,
            )

        self.assertIs(result, monthly_sections)
        monthly_builder.assert_called_once_with(
            ctx=runtime.ctx,
            parsed=runtime.parsed,
            subject_rows=scoped.subject_rows,
            actual_by_owner=runtime.actual_by_owner,
            budget_by_owner=runtime.budget_by_owner,
            previous_year_actual_by_owner_subject=owner_prior_actual.previous_year_actual_by_owner_subject,
            business_actual_by_owner=business_owner_actual.current_actual_by_owner_subject,
            business_previous_year_actual_by_owner_subject=business_owner_actual.previous_year_actual_by_owner_subject,
            current_month=runtime.selected_month,
            selected_entity=scoped.selected_entity,
            selected_group=scoped.selected_group,
            selected_owner=scoped.selected_owner,
        )

    def test_monthly_report_payload_centralizes_monthly_read_models_and_response_building(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(selected_entity="微众银行")
        template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="current.xlsx",
            previous_actual_source_file="prior.xlsx",
            has_imported_previous_actuals=True,
        )
        business_owner_actual = resolver_module.BusinessOwnerActualContext(
            runtime=runtime,
            current_actual_by_owner_subject={},
            previous_year_actual_by_owner_subject={},
            current_actual_source_file="business-current.xlsx",
            previous_actual_source_file="business-prior.xlsx",
        )
        owner_prior_actual = resolver_module.OwnerPriorActualContext(
            runtime=runtime,
            previous_year_actual_by_owner_subject={},
            previous_actual_source_file="owner-prior.xlsx",
        )
        monthly_context = resolver_module.MonthlyReportContext(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            business_owner_actual=business_owner_actual,
            owner_prior_actual=owner_prior_actual,
        )
        template_report = object()
        monthly_sections = object()
        payload = {"mode": "query", "monthly_business_rows": []}

        with (
            patch.object(
                resolver_module,
                "build_template_subject_tree_report",
                return_value=template_report,
            ) as template_builder,
            patch.object(
                resolver_module,
                "build_monthly_sections_report",
                return_value=monthly_sections,
            ) as monthly_builder,
            patch.object(
                resolver_module,
                "build_monthly_response_payload",
                return_value=payload,
            ) as payload_builder,
        ):
            result = resolver_module.build_monthly_report_payload(
                monthly_context=monthly_context,
            )

        self.assertIs(result, payload)
        template_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            include_zero_rows=False,
            keyword="",
        )
        monthly_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            business_owner_actual=business_owner_actual,
            owner_prior_actual=owner_prior_actual,
        )
        payload_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            owner_prior_actual=owner_prior_actual,
            template_report=template_report,
            monthly_sections=monthly_sections,
        )

    def test_template_subject_tree_report_centralizes_template_read_model_inputs(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(
            subject_rows=[{"id": 1, "subject_name": "业务费用"}],
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={"业务费用": [1.0] + [0.0] * 11},
            previous_year_subject_monthly_totals={"业务费用": [2.0] + [0.0] * 11},
            previous_year_subject_totals={"业务费用": 2.0},
            current_actual_source_file="current.xlsx",
            previous_actual_source_file="prior.xlsx",
            has_imported_previous_actuals=True,
        )
        template_report = object()

        with patch.object(
            resolver_module,
            "build_template_report_model",
            return_value=template_report,
        ) as template_builder:
            result = resolver_module.build_template_subject_tree_report(
                runtime=runtime,
                scoped=scoped,
                template_actual=template_actual,
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, template_report)
        template_builder.assert_called_once_with(
            ctx=runtime.ctx,
            subject_rows=scoped.subject_rows,
            actual_by_owner=runtime.actual_by_owner,
            budget_by_owner=runtime.budget_by_owner,
            previous_year_subject_monthly_totals=template_actual.previous_year_subject_monthly_totals,
            previous_year_subject_totals=template_actual.previous_year_subject_totals,
            current_month=runtime.selected_month,
            current_subject_monthly_totals_override=template_actual.current_subject_monthly_totals,
            budget_subject_totals_override=template_actual.budget_subject_totals,
            selected_entity=scoped.selected_entity,
            selected_group=scoped.selected_group,
            selected_owner=scoped.selected_owner,
            include_zero_rows=True,
            keyword="差旅",
        )

    def test_template_report_payload_centralizes_template_read_model_and_response_building(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={("A01 产品部", "业务费用"): [1.0] + [0.0] * 11},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={("A01 产品部", "业务费用"): 100.0},
        )
        scoped = SimpleNamespace(selected_entity="微众银行")
        template_actual = resolver_module.TemplateActualContext(
            current_subject_monthly_totals={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_actual_source_file="current.xlsx",
            previous_actual_source_file="prior.xlsx",
            has_imported_previous_actuals=True,
        )
        template_context = resolver_module.TemplateReportContext(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
        )
        template_report = object()
        payload = {"mode": "template", "subject_tree": []}

        with (
            patch.object(
                resolver_module,
                "build_template_subject_tree_report",
                return_value=template_report,
            ) as template_builder,
            patch.object(
                resolver_module,
                "build_template_response_payload",
                return_value=payload,
            ) as payload_builder,
        ):
            result = resolver_module.build_template_report_payload(
                template_context=template_context,
                include_zero_rows=True,
                keyword="差旅",
            )

        self.assertIs(result, payload)
        template_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            include_zero_rows=True,
            keyword="差旅",
        )
        payload_builder.assert_called_once_with(
            runtime=runtime,
            scoped=scoped,
            template_actual=template_actual,
            template_report=template_report,
        )

    def test_report_title_centralizes_template_and_subject_title_text(self) -> None:
        self.assertEqual(
            resolver_module.build_report_title(
                title_kind="template",
                budget_year=2026,
                selected_month=5,
            ),
            "2026年5月费用统计表",
        )
        self.assertEqual(
            resolver_module.build_report_title(
                title_kind="monthly",
                budget_year=2026,
                selected_month=5,
            ),
            "2026年5月费用统计表",
        )
        self.assertEqual(
            resolver_module.build_report_title(
                title_kind="subject",
                budget_year=2026,
                selected_month=5,
            ),
            "2026年5月预算科目报表",
        )

    def test_report_note_parts_centralizes_missing_actual_import_note(self) -> None:
        base_parts = ["查询模式说明。"]
        scope_parts = ["当前主体筛选：微众银行。"]

        note_parts = resolver_module.build_report_note_parts(
            base_parts=base_parts,
            scope_parts=scope_parts,
            actual_source_mode="source",
        )

        self.assertEqual(
            note_parts,
            [
                "查询模式说明。",
                "当前主体筛选：微众银行。",
                "当前未检测到已导入的费用执行明细，请在“费用执行明细导入”中导入本年实际明细。",
            ],
        )
        self.assertEqual(base_parts, ["查询模式说明。"])
        self.assertEqual(scope_parts, ["当前主体筛选：微众银行。"])

    def test_report_note_parts_skips_missing_actual_import_note_for_imported_actuals(self) -> None:
        note_parts = resolver_module.build_report_note_parts(
            base_parts=["部门模式说明。"],
            actual_source_mode="import",
        )

        self.assertEqual(note_parts, ["部门模式说明。"])

    async def test_query_report_context_centralizes_perspective_validation_and_scoped_context(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        scoped = object()

        with patch.object(
            resolver_module,
            "load_scoped_report_context",
            new=AsyncMock(return_value=scoped),
        ) as scoped_loader:
            context = await resolver_module.load_query_report_context(
                runtime=runtime,
                perspective="owner_dept",
                entity_name="微众银行",
                group_name="个人金融事业群",
                owner_dept="A01 产品部",
            )

        self.assertIs(context.runtime, runtime)
        self.assertEqual(context.perspective, "owner_dept")
        self.assertIs(context.scoped, scoped)
        scoped_loader.assert_awaited_once_with(
            runtime=runtime,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )

    async def test_query_report_context_rejects_invalid_perspective_before_loading_scope(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )

        with (
            patch.object(
                resolver_module,
                "load_scoped_report_context",
                new=AsyncMock(),
            ) as scoped_loader,
            self.assertRaisesRegex(
                resolver_module.ExpenseBudgetExecutionReportError,
                "perspective 仅支持 entity、group 或 owner_dept",
            ),
        ):
            await resolver_module.load_query_report_context(
                runtime=runtime,
                perspective="budget_dept",
            )

        scoped_loader.assert_not_awaited()

    async def test_subject_mode_report_context_centralizes_subject_and_prior_actual_contexts(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        subject = object()
        owner_prior_actual = object()

        with (
            patch.object(
                resolver_module,
                "load_subject_report_context",
                new=AsyncMock(return_value=subject),
            ) as subject_loader,
            patch.object(
                resolver_module,
                "load_owner_prior_actual_context",
                new=AsyncMock(return_value=owner_prior_actual),
            ) as prior_loader,
        ):
            context = await resolver_module.load_subject_mode_report_context(
                runtime=runtime,
                entity_name="微众银行",
            )

        self.assertIs(context.runtime, runtime)
        self.assertIs(context.subject, subject)
        self.assertIs(context.owner_prior_actual, owner_prior_actual)
        subject_loader.assert_awaited_once_with(
            runtime=runtime,
            entity_name="微众银行",
        )
        prior_loader.assert_awaited_once_with(runtime=runtime)

    async def test_scoped_template_actual_context_centralizes_scoped_actual_loader_inputs(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        scoped = SimpleNamespace(
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        template_actual = object()

        with patch.object(
            resolver_module,
            "load_template_actual_context",
            new=AsyncMock(return_value=template_actual),
        ) as template_loader:
            result = await resolver_module.load_scoped_template_actual_context(
                runtime=runtime,
                scoped=scoped,
            )

        self.assertIs(result, template_actual)
        template_loader.assert_awaited_once_with(
            ctx=runtime.ctx,
            budget_db=runtime.budget_db,
            budget_year=runtime.budget_year,
            selected_month=runtime.selected_month,
            selected_entity=scoped.selected_entity,
            selected_group=scoped.selected_group,
            selected_owner=scoped.selected_owner,
            actual_source_file=runtime.actual_source_file,
        )

    async def test_template_report_context_centralizes_template_context_loading(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        scoped = SimpleNamespace(
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        template_actual = object()

        with (
            patch.object(
                resolver_module,
                "load_scoped_report_context",
                new=AsyncMock(return_value=scoped),
            ) as scoped_loader,
            patch.object(
                resolver_module,
                "load_scoped_template_actual_context",
                new=AsyncMock(return_value=template_actual),
            ) as template_loader,
        ):
            context = await resolver_module.load_template_report_context(
                runtime=runtime,
                entity_name="微众银行",
                group_name="个人金融事业群",
                owner_dept="A01 产品部",
            )

        self.assertIs(context.runtime, runtime)
        self.assertIs(context.scoped, scoped)
        self.assertIs(context.template_actual, template_actual)
        scoped_loader.assert_awaited_once_with(
            runtime=runtime,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )
        template_loader.assert_awaited_once_with(runtime=runtime, scoped=scoped)

    async def test_monthly_report_context_centralizes_monthly_context_loading(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        scoped = SimpleNamespace(
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        template_actual = object()
        business_owner_actual = object()
        owner_prior_actual = object()

        with (
            patch.object(
                resolver_module,
                "load_scoped_report_context",
                new=AsyncMock(return_value=scoped),
            ) as scoped_loader,
            patch.object(
                resolver_module,
                "load_scoped_template_actual_context",
                new=AsyncMock(return_value=template_actual),
            ) as template_loader,
            patch.object(
                resolver_module,
                "load_business_owner_actual_context",
                new=AsyncMock(return_value=business_owner_actual),
            ) as business_loader,
            patch.object(
                resolver_module,
                "load_owner_prior_actual_context",
                new=AsyncMock(return_value=owner_prior_actual),
            ) as prior_loader,
        ):
            context = await resolver_module.load_monthly_report_context(
                runtime=runtime,
                entity_name="微众银行",
                group_name="个人金融事业群",
                owner_dept="A01 产品部",
            )

        self.assertIs(context.runtime, runtime)
        self.assertIs(context.scoped, scoped)
        self.assertIs(context.template_actual, template_actual)
        self.assertIs(context.business_owner_actual, business_owner_actual)
        self.assertIs(context.owner_prior_actual, owner_prior_actual)
        scoped_loader.assert_awaited_once_with(
            runtime=runtime,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )
        template_loader.assert_awaited_once_with(runtime=runtime, scoped=scoped)
        business_loader.assert_awaited_once_with(runtime=runtime)
        prior_loader.assert_awaited_once_with(runtime=runtime)

    async def test_business_owner_actual_context_centralizes_imported_owner_caliber_loaders(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        current_by_owner = {("A01 产品部", "业务费用"): [1.0] + [0.0] * 11}
        prior_by_owner = {("A01 产品部", "业务费用"): [2.0] + [0.0] * 11}

        with patch.object(
            resolver_module,
            "load_imported_owner_caliber_monthly_totals",
            new=AsyncMock(
                side_effect=[
                    (current_by_owner, "current-owner-import.xlsx"),
                    (prior_by_owner, "prior-owner-import.xlsx"),
                ]
            ),
        ) as imported_owner_loader:
            context = await resolver_module.load_business_owner_actual_context(runtime=runtime)

        self.assertIs(context.runtime, runtime)
        self.assertEqual(context.current_actual_by_owner_subject, current_by_owner)
        self.assertEqual(context.previous_year_actual_by_owner_subject, prior_by_owner)
        self.assertEqual(context.current_actual_source_file, "current-owner-import.xlsx")
        self.assertEqual(context.previous_actual_source_file, "prior-owner-import.xlsx")
        imported_owner_loader.assert_any_await(runtime.ctx, "current_year_actual")
        imported_owner_loader.assert_any_await(runtime.ctx, "prior_year_actual")

    async def test_owner_prior_actual_context_centralizes_owner_actual_loader_and_source(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        prior_by_owner = {("A01 产品部", "业务费用"): [10.0] + [0.0] * 11}

        with patch.object(
            resolver_module,
            "load_previous_year_actual_by_owner_subject",
            new=AsyncMock(return_value=(prior_by_owner, "budget-2025.db")),
        ) as prior_loader:
            context = await resolver_module.load_owner_prior_actual_context(runtime=runtime)

        self.assertIs(context.runtime, runtime)
        self.assertEqual(context.previous_year_actual_by_owner_subject, prior_by_owner)
        self.assertEqual(context.previous_actual_source_file, "budget-2025.db")
        prior_loader.assert_awaited_once_with(runtime.ctx, runtime.budget_db, runtime.budget_year)

    async def test_subject_report_context_centralizes_entity_selection_and_subject_catalog(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        entity_context = SimpleNamespace(selected_entity="微众银行")
        subject_rows = [{"id": 9, "subject_name": "IT费用"}]

        with (
            patch.object(
                resolver_module,
                "build_report_entity_context",
                return_value=entity_context,
            ) as entity_builder,
            patch.object(
                resolver_module,
                "_load_budget_subject_catalog_rows",
                new=AsyncMock(return_value=subject_rows),
            ) as subject_loader,
        ):
            context = await resolver_module.load_subject_report_context(
                runtime=runtime,
                entity_name="微众银行",
            )

        self.assertIs(context.runtime, runtime)
        self.assertIs(context.entity_context, entity_context)
        self.assertEqual(context.subject_rows, subject_rows)
        self.assertEqual(context.selected_entity, "微众银行")
        entity_builder.assert_called_once_with(runtime.ctx, entity_name="微众银行")
        subject_loader.assert_awaited_once()

    async def test_scoped_report_context_centralizes_scope_selection_and_subject_catalog(self) -> None:
        runtime = resolver_module.ReportRuntimeContext(
            budget_db=Path("budget-2026.db"),
            budget_year=2026,
            version_id=5,
            ctx=object(),
            parsed=object(),
            framework_source_mode="framework-mode",
            framework_source_file="framework.xlsx",
            actual_by_owner={},
            actual_source_mode="actual-mode",
            actual_source_file="actual.xlsx",
            version_name="V5",
            current_month=4,
            selected_month=3,
            budget_by_owner={},
        )
        scope_context = SimpleNamespace(
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )
        subject_rows = [{"id": 1, "subject_name": "业务费用"}]

        with (
            patch.object(
                resolver_module,
                "build_report_scope_context",
                return_value=scope_context,
            ) as scope_builder,
            patch.object(
                resolver_module,
                "_load_budget_subject_catalog_rows",
                new=AsyncMock(return_value=subject_rows),
            ) as subject_loader,
        ):
            context = await resolver_module.load_scoped_report_context(
                runtime=runtime,
                entity_name="微众银行",
                group_name="个人金融事业群",
                owner_dept="A01 产品部",
            )

        self.assertIs(context.runtime, runtime)
        self.assertIs(context.scope_context, scope_context)
        self.assertEqual(context.subject_rows, subject_rows)
        self.assertEqual(context.selected_entity, "微众银行")
        self.assertEqual(context.selected_group, "个人金融事业群")
        self.assertEqual(context.selected_owner, "A01 产品部")
        scope_builder.assert_called_once_with(
            runtime.ctx,
            runtime.parsed,
            entity_name="微众银行",
            group_name="个人金融事业群",
            owner_dept="A01 产品部",
        )
        subject_loader.assert_awaited_once()

    async def test_report_runtime_context_centralizes_framework_actual_budget_and_month_selection(self) -> None:
        ctx = object()
        parsed = object()
        actual_by_owner = {("A01 产品部", "业务费用"): [1.0] + [0.0] * 11}
        budget_by_owner = {("A01 产品部", "业务费用"): 100.0}
        editable_context_provider = AsyncMock(return_value=(Path("budget-2026.db"), 2026, 5))

        with (
            patch.object(
                resolver_module,
                "_load_framework_context",
                new=AsyncMock(return_value=(ctx, "framework-mode", "framework.xlsx", parsed)),
            ) as framework_loader,
            patch.object(
                resolver_module,
                "_load_actual_rows",
                new=AsyncMock(return_value=({}, {}, actual_by_owner, "actual-mode", "actual.xlsx")),
            ) as actual_loader,
            patch.object(
                resolver_module,
                "_load_budget_rows",
                new=AsyncMock(return_value=("V5", 4, {}, {}, budget_by_owner)),
            ) as budget_loader,
        ):
            context = await resolver_module.load_report_runtime_context(
                editable_context_provider=editable_context_provider,
                report_month=3,
            )

        self.assertIs(context.ctx, ctx)
        self.assertIs(context.parsed, parsed)
        self.assertEqual(context.budget_db, Path("budget-2026.db"))
        self.assertEqual(context.budget_year, 2026)
        self.assertEqual(context.version_id, 5)
        self.assertEqual(context.version_name, "V5")
        self.assertEqual(context.current_month, 4)
        self.assertEqual(context.selected_month, 3)
        self.assertEqual(context.actual_by_owner, actual_by_owner)
        self.assertEqual(context.budget_by_owner, budget_by_owner)
        self.assertEqual(context.framework_source_mode, "framework-mode")
        self.assertEqual(context.actual_source_mode, "actual-mode")
        self.assertEqual(context.framework_source_file, "framework.xlsx")
        self.assertEqual(context.actual_source_file, "actual.xlsx")
        editable_context_provider.assert_awaited_once()
        framework_loader.assert_awaited_once()
        actual_loader.assert_awaited_once_with(ctx)
        budget_loader.assert_awaited_once_with(ctx, Path("budget-2026.db"), 5)

    def test_report_response_payload_centralizes_common_fields_and_note_assembly(self) -> None:
        payload = resolver_module.build_report_response_payload(
            mode="template",
            budget_year=2026,
            version_id=3,
            version_name="V3",
            current_month=5,
            framework_source_mode="snapshot",
            actual_source_mode="import",
            framework_source_file="framework.xlsx",
            actual_source_file="actual.xlsx",
            note_parts=["部门模式说明。", "当前主体筛选：微众银行。"],
            previous_actual_source_file="prior.xlsx",
            context_fields={"selected_entity_name": "微众银行"},
            body_fields={"template_title": "2026年5月费用统计表", "subject_tree": []},
        )

        self.assertEqual(
            payload,
            {
                "mode": "template",
                "budget_year": 2026,
                "version_id": 3,
                "version_name": "V3",
                "current_month": 5,
                "framework_source_mode": "snapshot",
                "actual_source_mode": "import",
                "framework_source_file": "framework.xlsx",
                "actual_source_file": "actual.xlsx",
                "previous_actual_source_file": "prior.xlsx",
                "selected_entity_name": "微众银行",
                "template_title": "2026年5月费用统计表",
                "subject_tree": [],
                "note": "部门模式说明。 当前主体筛选：微众银行。",
            },
        )

    async def test_template_actual_context_centralizes_imported_and_fallback_actuals(self) -> None:
        ctx = resolver_module.FrameworkContext()
        ctx.owner_to_entity["A01 产品部"] = "微众银行"
        ctx.owner_to_group["A01 产品部"] = "个人金融事业群"
        with (
            patch.object(
                resolver_module,
                "load_imported_owner_caliber_monthly_totals",
                new=AsyncMock(
                    side_effect=[
                        (
                            {
                                ("A01 产品部", "业务费用"): [1.111, None, 3.335],
                                ("T01 平台部", "业务费用"): [99.0, 99.0, 99.0],
                            },
                            "current-import.xlsx",
                        ),
                        (
                            {
                                ("A01 产品部", "业务费用"): [10.0, 20.0, 30.0],
                                ("T01 平台部", "业务费用"): [99.0, 99.0, 99.0],
                            },
                            "prior-import.xlsx",
                        ),
                    ]
                ),
            ) as imported_loader,
            patch.object(
                resolver_module,
                "load_previous_year_actual_subject_monthly",
                new=AsyncMock(
                    return_value=(
                        {
                            "业务费用": [99.0, 99.0, 99.0],
                        },
                        {"业务费用": 297.0},
                        "budget-2025.db",
                    )
                ),
            ) as fallback_loader,
        ):
            context = await resolver_module.load_template_actual_context(
                ctx=ctx,
                budget_db=Path("budget-2026.db"),
                budget_year=2026,
                selected_month=2,
                selected_entity="微众银行",
                selected_group="个人金融事业群",
                selected_owner="A01 产品部",
                actual_source_file="expense-actual.xlsx",
            )

        self.assertEqual(context.current_subject_monthly_totals["业务费用"][:3], [1.11, 0.0, 3.33])
        self.assertEqual(context.current_subject_monthly_totals["业务费用"][3:], [0.0] * 9)
        self.assertEqual(context.previous_year_subject_monthly_totals["业务费用"][:3], [10.0, 20.0, 30.0])
        self.assertEqual(context.previous_year_subject_monthly_totals["业务费用"][3:], [0.0] * 9)
        self.assertEqual(context.previous_year_subject_totals, {"业务费用": 30.0})
        self.assertEqual(context.current_actual_source_file, "current-import.xlsx")
        self.assertEqual(context.previous_actual_source_file, "prior-import.xlsx")
        imported_loader.assert_any_await(ctx, "current_year_actual")
        imported_loader.assert_any_await(ctx, "prior_year_actual")
        fallback_loader.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
