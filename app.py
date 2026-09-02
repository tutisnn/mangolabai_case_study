from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


app = FastAPI(title="fx-convert-tool")

SOURCE = "ECB via frankfurter.dev"
SERIES_START = date(1999, 1, 4)
_cache: dict[tuple[str, str, str], dict] = {}


def upstream_base() -> str:
    return os.getenv("FX_UPSTREAM_BASE", "https://api.frankfurter.dev").rstrip("/")


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message})


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return error_response(exc.status_code, "bad_request", "The request could not be processed.")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "bad_request", "The request could not be processed.")


@app.get("/tools/convert")
async def convert(
    amount: Decimal = Query(...),
    from_currency: str = Query(..., alias="from"),
    to: str = Query(...),
    asked_date: date = Query(..., alias="date"),
) -> dict:
    base = from_currency.upper()
    target = to.upper()
    day = asked_date.isoformat()
    key = (day, base, target)

    if amount <= 0:
        return error_response(400, "invalid_amount", "Amount must be greater than zero.")
    if base == target:
        return {
            "amount": float(amount),
            "from": base,
            "to": target,
            "rate": 1.0,
            "result": float(round(amount, 2)),
            "rate_date": day,
            "asked_date": day,
            "source": SOURCE,
        }
    if asked_date > date.today():
        return error_response(400, "date_in_future", "Date must not be in the future.")
    if asked_date < SERIES_START:
        return error_response(400, "date_before_series_start", "Date is before the exchange-rate series starts.")

    if key in _cache:
        payload = _cache[key]
    else:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{upstream_base()}/{day}",
                    params={"base": base, "symbols": target},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return error_response(504, "upstream_timeout", "The exchange-rate service took too long to respond.")
        except httpx.HTTPStatusError:
            return error_response(502, "upstream_error", "The exchange-rate service returned an error.")
        except ValueError:
            return error_response(502, "upstream_bad_json", "The exchange-rate service returned invalid JSON.")
        except httpx.HTTPError:
            return error_response(502, "upstream_unavailable", "The exchange-rate service could not be reached.")
        _cache[key] = payload

    rates = payload.get("rates", {})
    if target not in rates or "date" not in payload:
        return error_response(400, "rate_not_available", "No exchange rate was available for that request.")

    rate = Decimal(str(rates[target]))
    result = amount * rate

    return {
        "amount": float(amount),
        "from": base,
        "to": target,
        "rate": float(rate),
        "result": float(round(result, 2)),
        "rate_date": payload["date"],
        "asked_date": day,
        "source": SOURCE,
    }
