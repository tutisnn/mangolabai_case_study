from __future__ import annotations

import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import _cache, app


def setup_function():
    _cache.clear()


def print_response(name: str, response):
    print(f"\nTEST: {name}")
    print("status:", response.status_code)
    print("response:", response.json())


def assert_error(response, status_code: int, code: str, message: str):
    print_response(code, response)
    assert response.status_code == status_code
    assert response.json() == {"error": code, "message": message}


def test_unknown_currency_code_returns_error(monkeypatch):
    print("\nTEST: unknown currency code returns structured error")
    print("GET /tools/convert?amount=250&from=EUR&to=TRE&date=2026-08-28")

    async def fake_get(self, url, params=None):
        raise AssertionError("unknown currencies should fail before calling upstream")

    monkeypatch.setenv("FX_UPSTREAM_BASE", "http://fake-upstream.local")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRE", "date": "2026-08-28"},
    )

    assert_error(response, 400, "unknown_currency", "One or both requested currency codes are not supported.")


def test_same_currency_returns_identity_conversion_without_calling_upstream(monkeypatch):
    print("\nTEST: same currency returns rate 1 without calling upstream")
    print("GET /tools/convert?amount=250&from=EUR&to=EUR&date=2026-08-28")

    async def fake_get(self, url, params=None):
        raise AssertionError("same currency should return before calling upstream")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "EUR", "date": "2026-08-28"},
    )

    print_response("same_currency_identity", response)
    assert response.status_code == 200
    assert response.json() == {
        "amount": 250.0,
        "from": "EUR",
        "to": "EUR",
        "rate": 1.0,
        "result": 250.0,
        "rate_date": "2026-08-28",
        "asked_date": "2026-08-28",
        "source": "ECB via frankfurter.dev",
    }


def test_try_to_try_returns_identity_conversion_for_2026_09_01(monkeypatch):
    print("\nTEST: TRY to TRY returns rate 1 without calling upstream")
    print("GET /tools/convert?amount=250&from=TRY&to=TRY&date=2026-09-01")

    async def fake_get(self, url, params=None):
        raise AssertionError("same currency should return before calling upstream")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "TRY", "to": "TRY", "date": "2026-09-01"},
    )

    print_response("try_to_try_identity", response)
    assert response.status_code == 200
    assert response.json() == {
        "amount": 250.0,
        "from": "TRY",
        "to": "TRY",
        "rate": 1.0,
        "result": 250.0,
        "rate_date": "2026-09-01",
        "asked_date": "2026-09-01",
        "source": "ECB via frankfurter.dev",
    }


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


def test_successful_conversion_is_cached(monkeypatch):
    print("\nTEST: repeated successful conversion does not call upstream twice")
    print("GET /tools/convert?amount=250&from=EUR&to=USD&date=2026-08-28")

    calls = []

    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "EUR", "date": "2026-08-28", "rates": {"USD": 1.2}},
            request=request,
        )

    monkeypatch.setenv("FX_UPSTREAM_BASE", "http://fake-upstream.local")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    first = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "USD", "date": "2026-08-28"},
    )
    second = client.get(
        "/tools/convert",
        params={"amount": "100", "from": "EUR", "to": "USD", "date": "2026-08-28"},
    )

    print_response("first_successful_conversion", first)
    print_response("second_successful_conversion_from_cache", second)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result"] == 300.0
    assert second.json()["result"] == 120.0
    assert len(calls) == 1


def test_failed_upstream_payload_is_not_cached(monkeypatch):
    print("\nTEST: failed upstream payload is not cached")
    print("GET /tools/convert?amount=250&from=EUR&to=GBP&date=2026-08-28")

    responses = [
        {"amount": 1.0, "base": "EUR", "date": "2026-08-28", "rates": {}},
        {"amount": 1.0, "base": "EUR", "date": "2026-08-28", "rates": {"GBP": 0.85}},
    ]

    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json=responses.pop(0), request=request)

    monkeypatch.setenv("FX_UPSTREAM_BASE", "http://fake-upstream.local")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    first = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "GBP", "date": "2026-08-28"},
    )
    second = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "GBP", "date": "2026-08-28"},
    )

    assert_error(first, 400, "rate_not_available", "No exchange rate was available for that request.")
    print_response("second_request_after_failed_payload", second)
    assert second.status_code == 200
    assert second.json()["rate"] == 0.85
    assert second.json()["result"] == 212.5


def test_weekend_uses_upstream_rate_date(monkeypatch):
    print("\nTEST: weekend request shows the actual upstream rate date")

    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        assert str(request.url).startswith("http://fake-upstream.local/2026-08-30")
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "EUR", "date": "2026-08-28", "rates": {"TRY": 47.1234}},
            request=request,
        )

    monkeypatch.setenv("FX_UPSTREAM_BASE", "http://fake-upstream.local")
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRY", "date": "2026-08-30"},
    )

    print("GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-30")
    print("status:", response.status_code)
    print("response:", response.json())

    assert response.status_code == 200
    assert response.json()["asked_date"] == "2026-08-30"
    assert response.json()["rate_date"] == "2026-08-28"
    assert response.json()["result"] == 11780.85


def test_invalid_amount_returns_error_shape():
    print("\nTEST: zero amount returns structured error")
    print("GET /tools/convert?amount=0&from=EUR&to=TRY&date=2026-08-28")

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "0", "from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    assert_error(response, 400, "invalid_amount", "Amount must be greater than zero.")


def test_negative_amount_returns_error_shape():
    print("\nTEST: negative amount returns structured error")
    print("GET /tools/convert?amount=-250&from=EUR&to=TRY&date=2026-08-28")

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "-250", "from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    assert_error(response, 400, "invalid_amount", "Amount must be greater than zero.")


def test_missing_amount_returns_bad_request():
    print("\nTEST: missing amount returns structured bad request")
    print("GET /tools/convert?from=EUR&to=TRY&date=2026-08-28")

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    assert_error(response, 422, "bad_request", "The request could not be processed.")


def test_amount_with_ten_decimal_places_returns_error():
    print("\nTEST: amount with ten decimal places returns structured error")
    print("GET /tools/convert?amount=1.1234567890&from=EUR&to=TRY&date=2026-08-28")

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "1.1234567890", "from": "EUR", "to": "TRY", "date": "2026-08-28"},
    )

    assert_error(response, 400, "amount_too_precise", "Amount must not have more than two decimal places.")


def test_upstream_timeout_returns_error(monkeypatch):
    async def fake_get(self, url, params=None):
        raise httpx.TimeoutException("slow upstream")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "USD", "date": "2026-08-29"},
    )

    assert_error(response, 504, "upstream_timeout", "The exchange-rate service took too long to respond.")


def test_upstream_http_error_returns_error(monkeypatch):
    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("upstream failed", request=request, response=response)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "GBP", "date": "2026-08-29"},
    )

    assert_error(response, 502, "upstream_error", "The exchange-rate service returned an error.")


def test_future_date_returns_error_when_upstream_rejects_it(monkeypatch):
    async def fake_get(self, url, params=None):
        raise AssertionError("future dates should fail before calling upstream")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRY", "date": "2099-01-01"},
    )

    assert_error(response, 400, "date_in_future", "Date must not be in the future.")


def test_date_before_series_start_returns_error_when_upstream_rejects_it(monkeypatch):
    async def fake_get(self, url, params=None):
        raise AssertionError("dates before the series starts should fail before calling upstream")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRY", "date": "1990-01-01"},
    )

    assert_error(response, 400, "date_before_series_start", "Date is before the exchange-rate series starts.")


def test_upstream_bad_json_returns_error(monkeypatch):
    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, content=b"not json", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "CHF", "date": "2026-08-29"},
    )

    assert_error(response, 502, "upstream_bad_json", "The exchange-rate service returned invalid JSON.")


def test_upstream_unavailable_returns_error(monkeypatch):
    async def fake_get(self, url, params=None):
        raise httpx.ConnectError("closed port")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "CAD", "date": "2026-08-29"},
    )

    assert_error(response, 502, "upstream_unavailable", "The exchange-rate service could not be reached.")


def test_rate_not_available_returns_error(monkeypatch):
    async def fake_get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, json={"base": "EUR", "date": "2026-08-29", "rates": {}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "AUD", "date": "2026-08-29"},
    )

    assert_error(response, 400, "rate_not_available", "No exchange rate was available for that request.")


def test_bad_request_returns_error_shape():
    client = TestClient(app)
    response = client.get(
        "/tools/convert",
        params={"amount": "250", "from": "EUR", "to": "TRY", "date": "not-a-date"},
    )

    assert_error(response, 422, "bad_request", "The request could not be processed.")
