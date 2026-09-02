from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import httpx
from fastapi import FastAPI, Query


app = FastAPI(title="fx-convert-tool")

SOURCE = "ECB via frankfurter.dev"
_cache: dict[tuple[str, str, str], dict] = {}


def upstream_base() -> str:
    return os.getenv("FX_UPSTREAM_BASE", "https://api.frankfurter.dev").rstrip("/")


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

    if key in _cache:
        payload = _cache[key]
    else:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{upstream_base()}/{day}",
                params={"base": base, "symbols": target},
            )
            response.raise_for_status()
            payload = response.json()
        _cache[key] = payload

    rates = payload.get("rates", {})
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
