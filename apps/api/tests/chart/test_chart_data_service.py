from __future__ import annotations

import asyncio
import unittest

from fastapi import HTTPException

from app.schemas import (
    ChartBarRequestDto,
    ChartStackedRequestDto,
    ChartVersionItemDto,
    ChartVersionSelectionDto,
)
from app.services.chart_data import ChartDataBuilder, MetricChartContext


def _version(
    *,
    show_level: int,
    data_file_id: int,
    year: int,
    version_id: int,
    version_name: str,
) -> ChartVersionItemDto:
    return ChartVersionItemDto(
        show_level=show_level,
        data_file_id=data_file_id,
        data_file_name=f"{year}.xlsx",
        year=year,
        version_id=version_id,
        version_name=version_name,
        current_month=6,
    )


class ChartDataBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = [
            _version(show_level=1, data_file_id=100, year=2026, version_id=1, version_name="基准"),
            _version(show_level=2, data_file_id=101, year=2026, version_id=2, version_name="乐观"),
        ]
        self.context = MetricChartContext(
            metric_name_map={
                "A01.ROOT": "总指标",
                "A01.C1": "收入",
                "A01.C2": "成本",
            },
            children_map={
                "A01.ROOT": ["A01.C1", "A01.C2"],
                "A01.C1": [],
                "A01.C2": [],
            },
            direct_data_map={
                "A01.ROOT": set(),
                "A01.C1": {"A01.D1"},
                "A01.C2": {"A01.D2"},
            },
            data_name_map={"A01.D1": "收入数据", "A01.D2": "成本数据"},
            data_value_type_map={"A01.D1": "余额", "A01.D2": "余额"},
        )

    def _builder(self, rows: list[tuple]) -> ChartDataBuilder:
        async def load_options() -> list[ChartVersionItemDto]:
            return self.options

        async def load_context() -> MetricChartContext:
            return self.context

        async def load_rows(
            effective_options: list[ChartVersionItemDto],
            grain: str,
        ) -> list[tuple]:
            self.loaded_grain = grain
            self.loaded_version_keys = [
                (option.show_level, option.data_file_id, option.version_id)
                for option in effective_options
            ]
            return rows

        def extract_data_code(data_code_name: str) -> str | None:
            return data_code_name.split()[0].strip().upper() or None

        return ChartDataBuilder(
            chart_version_options_provider=load_options,
            extract_runtime_metric_ref_code_from_name=extract_data_code,
            metric_chart_context_loader=load_context,
            compare_aggregate_rows_loader=load_rows,
        )

    def test_builds_percent_stacked_response_from_exact_selected_versions(self) -> None:
        rows = [
            (1, 100, 1, "A01.D1 收入数据", "M01", "Q1", 30.0),
            (1, 100, 1, "A01.D2 成本数据", "M01", "Q1", 70.0),
            (2, 101, 2, "A01.D1 收入数据", "M01", "Q1", 25.0),
            (2, 101, 2, "A01.D2 成本数据", "M01", "Q1", 75.0),
        ]
        req = ChartStackedRequestDto(
            metric_node_code="a01.root",
            use_all_versions=False,
            selected_versions=[
                ChartVersionSelectionDto(show_level=1, data_file_id=100, version_id=1),
                ChartVersionSelectionDto(show_level=2, data_file_id=101, version_id=2),
            ],
            stack_mode="percent",
        )

        response = asyncio.run(self._builder(rows).build_stacked_response(req))

        self.assertEqual(self.loaded_grain, "year")
        self.assertEqual(self.loaded_version_keys, [(1, 100, 1), (2, 101, 2)])
        self.assertEqual(response.categories, ["2026-V1 基准", "2026-V2 乐观"])
        self.assertEqual([item.key for item in response.series], ["A01.C1", "A01.C2"])
        self.assertEqual(response.series[0].values, [30.0, 25.0])
        self.assertEqual(response.series[1].values, [70.0, 75.0])

    def test_builds_single_version_bar_response_as_selected_metric_total(self) -> None:
        rows = [
            (1, 100, 1, "A01.D1 收入数据", "M01", "Q1", 1.0),
            (1, 100, 1, "A01.D2 成本数据", "M01", "Q1", 2.0),
            (1, 100, 1, "A01.D1 收入数据", "M02", "Q1", 3.0),
            (1, 100, 1, "A01.D2 成本数据", "M02", "Q1", 4.0),
        ]
        req = ChartBarRequestDto(
            metric_node_code="A01.ROOT",
            bar_compare_scope="self",
            use_all_versions=False,
            selected_versions=[
                ChartVersionSelectionDto(show_level=1, data_file_id=100, version_id=1),
            ],
            single_version_granularity="month",
        )

        response = asyncio.run(self._builder(rows).build_bar_response(req))

        self.assertEqual(self.loaded_grain, "month")
        self.assertEqual(response.categories[:2], ["M01", "M02"])
        self.assertEqual(response.series[0].key, "A01.ROOT")
        self.assertEqual(response.series[0].label, "A01.ROOT 总指标")
        self.assertEqual(response.series[0].values[:2], [3.0, 7.0])
        self.assertEqual(response.series[0].value_type, "余额")

    def test_rejects_empty_manual_version_selection(self) -> None:
        req = ChartStackedRequestDto(
            metric_node_code="A01.ROOT",
            use_all_versions=False,
            selected_versions=[],
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._builder([]).build_stacked_response(req))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("请选择至少一个展示版本", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
