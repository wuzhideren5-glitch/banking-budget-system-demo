from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.health import router


def test_health_endpoint_supports_get_and_head() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    get_response = client.get("/api/health")
    head_response = client.head("/api/health")

    assert get_response.status_code == 200
    assert get_response.json() == {"status": "ok"}
    assert head_response.status_code == 200
    assert head_response.content == b""
