# Review of tool.py

One page. Findings **ranked** — most harmful to a customer first.

For each finding: what is wrong, what it does to a customer (not to a linter),
and how you would verify it.

## 1.

Exceptions are not converted into proper HTTP error responses.

`convert` catches every error with a broad `except Exception` and returns a body
that looks like a normal conversion response, even though the conversion failed:

```python
except Exception as exc:
    return {
        "amount": amount,
        "from": from_,
        "to": to,
        "rate": 0.0,
        "result": 0.0,
        "rate_date": str(on or date.today()),
        "source": "ECB via frankfurter.dev",
    }
```

This response does not include `error` or `message`, and FastAPI can return it
as a successful 200 response. If the upstream times out, returns 500, returns
invalid JSON, or rejects a currency, the customer may see `rate: 0.0` and
`result: 0.0` instead of a real error.

Customer impact: an AI agent could treat this as a real conversion result and
tell a customer something like "250 EUR = 0 TRY". This directly violates the
brief's warning that a wrong number is worse than no number.

How I would verify it: I would run the service against a fake upstream that
returns 500, times out, or returns non-JSON content. The expected behavior is a
non-2xx response with `{ "error": "...", "message": "..." }`; I would check that
the current code instead returns a successful-looking `rate: 0.0` response.

## 2.

The cache ignores the requested date.

In `tool.py`, the cache key only contains the currency pair:

```python
key = f"{base}-{target}"
```

That means once a rate for `EUR-TRY` is cached, later `EUR-TRY` requests for
different dates can reuse the same rate.

Customer impact: a customer asking for a 2021 conversion can receive a rate that
was cached from 2026. Worse, the response can claim that the cached rate belongs
to `2021-09-01`. This is not just a cache issue; it is a wrong financial answer
for the customer.

How I verified it: I started `tool.py` and called the same currency pair with
two different dates:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-09-01
/tools/convert?amount=250&from_=EUR&to=TRY&on=2021-09-01
```

Both responses returned the same rate:

```json
"rate": 55.95
```

But the second response presented that rate as if it belonged to this date:

```json
"rate_date": "2021-09-01"
```

This violates the brief's requirement that the endpoint must not present a rate
as belonging to a date it does not belong to.

## 3.

Weekend and holiday dates do not distinguish `asked_date` from `rate_date`.

The brief defines `asked_date` as the caller's requested date and `rate_date` as
the date the used rate actually belongs to. `tool.py` does not return
`asked_date`, and its `rate_date` is generated from the caller's `on` parameter
instead of the upstream response's real `date` field.

Customer impact: if a customer asks for a date like `2026-08-30`, when the ECB
did not publish a rate, the service can still return a successful response with
`rate_date: "2026-08-30"`. That makes it look as if the rate really belongs to
that day. An AI agent could then explain the conversion using the wrong date.

How I verified it: I called `tool.py` with:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-08-30
```

The service returned:

```json
"rate_date": "2026-08-30"
```

But `2026-08-30` was a Sunday, so the ECB would not have published a rate for
that date. The service should read the upstream `date`, return it as
`rate_date`, and keep the requested date separately as `asked_date`.

## 4.

Future or unavailable dates can fall back to `latest` and look valid.

In `fetch_rate`, when the target rate is missing, the code treats that as a
weekend/holiday case and falls back to `/latest`:

```python
if target not in payload.get("rates", {}):
    response = await client.get(f"{UPSTREAM}/latest", params={"base": base, "symbols": target})
    payload = response.json()
```

This fallback is too broad. Future dates, dates before the series starts,
unsupported currencies, or malformed upstream responses can all fall into the
same path.

Customer impact: if a customer asks for a future date like `2090-01-01`, where
an ECB rate cannot exist, the service can use today's/latest rate and return a
successful response. Worse, it can say that the rate belongs to `2090-01-01`.

How I verified it: I called:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2090-01-01
```

The service returned:

```json
{"amount":250.0,"from":"EUR","to":"TRY","rate":55.91,"result":13977.5,"rate_date":"2090-01-01","source":"ECB via frankfurter.dev"}
```

Then I called the current date:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-09-02
```

and got the same rate:

```json
{"amount":250.0,"from":"EUR","to":"TRY","rate":55.91,"result":13977.5,"rate_date":"2026-09-02","source":"ECB via frankfurter.dev"}
```

This shows that `latest` can be used for an unavailable date, while the response
presents the requested date as the rate date.

## 5.

`FX_UPSTREAM_BASE` is not used.

`tool.py` hardcodes the real Frankfurter host:

```python
UPSTREAM = "https://api.frankfurter.dev/v1"
```

The README requires the upstream URL to come from the `FX_UPSTREAM_BASE`
environment variable. When the reviewer points the service at a fake upstream,
this implementation cannot use it and will still try to call the real host.

## 6.

The rate is rounded too early, and the result is calculated from the rounded
rate.

`tool.py` rounds the upstream rate to two decimal places before calculating the
result:

```python
rate = round(rate, 2)
result = round(amount * rate, 2)
```

This loses precision from Frankfurter's response. For example, if the upstream
returns `47.1234`, the service changes it to `47.12` and calculates the result
with that shortened value.

Customer impact: for small amounts the difference may look minor, but for large
conversions, early rounding can produce the wrong financial result. Even if the
displayed rate is rounded, the calculation should use the full upstream rate.

How I would verify it: I would use a fake upstream that returns `rate=47.1234`
and request `amount=250`. The correct calculation is
`250 * 47.1234 = 11780.85`. The current code rounds first to `47.12`, so it
calculates `11780.00`.

## The one I would fix before shipping tonight

I would fix the first finding: exceptions should not be converted into a
successful-looking `rate: 0.0` response. They should return a non-2xx status
with `{ "error": "...", "message": "..." }`.

## Things that look suspicious but are fine

Being right about a non-issue is worth as much as finding a real defect.
