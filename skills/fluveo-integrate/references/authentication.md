# Authentication

Contents: [Base URL and mode](#base-url-and-mode) · [Two auth schemes](#two-auth-schemes) · [Headers to send / never send](#headers-to-send--never-send) · [Stripe-Version](#stripe-version) · [Examples](#examples) · [Auth failures](#auth-failures) · [Key lifecycle](#key-lifecycle)

## Base URL and mode

| | Value |
|---|---|
| API (current environment) | `https://api.devfluveo.com` |
| Dashboard | `https://dashboard.devfluveo.com` |
| Local development | `http://localhost:8080` |
| Key namespace issued today | `sk_test_*` only |

Read the base URL from an env var (`FLUVEO_API_BASE`, default `https://api.devfluveo.com`) so it can change
per environment. The older `api.` host on `fluveo.dev` referenced in upstream docs does **not** resolve today.

Test mode is selected **by the key**, not by a sandbox hostname. Fluveo does not issue `sk_live_*`,
publishable (`pk_*`) or restricted (`rk_*`) keys. An `sk_live_*`-shaped value is rejected before parsing.
Do not invent key prefixes.

## Getting a key

1. Sign up at `https://dashboard.devfluveo.com/signup` (no email verification).
2. Create a merchant: business name + region (US → `usd`).
3. The dashboard shows the `sk_test_*` key **once** — store it in a secret manager or `.env` as `FLUVEO_API_KEY`.
4. Verify: `curl "$FLUVEO_API_BASE/v1/balance" -u "$FLUVEO_API_KEY:" -H "User-Agent: myshop/1.0"` → `200`.

### Scripted sign-up (dashboard-internal routes)

The dashboard exposes the same steps as JSON routes. They are **not** part of the `/v1` contract and may change;
the UI at `/signup` is the supported path. Keep one cookie jar across both calls and send an `Origin` header.

```bash
D=https://dashboard.devfluveo.com
curl -s -c jar -b jar "$D/api/auth/signup" -H "Origin: $D" -H "Content-Type: application/json" -A "Mozilla/5.0" \
  -d '{"email":"dev@merchant.example","password":"correct-horse-battery","terms_accepted":true}'
# {"ok":true,"merchant_id":null}
curl -s -c jar -b jar "$D/api/merchants" -H "Origin: $D" -H "Content-Type: application/json" -A "Mozilla/5.0" \
  -d '{"display_name":"My Shop","region":"us"}'
# 201 {"merchant_id":"mch_...","display_name":"My Shop","region":"us","secret_key":"sk_test_example"}
```

`secret_key` is returned **only** in that `201` response — store it immediately.

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
- `User-Agent: <your-app>/<version>` — always. The edge (Cloudflare) rejects Python-urllib's default UA with a
  plain-text `403 error code: 1010`, not the JSON error envelope. `python-requests`, curl and Node fetch pass.

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
curl https://api.devfluveo.com/v1/balance -u sk_test_example: -H "User-Agent: myshop/1.0"

# Bearer
curl https://api.devfluveo.com/v1/balance -H "Authorization: Bearer sk_test_example" -H "User-Agent: myshop/1.0"
```

```js
// Node 18+ (fetch). Key from the environment, never hard-coded.
const key = process.env.FLUVEO_API_KEY;
const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
const res = await fetch(`${BASE}/v1/balance`, {
  headers: { Authorization: `Bearer ${key}`, "User-Agent": "myshop/1.0" },
});
const body = await res.json();
if (!res.ok) throw new Error(`${body.error.type}: ${body.error.message}`);
```

```python
import os, requests
key = os.environ["FLUVEO_API_KEY"]
BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
r = requests.get(f"{BASE}/v1/balance", auth=(key, ""), headers={"User-Agent": "myshop/1.0"})
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
