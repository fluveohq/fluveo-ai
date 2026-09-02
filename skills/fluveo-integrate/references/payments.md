# Payments — PaymentIntents and Charges

Contents: [Endpoints](#endpoints) · [Lifecycle](#lifecycle) · [Create](#create) · [Confirm with an inline test card](#confirm-with-an-inline-test-card) · [Create + confirm in one call](#create--confirm-in-one-call) · [3DS / requires_action](#3ds--requires_action) · [Manual capture](#manual-capture) · [Cancel](#cancel) · [Retrieve and poll](#retrieve-and-poll) · [Update](#update) · [List](#list) · [Charges (read-only)](#charges-read-only) · [Node and Python](#node-and-python) · [Errors](#errors)

## Endpoints

| Method | Path | Idempotency-Key | Purpose |
|---|---|---|---|
| `POST` | `/v1/payment_intents` | 24h journal | Create |
| `GET` | `/v1/payment_intents/{intent}` | — | Retrieve (authoritative state) |
| `POST` | `/v1/payment_intents/{intent}` | 24h journal | Update |
| `POST` | `/v1/payment_intents/{intent}/confirm` | 24h journal | Confirm with card data |
| `POST` | `/v1/payment_intents/{intent}/capture` | 24h journal | Capture (manual mode) |
| `POST` | `/v1/payment_intents/{intent}/cancel` | 24h journal | Cancel / release hold |
| `GET` | `/v1/payment_intents` | — | List |
| `GET` | `/v1/charges/{charge}` | — | Retrieve charge (read-only) |
| `GET` | `/v1/charges` | — | List charges (read-only) |

There is **no** `POST /v1/charges`; money moves only through PaymentIntents.

## Lifecycle

```
requires_payment_method
        │  POST /confirm  (payment_method_data[type]=card + card fields)
        ▼
requires_confirmation ─┐ (rare)
        ▼              │
requires_action ───────┤  3DS / redirect: next_action.redirect_to_url.url (test simulator only)
        ▼              │
processing ────────────┤
        ▼              ▼
   succeeded   ◄── capture_method=automatic (default)

   requires_capture     ◄── capture_method=manual, after confirm
        │  POST /capture  (amount_to_capture ≤ amount; partial auto-refunds the rest)
        ▼
   succeeded

   canceled             ◄── POST /cancel from any non-terminal state
```

`status` enum: `requires_payment_method`, `requires_confirmation`, `requires_action`, `processing`,
`requires_capture`, `succeeded`, `canceled`. Only `succeeded` means money was captured.

## Create

Contracted body fields (`application/x-www-form-urlencoded`): `amount` (required, integer minor units),
`currency` (required, lowercase ISO 4217), `capture_method` (`automatic` default | `automatic_async` | `manual`),
`confirm` (boolean), `customer` (`cus_...`), `description`, `metadata[key]`, `payment_method_data` (only with
`confirm=true`), `receipt_email`, `return_url`, `setup_future_usage` (`on_session` | `off_session`, needs
`customer`), `statement_descriptor_suffix`. Anything else is a named `400`.

```bash
curl https://api.devfluveo.com/v1/payment_intents \
  -u sk_test_example: \
  -H "Idempotency-Key: order-9001-create" \
  -d amount=4242 \
  -d currency=usd \
  -d customer=cus_9R8e8AzB2xQRH9Jf \
  --data-urlencode "metadata[order_id]=ord_9001"
```

Response `200` (abbreviated; all fields below are in the contract):

```json
{
  "id": "pi_1A9e8AzB2xQRH9JfQu5N",
  "object": "payment_intent",
  "status": "requires_payment_method",
  "amount": 4242,
  "amount_capturable": 0,
  "amount_received": 0,
  "currency": "usd",
  "capture_method": "automatic",
  "client_secret": "pi_1A9e8AzB2xQRH9JfQu5N_secret_REDACTED",
  "customer": "cus_9R8e8AzB2xQRH9Jf",
  "description": null,
  "latest_charge": null,
  "payment_method": null,
  "payment_method_types": ["card"],
  "next_action": null,
  "last_payment_error": null,
  "receipt_email": null,
  "setup_future_usage": null,
  "metadata": { "order_id": "ord_9001" },
  "created": 1769349712,
  "livemode": false
}
```

Keep `id`. Treat `client_secret` as a secret (never log it, never send it to a browser unless you are using
Fluveo Elements — see `not-available.md`).

## Confirm with an inline test card

Confirm body fields: `payment_method_data`, `receipt_email`, `return_url`, `setup_future_usage`.
`payment_method_data[type]` must be `card`; `payment_method_data[card][number|exp_month|exp_year|cvc]` are all
required. **A saved `pm_*` id (`payment_method=pm_...`) returns a named `400`** — it is not supported.
Non-card types return `400`.

Test card (test mode only): number `4242424242424242`, `exp_month=12`, `exp_year=2030`, `cvc=123`.

```bash
curl https://api.devfluveo.com/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N/confirm \
  -u sk_test_example: \
  -H "Idempotency-Key: order-9001-confirm" \
  -d "payment_method_data[type]=card" \
  -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" \
  -d "payment_method_data[card][exp_year]=2030" \
  -d "payment_method_data[card][cvc]=123" \
  --data-urlencode "return_url=https://merchant.example.com/checkout/return"
```

Response `200` (abbreviated, automatic capture):

```json
{
  "id": "pi_1A9e8AzB2xQRH9JfQu5N",
  "object": "payment_intent",
  "status": "succeeded",
  "amount": 4242,
  "amount_received": 4242,
  "currency": "usd",
  "latest_charge": "ch_3R9k8AzB2xQRH9Jf",
  "payment_method": null,
  "next_action": null,
  "last_payment_error": null,
  "livemode": false
}
```

Card data is transient: never store it, never put it in `metadata`/`description`, never log request bodies.
Raw card fields are not part of the idempotency fingerprint (a same-key retry with a different card replays the
first result).

## Create + confirm in one call

Send `confirm=true` together with `payment_method_data` on create:

```bash
curl https://api.devfluveo.com/v1/payment_intents \
  -u sk_test_example: \
  -H "Idempotency-Key: order-9001-charge" \
  -d amount=4242 -d currency=usd -d confirm=true \
  -d "payment_method_data[type]=card" \
  -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" \
  -d "payment_method_data[card][exp_year]=2030" \
  -d "payment_method_data[card][cvc]=123"
```

## 3DS / requires_action

After confirm, branch on `status`:

| `status` | Meaning | Your move |
|---|---|---|
| `succeeded` | Captured (automatic) | Fulfil. |
| `requires_capture` | Authorized (manual) | Capture later. |
| `requires_action` | Cardholder must authenticate | Send the customer to `next_action.redirect_to_url.url`; they return to `return_url`. Then **retrieve** the PaymentIntent. |
| `processing` | PSP settling | Poll `GET` until terminal. |
| `requires_payment_method` | Declined / auth failed | Read `last_payment_error`; ask for another card. |

`next_action`, when non-null, is `{ "type": "redirect_to_url", "redirect_to_url": { "url": "...", "return_url": "..." } }`.
Pass `return_url` on confirm (or create) or a 3DS-required card returns `403 authentication_required`.
Today only the built-in test simulator emits `redirect_to_url`; real-PSP challenges are fail-closed with
`next_action: null`. Never trust the redirect back to `return_url` — always `GET` the PaymentIntent.

## Manual capture

```bash
# authorize
curl https://api.devfluveo.com/v1/payment_intents \
  -u sk_test_example: -H "Idempotency-Key: order-9002-auth" \
  -d amount=4242 -d currency=usd -d capture_method=manual -d confirm=true \
  -d "payment_method_data[type]=card" \
  -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" \
  -d "payment_method_data[card][exp_year]=2030" \
  -d "payment_method_data[card][cvc]=123"
# -> "status": "requires_capture", "amount_capturable": 4242

# capture (full: omit amount_to_capture; partial: amount_to_capture < amount auto-refunds the remainder)
curl https://api.devfluveo.com/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N/capture \
  -u sk_test_example: -H "Idempotency-Key: order-9002-capture" \
  -d amount_to_capture=4000 \
  -d statement_descriptor_suffix=ORDER9002
# -> "status": "succeeded", "amount_received": 4000
```

Capture body fields: `amount_to_capture`, `statement_descriptor_suffix` only (`statement_descriptor` → 400).

## Cancel

Releases an uncaptured authorization; nothing is charged. Body: optional `cancellation_reason`
(`abandoned` | `duplicate` | `fraudulent` | `requested_by_customer`).

```bash
curl https://api.devfluveo.com/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N/cancel \
  -u sk_test_example: -H "Idempotency-Key: order-9002-cancel" \
  -d cancellation_reason=requested_by_customer
# -> "status": "canceled", "cancellation_reason": "requested_by_customer", "canceled_at": 1769350000
```

A `succeeded` intent cannot be cancelled — create a refund instead (`refunds.md`).

## Retrieve and poll

```bash
curl https://api.devfluveo.com/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N -u sk_test_example:
```

Because there are no webhooks, this is the completion signal. Poll with backoff (e.g. 1s, 2s, 4s… cap 30s)
until `status` ∈ {`succeeded`, `requires_capture`, `canceled`, `requires_payment_method`}. `404 resource_missing`
means the id does not exist for this merchant.

## Update

`POST /v1/payment_intents/{intent}` accepts `amount`, `currency`, `customer`, `description`, `metadata`,
`receipt_email`, `setup_future_usage`, `statement_descriptor_suffix`. Metadata merges by key; an empty
`metadata[key]=` removes that key; a bare `metadata=` clears all public keys.

```bash
curl https://api.devfluveo.com/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N \
  -u sk_test_example: -H "Idempotency-Key: order-9001-meta-1" \
  --data-urlencode "metadata[shipment]=shp_77" -d description="Order 9001"
```

## List

`GET /v1/payment_intents?limit=10&customer=cus_...&starting_after=pi_...` — query params: `limit` (1–100,
default 10), `customer`, `starting_after`, `ending_before` (mutually exclusive). Any other filter → `400`.

```bash
curl -G https://api.devfluveo.com/v1/payment_intents -u sk_test_example: -d limit=20 -d customer=cus_9R8e8AzB2xQRH9Jf
```

```json
{ "object": "list", "url": "/v1/payment_intents", "has_more": false,
  "data": [ { "id": "pi_1A9e8AzB2xQRH9JfQu5N", "object": "payment_intent", "amount": 4242, "currency": "usd",
              "status": "succeeded", "client_secret": null, "next_action": null, "last_payment_error": null } ] }
```

List rows always return `client_secret`, `next_action` and `last_payment_error` as `null`, and the list can lag a
just-written object by seconds. Use retrieve for flow state.

## Charges (read-only)

A successful PaymentIntent exposes its charge as `latest_charge` (`ch_...`). Charges are projections; you
cannot create, capture or update them.

```bash
curl https://api.devfluveo.com/v1/charges/ch_3R9k8AzB2xQRH9Jf -u sk_test_example:
curl -G https://api.devfluveo.com/v1/charges -u sk_test_example: -d payment_intent=pi_1A9e8AzB2xQRH9JfQu5N
```

List query params: `limit`, `starting_after`, `ending_before`, `customer`, `payment_intent`.

```json
{
  "id": "ch_3R9k8AzB2xQRH9Jf", "object": "charge", "amount": 4242, "amount_captured": 4242, "amount_refunded": 0,
  "currency": "usd", "customer": "cus_9R8e8AzB2xQRH9Jf", "payment_intent": "pi_1A9e8AzB2xQRH9JfQu5N",
  "status": "succeeded", "captured": true, "paid": true, "refunded": false, "disputed": false,
  "balance_transaction": null, "receipt_url": null, "failure_code": null, "failure_message": null,
  "payment_method_details": { "type": "card", "card": { "brand": null, "last4": null, "exp_month": null, "exp_year": null } },
  "billing_details": {}, "metadata": {}, "created": 1769412345, "livemode": false
}
```

`balance_transaction` and `receipt_url` are currently `null`; card sub-fields may be `null`.

## Node and Python

```js
// Node 18+: create+confirm, then poll. Form-encode with URLSearchParams (bracket keys are literal).
const key = process.env.FLUVEO_API_KEY;
const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
const headers = { Authorization: `Bearer ${key}`, "User-Agent": "myshop/1.0" };

async function fluveo(method, path, form, idempotencyKey) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      ...headers,
      ...(form ? { "Content-Type": "application/x-www-form-urlencoded" } : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: form ? new URLSearchParams(form).toString() : undefined,
  });
  const body = await res.json();
  if (!res.ok) { const e = new Error(body.error.message); e.fluveo = body.error; e.status = res.status; throw e; }
  return body;
}

const pi = await fluveo("POST", "/v1/payment_intents", {
  amount: "4242", currency: "usd", confirm: "true",
  "payment_method_data[type]": "card",
  "payment_method_data[card][number]": "4242424242424242",   // test mode only
  "payment_method_data[card][exp_month]": "12",
  "payment_method_data[card][exp_year]": "2030",
  "payment_method_data[card][cvc]": "123",
  "metadata[order_id]": "ord_9001",
}, "order-9001-charge");

let state = pi;
for (let delay = 1000; !["succeeded", "requires_capture", "canceled", "requires_payment_method"].includes(state.status); delay = Math.min(delay * 2, 30000)) {
  await new Promise(r => setTimeout(r, delay));
  state = await fluveo("GET", `/v1/payment_intents/${pi.id}`);
}
```

```python
import os, time, requests

BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
AUTH = (os.environ["FLUVEO_API_KEY"], "")   # Basic auth, empty password

def fluveo(method, path, data=None, idempotency_key=None):
    headers = {"User-Agent": "myshop/1.0"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    r = requests.request(method, BASE + path, auth=AUTH, data=data, headers=headers, timeout=30)
    body = r.json()
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {body['error']['type']} {body['error'].get('code')}: {body['error']['message']}")
    return body

pi = fluveo("POST", "/v1/payment_intents", {
    "amount": 4242, "currency": "usd", "capture_method": "manual", "confirm": "true",
    "payment_method_data[type]": "card",
    "payment_method_data[card][number]": "4242424242424242",   # test mode only
    "payment_method_data[card][exp_month]": "12",
    "payment_method_data[card][exp_year]": "2030",
    "payment_method_data[card][cvc]": "123",
}, idempotency_key="order-9002-auth")

delay = 1
while pi["status"] not in ("succeeded", "requires_capture", "canceled", "requires_payment_method"):
    time.sleep(delay); delay = min(delay * 2, 30)
    pi = fluveo("GET", f"/v1/payment_intents/{pi['id']}")

if pi["status"] == "requires_capture":
    pi = fluveo("POST", f"/v1/payment_intents/{pi['id']}/capture", {"amount_to_capture": 4242}, "order-9002-capture")
```

## Errors

| HTTP | `error.code` | Cause / action |
|---|---|---|
| 400 | `parameter_missing` | Required field absent — `param` names it. |
| 400 | `amount_too_small` / `amount_too_large` | Outside connector limits. |
| 400 | (named `invalid_request_error`, `param` set) | Unsupported param, `pm_*` id, non-card type, `metadata[fluveo_*]`. |
| 402 | `card_declined` (+ `decline_code`), `expired_card`, `incorrect_cvc` | Show a generic decline; do not auto-retry. |
| 403 | `authentication_required` | 3DS needed and no `return_url` given. |
| 404 | `resource_missing` | Unknown id or another merchant's id. |
| 400 | `idempotency_error` | Same key, different body/endpoint. |
| 409 | `api_error` | Same key still executing — wait and retry with the same key. |
| 429 | `rate_limit_error` | Honour `Retry-After`. |
| 5xx | `api_error` | Retry with the **same** `Idempotency-Key`. |

Full handling guidance: `errors-and-retries.md`.
