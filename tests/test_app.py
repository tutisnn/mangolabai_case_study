from __future__ import annotations

import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app


def test_convert_uses_fake_upstream(monkeypatch):
    print("\nTEST: successful conversion uses FX_UPSTREAM_BASE fake upstream")
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url).startswith("http://fake-upstream.local/2026-08-28")
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "EUR", "date": "2026-08-28", "rates": {"TRY": 47.1234}},
            request=request,
        )

    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        return await handler(request)

    monkeypatch.setenv("FX_UPSTREAM_BASE", "http://fake-upstream.local")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    print("GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28")
    print("status:", response.status_code)
    print("response:", response.json())

    assert response.status_code == 200
    assert response.json() == {
        "amount": 250.0,
        "from": "EUR",
        "to": "TRY",
        "rate": 47.1234,
        "result": 11780.85,
        "rate_date": "2026-08-28",
        "asked_date": "2026-08-28",
        "source": "ECB via frankfurter.dev",
    }
    assert len(calls) == 1


def test_convert_failure_returns_error_shape():
    print("\nTEST: failure returns non-2xx error response shape")
    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "0", "from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    print("GET /tools/convert?amount=0&from=EUR&to=TRY&date=2026-08-28")
    print("status:", response.status_code)
    print("response:", response.json())

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_amount",
        "message": "Amount must be greater than zero.",
    }
