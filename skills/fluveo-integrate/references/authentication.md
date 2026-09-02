# Authentication

Contents: [Base URL and mode](#base-url-and-mode) · [Two auth schemes](#two-auth-schemes) · [Headers to send / never send](#headers-to-send--never-send) · [Stripe-Version](#stripe-version) · [Examples](#examples) · [Auth failures](#auth-failures) · [Key lifecycle](#key-lifecycle)

## Base URL and mode

| | Value |
|---|---|
| Production API | `https://api.fluveo.dev` |
| Local development | `http://localhost:8080` |
| Key namespace issued today | `sk_test_*` only |

Test mode is selected **by the key**, not by a sandbox hostname. Fluveo does not issue `sk_live_*`,
publishable (`pk_*`) or restricted (`rk_*`) keys. An `sk_live_*`-shaped value is rejected before parsing.
Do not invent key prefixes.

## Two auth schemes

| Scheme | Wire form |
|---|---|
| HTTP Basic | secret key as username, **empty password**: `-u sk_test_example:` (the trailing colon matters) |
| Bearer | exactly one token: `Authorization: Bearer sk_test_example` |

Both are equivalent for every contracted `/v1` operation. Pick one and use it consistently.

## Headers to send / never send

Send:

- `Authorization` (Basic or Bearer) — required on every `/v1` call.
- `Content-Type: application/x-www-form-urlencoded` on POST/PUT bodies (curl `-d` sets it for you).
- `Idempotency-Key: <your-unique-string>` on writes (1–255 bytes). See `errors-and-retries.md`.
- `Stripe-Version: 2026-05-27.dahlia` — optional; see below.

Never send (each is rejected with a Stripe-shaped `400`, or `401` if sent alone):

- `api-key` (Hyperswitch-native), `Stripe-Account`, `X-Connected-Merchant-Id`, processor/profile/connector ids.
- A second credential header, or a non-empty Basic password.
- A duplicate `Idempotency-Key` header, an empty one, or one longer than 255 bytes.

## Stripe-Version

The contract is pinned to Stripe API `2026-05-27.dahlia`.

| You send | Result |
|---|---|
| no `Stripe-Version` header | pinned version is used |
| `Stripe-Version: 2026-05-27.dahlia` | accepted |
| any other value, or the header repeated | `400 invalid_stripe_version` |

Responses echo `Stripe-Version`.

## Examples

```bash
# Basic
curl https://api.fluveo.dev/v1/balance -u sk_test_example:

# Bearer
curl https://api.fluveo.dev/v1/balance -H "Authorization: Bearer sk_test_example"
```

```js
// Node 18+ (fetch). Key from the environment, never hard-coded.
const key = process.env.FLUVEO_API_KEY;
const res = await fetch("https://api.fluveo.dev/v1/balance", {
  headers: { Authorization: `Bearer ${key}` },
});
const body = await res.json();
if (!res.ok) throw new Error(`${body.error.type}: ${body.error.message}`);
```

```python
import os, requests
key = os.environ["FLUVEO_API_KEY"]
r = requests.get("https://api.fluveo.dev/v1/balance", auth=(key, ""))
body = r.json()
if not r.ok:
    raise RuntimeError(f"{body['error']['type']}: {body['error']['message']}")
```

Abbreviated `200` response (`GET /v1/balance`):

```json
{
  "object": "balance",
  "livemode": false,
  "available": [ { "amount": 423800, "currency": "usd", "source_types": { "card": 423800 } } ],
  "pending":   [ { "amount": 12450,  "currency": "usd", "source_types": { "card": 12450 } } ]
}
```

## Auth failures

A missing, malformed, unknown, or revoked key returns `401` with `error.type = "invalid_request_error"`.
The message never reveals whether the key once existed. Fix the credential; do not retry blindly.

## Key lifecycle

- Keys are created/revoked on the dashboard API Keys page. The full value is shown **once**; store it in a
  secret manager and read it from an environment variable (`FLUVEO_API_KEY`).
- Rotate by issuing a replacement, deploying it, then revoking the old key. Revocation takes effect within
  at most five seconds for new requests; in-flight requests are not cancelled.
- Treat any exposed key as compromised and rotate immediately.
- See `security.md` for browser, logging and PCI rules.
