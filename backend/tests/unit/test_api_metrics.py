"""Prometheus HTTP metrics on the API."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from api.main import create_app
from api.metrics import route_template


def test_route_template_unmatched() -> None:
    scope: dict = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "method": "GET",
        "path": "/unknown",
        "raw_path": b"/unknown",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "scheme": "http",
        "server": ("test", 80),
    }
    req = Request(scope)
    assert route_template(req) == "unmatched"


def test_route_template_from_scope_route() -> None:
    scope: dict = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "method": "GET",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "scheme": "http",
        "server": ("test", 80),
        "route": SimpleNamespace(path="/health"),
    }
    req = Request(scope)
    assert route_template(req) == "/health"


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text() -> None:
    app = create_app(use_lifespan=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/metrics")
    assert r.status_code == 200
    assert "process_" in r.text or "python_" in r.text
    assert "http_requests_total" in r.text
    assert "http_requests_in_progress" in r.text


@pytest.mark.asyncio
async def test_metrics_disabled_no_route() -> None:
    app = create_app(use_lifespan=False, enable_metrics=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/metrics")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_health_recorded_in_http_metrics() -> None:
    app = create_app(use_lifespan=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.get("/health")
        body = (await ac.get("/metrics")).text
    assert "http_requests_total" in body
    assert "/health" in body
