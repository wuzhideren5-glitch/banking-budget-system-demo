from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import SimpleNamespace
from typing import Any

from scripts.full_user_journey import create_test_metric_tree


@dataclass
class _FakeResponse:
    status_code: int = 200
    text: str = ""
    content: bytes = b"{}"
    headers: dict[str, str] | None = None
    request: Any = field(
        default_factory=lambda: SimpleNamespace(url=SimpleNamespace(path="/api/org-product-metrics/db-snapshot"))
    )

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class _FakeClient:
    def __init__(self) -> None:
        self.gets: list[str] = []

    def get(self, path: str) -> _FakeResponse:
        self.gets.append(path)
        payload = {
            "entities": [
                {
                    "entity_code": "Z99",
                    "tables": [
                        {
                            "table_name": "业务状况表",
                            "metrics": [
                                {
                                    "metric_node_code": "A01.01.01.001",
                                    "data_acct_code": "A01.01.01.001",
                                    "mapping_status": "MANUAL_CONFIRMED",
                                },
                                {
                                    "metric_node_code": "Z99.99.99.001",
                                    "data_acct_code": "Z99.99.99.001",
                                    "mapping_status": "MANUAL_CONFIRMED",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        return _FakeResponse(
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )


def test_full_user_journey_selects_existing_product_prefixed_metric_identity() -> None:
    client = _FakeClient()

    metric_node = create_test_metric_tree(client, "Z99")

    assert metric_node == "Z99.99.99.001"
    assert client.gets == ["/api/org-product-metrics/db-snapshot"]
