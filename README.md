# FX Conversion Tool

Small FastAPI service for converting currencies with Frankfurter ECB rates.

## Run

```bash
python -m pip install -r requirements.txt
./run.sh
```

The service listens on `PORT`, defaulting to `8080`.

```bash
PORT=9090 ./run.sh
```

The upstream base URL is read from `FX_UPSTREAM_BASE`, defaulting to
`https://api.frankfurter.dev`.

```bash
FX_UPSTREAM_BASE=http://localhost:9000 ./run.sh
```

## Test

```bash
python -m pip install -r requirements.txt
./test.sh
```

Tests fake the upstream and do not require network access.

## Endpoint

```http
GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28
```

Successful response:

```json
{
  "amount": 250.0,
  "from": "EUR",
  "to": "TRY",
  "rate": 47.1234,
  "result": 11780.85,
  "rate_date": "2026-08-28",
  "asked_date": "2026-08-28",
  "source": "ECB via frankfurter.dev"
}
```

`asked_date` is the date requested by the caller. `rate_date` is the date from
the upstream response and may be earlier on weekends or holidays.

Failure response:

```json
{ "error": "short_machine_code", "message": "Human readable sentence." }
```

## Decisions

| Case | Behavior |
|---|---|
| Weekend or holiday | Use Frankfurter's returned rate if available, and expose its actual `date` as `rate_date`. |
| Future date | Reject before calling upstream. |
| Before ECB series start | Reject dates before `1999-01-04` before calling upstream. |
| Unsupported currency | Reject before calling upstream if `from` or `to` is not in the supported Frankfurter currency list. |
| Same `from` and `to` | Return an identity conversion with `rate: 1.0` without calling upstream. |
| Slow upstream | Return `504 upstream_timeout`. |
| Upstream 5xx/4xx | Return `502 upstream_error`. |
| Upstream non-JSON | Return `502 upstream_bad_json`. |
| Upstream unreachable | Return `502 upstream_unavailable`. |
| Missing or invalid query parameter | Return `422 bad_request`. |
| Zero or negative amount | Return `400 invalid_amount`. |
| Amount with more than two decimals | Return `400 amount_too_precise`. |
| Repeated successful request | Cache by `date/from/to`, so the upstream is not called again. |
| Failed request | Do not cache failed or unusable upstream responses. |

## Error Codes

| Code | HTTP status | Meaning |
|---|---:|---|
| `invalid_amount` | 400 | Amount is zero or negative. |
| `amount_too_precise` | 400 | Amount has more than two decimal places. |
| `unknown_currency` | 400 | One or both currency codes are not supported. |
| `date_in_future` | 400 | Requested date is in the future. |
| `date_before_series_start` | 400 | Requested date is before `1999-01-04`. |
| `rate_not_available` | 400 | Upstream returned no usable rate/date for the request. |
| `bad_request` | 422 | Query parameters could not be parsed or validated. |
| `upstream_error` | 502 | Upstream returned an HTTP error response. |
| `upstream_bad_json` | 502 | Upstream response was not valid JSON. |
| `upstream_unavailable` | 502 | Upstream could not be reached. |
| `upstream_timeout` | 504 | Upstream took too long to respond. |
