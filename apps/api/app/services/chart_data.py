"""Multidimensional chart data builder."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path, compare_db_path
from app.metric_tree_paths import load_metric_tree_with_data_accounts
from app.schemas import (
    ChartBarRequestDto,
    ChartStackedMatrixRowDto,
    ChartStackedRequestDto,
    ChartStackedResolvedVersionDto,
    ChartStackedResponseDto,
    ChartStackedSeriesDto,
    ChartVersionItemDto,
    ChartVersionSelectionDto,
)


ChartVersionOptionsProvider = Callable[[], Awaitable[list[ChartVersionItemDto]]]
RuntimeMetricRefCodeExtractor = Callable[[str], str | None]
MetricChartContextLoader = Callable[[], Awaitable["MetricChartContext"]]
CompareAggregateRowsLoader = Callable[[list[ChartVersionItemDto], str], Awaitable[list[tuple[Any, ...]]]]


@dataclass(frozen=True)
class MetricChartContext:
    metric_name_map: dict[str, str]
    children_map: dict[str, list[str]]
    direct_data_map: dict[str, set[str]]
    data_name_map: dict[str, str]
    data_value_type_map: dict[str, str]


@dataclass(frozen=True)
class MetricChartSegments:
    segment_order: list[str]
    segment_data_codes: dict[str, set[str]]
    segment_label_map: dict[str, str]
    segment_value_type_map: dict[str, str | None]


def _period_labels(granularity: str) -> list[str]:
    if granularity == "quarter":
        return ["Q1", "Q2", "Q3", "Q4"]
    return [f"M{i:02d}" for i in range(1, 13)]


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


def _chart_version_key(option: ChartVersionItemDto) -> tuple[int, int, int]:
    return (int(option.show_level), int(option.data_file_id), int(option.version_id))


def _resolve_effective_chart_versions(
    *,
    use_all_versions: bool,
    selected_versions: list[ChartVersionSelectionDto],
    options: list[ChartVersionItemDto],
) -> list[ChartVersionItemDto]:
    if use_all_versions:
        return options

    by_full_key = {_chart_version_key(option): option for option in options}

    resolved: list[ChartVersionItemDto] = []
    seen: set[tuple[int, int, int]] = set()
    for selected in selected_versions:
        option = by_full_key.get(
            (int(selected.show_level), int(selected.data_file_id), int(selected.version_id))
        )
        if option is None:
            continue
        key = _chart_version_key(option)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(option)
    return resolved


async def load_metric_chart_context() -> MetricChartContext:
    roots = await load_metric_tree_with_data_accounts()

    metric_name_map: dict[str, str] = {}
    children_map: dict[str, list[str]] = {}
    direct_data_map: dict[str, set[str]] = {}
    data_name_map: dict[str, str] = {}
    data_value_type_map: dict[str, str] = {}

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") != "metric":
            return
        code = str(node.get("code", "")).strip().upper()
        if not code:
            return
        metric_name_map[code] = str(node.get("name", ""))
        children_map.setdefault(code, [])
        direct_data_map.setdefault(code, set())
        for child in node.get("children") or []:
            if child.get("type") == "metric":
                child_code = str(child.get("code", "")).strip().upper()
                if child_code:
                    children_map[code].append(child_code)
                walk(child)
                continue
            data_code = str(child.get("code", "")).strip().upper()
            if not data_code:
                continue
            direct_data_map[code].add(data_code)
            data_name_map[data_code] = str(child.get("name", data_code))
            data_value_type_map[data_code] = str(child.get("value_type", ""))

    for root in roots:
        walk(root)

    return MetricChartContext(
        metric_name_map=metric_name_map,
        children_map=children_map,
        direct_data_map=direct_data_map,
        data_name_map=data_name_map,
        data_value_type_map=data_value_type_map,
    )


async def load_compare_chart_aggregate_rows(
    effective_options: list[ChartVersionItemDto],
    grain: str,
) -> list[tuple[Any, ...]]:
    if not effective_options:
        return []
    clauses: list[str] = []
    values: list[Any] = [grain]
    param_marker = "%s" if _uses_mysql_path(compare_db_path()) else "?"
    for option in effective_options:
        clauses.append(
            f"(show_level = {param_marker} AND data_file_id = {param_marker} "
            f"AND source_version_id = {param_marker})"
        )
        values.extend([int(option.show_level), int(option.data_file_id), int(option.version_id)])
    if _uses_mysql_path(compare_db_path()):
        count_row = await get_pool().fetch_one(
            "SELECT COUNT(*) AS cnt FROM compare_pivot_aggregate WHERE grain = %s",
            (grain,),
        )
        if int(_row_value(count_row, "cnt", 0) or 0) == 0:
            raise HTTPException(
                status_code=409,
                detail="数据透视图聚合表为空，请先在“预算事实刷新跑批”执行跑批生成聚合表。",
            )
        rows = await get_pool().fetch_all(
            f"""
            SELECT show_level, data_file_id, source_version_id, data_code_name, month, quarter, value
            FROM compare_pivot_aggregate
            WHERE grain = %s
              AND ({" OR ".join(clauses)})
            """,
            tuple(values),
        )
    else:
        rows = await asyncio.to_thread(
            _sqlite_load_compare_chart_aggregate_rows,
            compare_db_path(),
            grain,
            clauses,
            values,
        )
    if not rows:
        raise HTTPException(
            status_code=409,
            detail="所选展示版本没有对应的数据透视图聚合结果，请先在“预算事实刷新跑批”执行跑批。",
        )
    return rows


def _sqlite_load_compare_chart_aggregate_rows(
    db_path: Path,
    grain: str,
    clauses: list[str],
    values: list[Any],
) -> list[tuple[Any, ...]]:
    try:
        with sqlite3.connect(db_path) as conn:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM compare_pivot_aggregate WHERE grain = ?",
                (grain,),
            ).fetchone()
            if int(count_row[0] or 0) == 0:
                raise HTTPException(
                    status_code=409,
                    detail="数据透视图聚合表为空，请先在“预算事实刷新跑批”执行跑批生成聚合表。",
                )
            return conn.execute(
                f"""
                SELECT show_level, data_file_id, source_version_id, data_code_name, month, quarter, value
                FROM compare_pivot_aggregate
                WHERE grain = ?
                  AND ({" OR ".join(clauses)})
                """,
                tuple(values),
            ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=409,
            detail="数据透视图聚合表为空，请先在“预算事实刷新跑批”执行跑批生成聚合表。",
        ) from exc


def _collect_metric_descendants(root_code: str, children_map: dict[str, list[str]]) -> set[str]:
    stack = [root_code]
    out: set[str] = set()
    while stack:
        code = stack.pop()
        if code in out:
            continue
        out.add(code)
        stack.extend(children_map.get(code, []))
    return out


def _resolve_metric_chart_segments(
    context: MetricChartContext,
    selected_metric_code: str,
    *,
    compare_scope: str,
) -> MetricChartSegments:
    selected_code = selected_metric_code.strip().upper()
    if selected_code not in context.metric_name_map:
        raise HTTPException(status_code=400, detail=f"指标节点 {selected_code} 不存在")

    selected_descendants = _collect_metric_descendants(selected_code, context.children_map)
    direct_data_codes = sorted(context.direct_data_map.get(selected_code, set()))
    if compare_scope == "self":
        data_codes: set[str] = set()
        for metric_code in selected_descendants:
            data_codes.update(context.direct_data_map.get(metric_code, set()))
        segment_order = [selected_code]
        segment_data_codes = {selected_code: data_codes}
        segment_label_map = {
            selected_code: f"{selected_code} {context.metric_name_map.get(selected_code, '')}".strip()
        }
    else:
        child_codes = sorted(context.children_map.get(selected_code, []))
        if not child_codes and not direct_data_codes:
            raise HTTPException(status_code=400, detail="所选指标没有下级指标，请改用本指标比较")
        segment_order = child_codes[:]
        segment_data_codes: dict[str, set[str]] = {}
        segment_label_map: dict[str, str] = {}
        for segment in child_codes:
            data_codes: set[str] = set()
            for metric_code in _collect_metric_descendants(segment, context.children_map):
                data_codes.update(context.direct_data_map.get(metric_code, set()))
            segment_data_codes[segment] = data_codes
            segment_label_map[segment] = f"{segment} {context.metric_name_map.get(segment, '')}".strip()
        covered_codes: set[str] = set()
        for segment in child_codes:
            covered_codes.update(segment_data_codes.get(segment, set()))
        for data_code in direct_data_codes:
            if data_code in covered_codes:
                continue
            seg_key = f"DATA::{data_code}"
            segment_order.append(seg_key)
            segment_data_codes[seg_key] = {data_code}
            segment_label_map[seg_key] = context.data_name_map.get(data_code, data_code)

    segment_value_type_map: dict[str, str | None] = {}
    for segment in segment_order:
        value_types = {
            context.data_value_type_map.get(data_code, "")
            for data_code in segment_data_codes.get(segment, set())
            if context.data_value_type_map.get(data_code, "")
        }
        segment_value_type_map[segment] = next(iter(value_types)) if len(value_types) == 1 else None
    return MetricChartSegments(
        segment_order=segment_order,
        segment_data_codes=segment_data_codes,
        segment_label_map=segment_label_map,
        segment_value_type_map=segment_value_type_map,
    )


def _fill_series_from_compare_aggregate(
    *,
    rows: list[tuple[Any, ...]],
    effective_options: list[ChartVersionItemDto],
    single_version: bool,
    single_version_granularity: str,
    category_index_map: dict[str, int],
    code_to_segment: dict[str, str],
    series_abs_map: dict[str, list[float]],
    extract_runtime_metric_ref_code_from_name: RuntimeMetricRefCodeExtractor,
) -> None:
    option_index_by_key = {
        _chart_version_key(option): idx
        for idx, option in enumerate(effective_options)
    }
    for row in rows:
        data_code = extract_runtime_metric_ref_code_from_name(
            str(_row_value(row, "data_code_name", 3) or "")
        )
        if not data_code:
            continue
        segment = code_to_segment.get(data_code)
        if not segment:
            continue
        if single_version:
            period_key = str(
                _row_value(row, "quarter", 5)
                if single_version_granularity == "quarter"
                else _row_value(row, "month", 4)
            )
            c_idx = category_index_map.get(period_key)
            if c_idx is None:
                continue
        else:
            key = (
                int(_row_value(row, "show_level", 0) or 0),
                int(_row_value(row, "data_file_id", 1) or 0),
                int(_row_value(row, "source_version_id", 2) or 0),
            )
            c_idx = option_index_by_key.get(key)
            if c_idx is None:
                continue
        series_abs_map[segment][c_idx] += float(_row_value(row, "value", 6) or 0.0)


class ChartDataBuilder:
    def __init__(
        self,
        *,
        chart_version_options_provider: ChartVersionOptionsProvider,
        extract_runtime_metric_ref_code_from_name: RuntimeMetricRefCodeExtractor,
        metric_chart_context_loader: MetricChartContextLoader = load_metric_chart_context,
        compare_aggregate_rows_loader: CompareAggregateRowsLoader = load_compare_chart_aggregate_rows,
    ) -> None:
        self._chart_version_options_provider = chart_version_options_provider
        self._extract_runtime_metric_ref_code_from_name = extract_runtime_metric_ref_code_from_name
        self._metric_chart_context_loader = metric_chart_context_loader
        self._compare_aggregate_rows_loader = compare_aggregate_rows_loader

    async def build_stacked_response(self, req: ChartStackedRequestDto) -> ChartStackedResponseDto:
        return await self._build_metric_response(
            req=req,
            compare_scope="children",
            stack_mode=req.stack_mode,
            include_value_type=False,
            note="stack_mode=percent 时数值单位为百分比",
        )

    async def build_bar_response(self, req: ChartBarRequestDto) -> ChartStackedResponseDto:
        return await self._build_metric_response(
            req=req,
            compare_scope=req.bar_compare_scope.strip().lower(),
            stack_mode="absolute",
            include_value_type=True,
            note=None,
        )

    async def _build_metric_response(
        self,
        *,
        req: ChartStackedRequestDto | ChartBarRequestDto,
        compare_scope: str,
        stack_mode: str,
        include_value_type: bool,
        note: str | None,
    ) -> ChartStackedResponseDto:
        selected_versions = req.selected_versions
        if not req.use_all_versions and not selected_versions:
            raise HTTPException(status_code=400, detail="请选择至少一个展示版本")
        if len(selected_versions) > 5:
            raise HTTPException(status_code=400, detail="最多选择5个展示版本")

        options = await self._chart_version_options_provider()
        resolved_options = _resolve_effective_chart_versions(
            use_all_versions=req.use_all_versions,
            selected_versions=selected_versions,
            options=options,
        )
        if not resolved_options:
            return ChartStackedResponseDto(note="没有可用版本数据")

        context = await self._metric_chart_context_loader()
        segments = _resolve_metric_chart_segments(
            context,
            req.metric_node_code,
            compare_scope=compare_scope,
        )

        code_to_segment: dict[str, str] = {}
        for segment in segments.segment_order:
            for data_code in sorted(segments.segment_data_codes.get(segment, set())):
                if data_code not in code_to_segment:
                    code_to_segment[data_code] = segment

        effective_options = sorted(resolved_options, key=lambda o: (o.year, o.version_id))
        single_version = len(effective_options) == 1
        categories = (
            _period_labels(req.single_version_granularity)
            if single_version
            else [f"{opt.year}-V{opt.version_id} {opt.version_name}" for opt in effective_options]
        )
        category_index_map = {name: idx for idx, name in enumerate(categories)}

        series_abs_map: dict[str, list[float]] = {
            segment: [0.0] * len(categories)
            for segment in segments.segment_order
        }
        grain = req.single_version_granularity if single_version else "year"
        aggregate_rows = await self._compare_aggregate_rows_loader(effective_options, grain)
        _fill_series_from_compare_aggregate(
            rows=aggregate_rows,
            effective_options=effective_options,
            single_version=single_version,
            single_version_granularity=req.single_version_granularity,
            category_index_map=category_index_map,
            code_to_segment=code_to_segment,
            series_abs_map=series_abs_map,
            extract_runtime_metric_ref_code_from_name=self._extract_runtime_metric_ref_code_from_name,
        )

        series, matrix_rows = self._build_series_and_matrix_rows(
            segments=segments,
            series_abs_map=series_abs_map,
            categories=categories,
            stack_mode=stack_mode,
            include_value_type=include_value_type,
        )

        resolved_versions = [
            ChartStackedResolvedVersionDto(
                data_file_id=option.data_file_id,
                year=option.year,
                version_id=option.version_id,
                version_name=option.version_name,
            )
            for option in effective_options
        ]
        return ChartStackedResponseDto(
            categories=categories,
            series=series,
            matrix_headers=categories,
            matrix_rows=matrix_rows,
            resolved_versions=resolved_versions,
            note=note,
        )

    def _build_series_and_matrix_rows(
        self,
        *,
        segments: MetricChartSegments,
        series_abs_map: dict[str, list[float]],
        categories: list[str],
        stack_mode: str,
        include_value_type: bool,
    ) -> tuple[list[ChartStackedSeriesDto], list[ChartStackedMatrixRowDto]]:
        series: list[ChartStackedSeriesDto] = []
        matrix_rows: list[ChartStackedMatrixRowDto] = []
        totals = [0.0] * len(categories)
        if stack_mode == "percent":
            for values in series_abs_map.values():
                for idx, value in enumerate(values):
                    totals[idx] += value

        for segment in segments.segment_order:
            raw_values = series_abs_map[segment]
            values = (
                [
                    (raw_values[idx] / totals[idx] * 100.0) if totals[idx] else 0.0
                    for idx in range(len(categories))
                ]
                if stack_mode == "percent"
                else raw_values
            )
            label = segments.segment_label_map.get(segment, segment)
            value_type = segments.segment_value_type_map.get(segment) if include_value_type else None
            series.append(
                ChartStackedSeriesDto(
                    key=segment,
                    label=label,
                    values=values,
                    value_type=value_type,
                )
            )
            matrix_rows.append(
                ChartStackedMatrixRowDto(
                    row_label=label,
                    values=values,
                    value_type=value_type,
                )
            )
        return series, matrix_rows
