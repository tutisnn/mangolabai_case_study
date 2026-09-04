# Notes

## Decisions

I use Frankfurter's response `date` as `rate_date` and keep the requested date
as `asked_date`. If the ECB did not publish a rate on the requested date, such
as a weekend or holiday, the service can still answer only when Frankfurter
returns a valid earlier rate and makes that date visible.

Future dates and dates before `1999-01-04` are rejected before calling upstream.
Unsupported currencies are also rejected locally from a supported currency set.
Same-currency conversion returns `rate: 1.0` without calling upstream.

Only successful upstream payloads are cached. Failed responses or payloads
without the requested rate are not cached.

## With another day

I would refresh the supported currency list from Frankfurter metadata at startup
with a short-lived cache, and add integration smoke tests for the live
Frankfurter API outside the offline test suite.

## AI tools

I used Codex with GPT-5.5 medium to read the brief, implement the FastAPI
service, write offline tests with a fake upstream, and review edge cases against
the README.

## One thing the AI got wrong

The AI was useful for writing the code, but we disagreed on one product decision:
how to handle conversions where `from` and `to` are the same. The AI first
suggested treating that as an error. I decided the better behavior is an identity
conversion, because the tool can answer that edge case safely without making an
upstream request or inventing an exchange rate.
