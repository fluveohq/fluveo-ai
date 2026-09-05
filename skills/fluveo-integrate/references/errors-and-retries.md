# Errors, idempotency and retries

Contents: [Envelope](#envelope) · [Error types](#error-types) · [Common codes](#common-codes) · [Business-rule refusals](#business-rule-refusals) · [Idempotency journal](#idempotency-journal) · [Retry policy](#retry-policy) · [429 backoff](#429-backoff) · [Stripe-Version](#stripe-version) · [What to show users](#what-to-show-users) · [Reference client](#reference-client)

## Envelope

Every non-2xx response is JSON:

```json
{
  "error": {
    "type": "invalid_request_error",
    "code": "amount_too_small",
    "message": "Amount must be at least 50",
    "param": "amount"
  }
}
```

| Field | Use |
|---|---|
| `type` | Branch control flow on this. |
| `code` | Machine-readable reason (may be absent). |
| `message` | For logs. May change; never parse it. Never show raw to end users. |
| `param` | The offending request field (when applicable). |
| `decline_code` | Present on `card_error` declines; for your logs, not the cardholder. |

Messages are redacted fail-closed: they never carry internal processor/connector identifiers.

## Error types

| `type` | HTTP | Meaning | What to do |
|---|---|---|---|
| `invalid_request_error` | 400 | Malformed/missing/unsupported field, or a business-rule refusal. | Fix `param` when present; when absent, use the refusal guidance below. |
| `invalid_request_error` | 401 | Missing/invalid/revoked key. | Fix credentials. |
| `invalid_request_error` | 403 (`authentication_required`) | 3DS needed, no `return_url`. | Re-confirm with `return_url`. |
| `invalid_request_error` | 404 (`resource_missing`) | Unknown id or another merchant's id. | Do not retry. |
| `card_error` | 402 | Card declined / failed a check. | Show a generic decline; let the customer try another card. Never auto-retry. |
| `idempotency_error` | 400 | Key reused with a different body or endpoint. | Bug: use a fresh key for a new operation, or resend the original request unchanged. |
| `api_error` | 409 | Same `Idempotency-Key` is still executing / ambiguous. | Wait (`Retry-After` if present, else ~2s) and retry the **same** key. |
| `rate_limit_error` | 429 | Too many requests. | Honour `Retry-After`; exponential backoff. |
| `api_error` | 5xx | Fluveo-side failure. | Retry with the **same** `Idempotency-Key` (journaled ops) — see below. |
| — | 503 (`ledger_unavailable`) | Ledger unreachable on balance reads. | Backoff and retry. |

Also: `400 invalid_stripe_version` for a bad `Stripe-Version` header.

## Common codes

| HTTP | `code` | Cause |
|---|---|---|
| 400 | `parameter_missing` | Required field absent. |
| 400 | `amount_too_small` / `amount_too_large` | Outside connector limits. |
| 400 | `invalid_due_date` | Invoice `due_date` without `collection_method=send_invoice`. |
| 400 | `idempotency_error` | Key/body mismatch. |
| 400 | `invalid_stripe_version` | Unsupported/repeated `Stripe-Version`. |
| 400 | `invalid_request_error`, message `This account is not enabled for payments yet.` | The merchant's payments onboarding (Stripe Connect verification, done by the owner in the dashboard) is not approved yet. Stop and tell the account owner; do **not** retry in a loop and do not look for workarounds. |
| 402 | `card_declined` (+`decline_code`), `expired_card`, `incorrect_cvc` | Card problems. |
| 403 | `authentication_required` | 3DS required without `return_url`. |
| 404 | `resource_missing` | Unknown object. |
| 404 | `unsupported_operation` | A quarantined Stripe path (e.g. top-level `/v1/payment_methods`). |
| 429 | `rate_limit_error` | Back off. |
| 500 | `api_error` | Retry same key. |
| 503 | `ledger_unavailable` | Retry with backoff. |

## Business-rule refusals

A `400 invalid_request_error` can have no `param` and use a plain-language `message` for a business rule rather
than a malformed field. Do not treat a missing `param` as a broken error response. These known messages mean:

- `This account does not have enough available balance to refund this payment.` — no refund was created. Check
  `GET /v1/balance` → `available` and the charge row's `available_on` in `GET /v1/balance_transactions`. Wait
  for funds to become available or request a smaller partial refund.
- `This account is not enabled for payouts yet.` on a refund right after a sale — no refund was created. Wait
  2–3 minutes for account reconciliation, then resend the unchanged refund with the **same** `Idempotency-Key`.
- `This account is not enabled for payments yet.` — the account owner must finish payments onboarding and be
  approved. Stop and tell the owner; do not retry in a loop or try to bypass approval.

Do not build general control flow by parsing `message`; prefer `type`, `code`, and `param`. The exact messages
above are documented operator guidance for the current business-rule responses, which do not yet carry a code.

## Non-JSON responses from the edge

Cloudflare sits in front of the API and returns a plain-text `403 error code: 1010` (not the JSON envelope) for
requests whose `User-Agent` is `Python-urllib/*`; `python-requests`, curl and Node fetch pass. Never assume an
error body parses as JSON: on a non-JSON 4xx, log the status and the first 200 bytes of the body. Fix: always
send an explicit `User-Agent: <your-app>/<version>`.

## Idempotency journal

`Idempotency-Key` (1–255 bytes, one header) is accepted on POST writes (the docs do not state whether `PUT /v1/checkout/branding` honours it; sending it there is harmless but unverified). Two tiers:

**Durable 24 h byte-for-byte journal** — PaymentIntent create/update/confirm/capture/cancel; Refund
create/update; Customer create/update; Checkout Session create/update/expire; Payment Link create.
Scope: `(merchant, mode, key)`. Rules:

- Identical retry → the original status + body (even a stored `5xx`), with `Idempotent-Replayed: true`.
- Same key, different non-sensitive body, different object id, or different endpoint → `400 idempotency_error`,
  no second mutation.
- Concurrent duplicate → `409 api_error`, never cached; retry later with the same key.
- Ambiguous execution (crash mid-way) stays fail-closed: you keep getting `409` until Fluveo reconciles. Do
  **not** start the operation over with a new key while the outcome is ambiguous.
- Pre-effect validation failures release the key, so a corrected request may reuse it.
- Raw card fields are not fingerprinted: same key + different card + same other params replays the first result.
- After 24 h the key can start a new generation (a replayed create would then make a new object).

**Resource-local semantics** — everything else (SetupIntents, Payment Link update/expire, Billing writes,
Checkout Branding). Send a key anyway, but verify via `GET`/list after a retried timeout.

Key derivation: use your own stable operation id — `order-9001-charge`, `order-9001-refund-1`,
`signup-user-501`. Never a random UUID per attempt (that defeats replay), never the same key for two
different operations on one order.

## Retry policy

```
if 2xx                    -> done
if 400/401/402/403/404    -> do not retry (fix input / surface decline)
if 400 idempotency_error  -> bug; do not retry blindly
if 409 api_error          -> sleep(Retry-After or 2s), retry SAME key, max ~10 tries
if 429                    -> sleep(Retry-After), retry SAME key
if 5xx / timeout / conn   -> exponential backoff (1s,2s,4s,… cap 30s, jitter), retry SAME key, max ~5 tries
after retries exhausted   -> for money ops, GET the object (or list) before declaring failure
```

Timeouts on a write are **indeterminate**: the request may have executed. Always retry with the same key or read
back the state; never issue a second create with a fresh key.

## 429 backoff

`429` carries `Retry-After` (seconds). Sleep at least that long; on repeated 429s double the wait with jitter
and reduce concurrency. Do not spread load by rotating keys.

## Stripe-Version

Omit the header or send exactly `Stripe-Version: 2026-05-27.dahlia`. Any other value (or a repeated header) is
`400 invalid_stripe_version`. If you point stripe-node/stripe-python at Fluveo, set `apiVersion` to that string.

## What to show users

| Situation | User-facing text | Log |
|---|---|---|
| `card_error` | "Your card was declined. Try another card." | `code`, `decline_code`, `pi_` id |
| `requires_action` | Redirect to `next_action.redirect_to_url.url` | — |
| `invalid_request_error` | Generic "something went wrong" (it is your bug) | `param`, `message` |
| `429`, `5xx`, `409` | "Processing…" while retrying; then "Please try again" | status, key, attempt count |
| `idempotency_error` | Generic; alert engineering | key, both bodies' hashes |

Never show `message` verbatim, never show `client_secret`, keys, or ids beyond your own order number.

## Reference client

```python
import os, time, random, requests

BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
AUTH = (os.environ["FLUVEO_API_KEY"], "")

class FluveoError(Exception):
    def __init__(self, status, err):
        super().__init__(f"{status} {err.get('type')} {err.get('code')}: {err.get('message')}")
        self.status, self.type, self.code, self.param = status, err.get("type"), err.get("code"), err.get("param")

def request(method, path, data=None, params=None, idempotency_key=None, max_tries=6):
    headers = {"Stripe-Version": "2026-05-27.dahlia", "User-Agent": "myshop/1.0"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    delay = 1.0
    for attempt in range(1, max_tries + 1):
        try:
            r = requests.request(method, BASE + path, auth=AUTH, data=data, params=params, headers=headers, timeout=30)
        except requests.RequestException:
            if attempt == max_tries or not idempotency_key:
                raise
            time.sleep(delay + random.random()); delay = min(delay * 2, 30); continue
        if r.ok:
            return r.json()
        try:
            err = r.json().get("error", {})
        except ValueError:  # non-JSON body from the edge (e.g. Cloudflare 403 1010)
            err = {"type": "edge_error", "message": r.text[:200]}
        retry_after = float(r.headers.get("Retry-After", 0) or 0)
        if r.status_code in (409, 429) or r.status_code >= 500:
            if attempt == max_tries:
                raise FluveoError(r.status_code, err)
            time.sleep(max(retry_after, delay) + random.random()); delay = min(delay * 2, 30); continue
        raise FluveoError(r.status_code, err)
```

```js
// Node 18+ equivalent
const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
const sleep = ms => new Promise(r => setTimeout(r, ms));
export async function fluveo(method, path, { form, idempotencyKey, maxTries = 6 } = {}) {
  const headers = { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`, "Stripe-Version": "2026-05-27.dahlia",
                    "User-Agent": "myshop/1.0" };
  if (form) headers["Content-Type"] = "application/x-www-form-urlencoded";
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  let delay = 1000;
  for (let attempt = 1; ; attempt++) {
    let res;
    try {
      res = await fetch(BASE + path, { method, headers, body: form ? new URLSearchParams(form).toString() : undefined });
    } catch (e) {
      if (attempt >= maxTries || !idempotencyKey) throw e;
      await sleep(delay + Math.random() * 500); delay = Math.min(delay * 2, 30000); continue;
    }
    const text = await res.text();
    let body;
    try { body = JSON.parse(text); } catch { body = { error: { type: "edge_error", message: text.slice(0, 200) } }; }
    if (res.ok) return body;
    const retryAfter = Number(res.headers.get("Retry-After") || 0) * 1000;
    if ((res.status === 409 || res.status === 429 || res.status >= 500) && attempt < maxTries) {
      await sleep(Math.max(retryAfter, delay) + Math.random() * 500); delay = Math.min(delay * 2, 30000); continue;
    }
    const err = new Error(`${res.status} ${body.error?.type} ${body.error?.code ?? ""}: ${body.error?.message}`);
    Object.assign(err, { status: res.status, fluveo: body.error }); throw err;
  }
}
```
