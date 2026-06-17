from __future__ import annotations

from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True)
class RuntimeMetricRollupFormulaSyncResult:
    created: int = 0
    updated: int = 0

    @property
    def changed(self) -> int:
        return self.created + self.updated


async def sync_runtime_metric_rollup_formulas(
    db: aiosqlite.Connection,
    *,
    metric_node_codes: set[str] | None = None,
) -> RuntimeMetricRollupFormulaSyncResult:
    """Product-horizontal formula generation is retired in the product-prefixed model."""
    return RuntimeMetricRollupFormulaSyncResult()
