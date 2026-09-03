# Refunds

Contents: [Endpoints](#endpoints) · [Full refund](#full-refund) · [Partial refund](#partial-refund) · [Refunding by charge](#refunding-by-charge) · [Idempotency](#idempotency) · [Statuses](#statuses) · [Retrieve and poll](#retrieve-and-poll) · [Update metadata](#update-metadata) · [List](#list) · [Node and Python](#node-and-python) · [Errors](#errors)

## Endpoints

| Method | Path | Idempotency-Key | Purpose |
|---|---|---|---|
| `POST` | `/v1/refunds` | 24h journal | Create (full or partial) |
| `GET` | `/v1/refunds/{refund}` | — | Retrieve |
| `POST` | `/v1/refunds/{refund}` | 24h journal | Update (metadata only) |
| `GET` | `/v1/refunds` | — | List |

Refunds apply to a **captured** PaymentIntent (`status: succeeded`). To release an uncaptured authorization use
`POST /v1/payment_intents/{intent}/cancel` instead (`payments.md`). Fluveo fees are not returned on refund.

Create body fields: `payment_intent` (required, `pi_...`), `amount` (integer minor units; omit for full),
`reason` (`duplicate` | `fraudulent` | `requested_by_customer`), `metadata[key]`. Anything else → named `400`.

## Full refund

```bash
curl https://api.devfluveo.com/v1/refunds \
  -u sk_test_example: \
  -H "Idempotency-Key: order-9001-refund-full" \
  -d payment_intent=pi_1A9e8AzB2xQRH9JfQu5N \
  -d reason=requested_by_customer
```

Response `200` (one possible shape — `failure_reason`, `pending_reason`, `next_action` and `receipt_number` are
optional and are **omitted**, not `null`, on live responses; read them defensively):

```json
{
  "id": "re_3R9k8AzB2xQRH9Jf",
  "object": "refund",
  "amount": 4242,
  "currency": "usd",
  "payment_intent": "pi_1A9e8AzB2xQRH9JfQu5N",
  "charge": "ch_3R9k8AzB2xQRH9Jf",
  "status": "succeeded",
  "reason": "requested_by_customer",
  "balance_transaction": null,
  "failure_reason": null,
  "pending_reason": null,
  "next_action": null,
  "receipt_number": null,
  "created": 1769412345,
  "metadata": {}
}
```

Notes: `balance_transaction` is currently always `null` (the refund still appears in
`GET /v1/balance_transactions` as `type: "refund"`). There is **no `livemode`** on Refund objects.

## Partial refund

```bash
curl https://api.devfluveo.com/v1/refunds \
  -u sk_test_example: \
  -H "Idempotency-Key: order-9001-refund-1" \
  -d payment_intent=pi_1A9e8AzB2xQRH9JfQu5N \
  -d amount=2000 \
  --data-urlencode "metadata[ticket]=sup_5521"
```

Multiple partial refunds are allowed up to the captured amount. Use a **different** `Idempotency-Key` per
distinct refund (e.g. `order-9001-refund-1`, `-2`); reusing the key with a different `amount` returns
`400 idempotency_error`, and reusing it with the same body returns the first refund again (no double refund).

## Refunding by charge

The contracted create body only declares `payment_intent`. If you hold a `ch_...` id, resolve it first:
`GET /v1/charges/{charge}` → read `payment_intent` → create the refund with that. (Fluveo docs mention a
`charge` parameter, but it is not in the OpenAPI subset; do not rely on it.)

## Idempotency

Refund create and update are in the 24-hour byte-for-byte replay journal, scoped to
`(merchant, mode, Idempotency-Key)`. A replay carries `Idempotent-Replayed: true`. On a timeout or `5xx`,
retry with the **same** key. A concurrent duplicate gets `409 api_error` — wait and retry the same key.

## Statuses

| `status` | Meaning | Action |
|---|---|---|
| `succeeded` | Processed by the PSP; ledger posted. | Done. |
| `pending` | Accepted, not yet settled. | Poll `GET /v1/refunds/{refund}`. |
| `failed` | Rejected by the PSP. | Inspect `failure_reason`; contact support / retry with a new key if appropriate. |
| `requires_action` | Customer interaction required (rare, region-specific). | Inspect `next_action`. |

## Retrieve and poll

```bash
curl https://api.devfluveo.com/v1/refunds/re_3R9k8AzB2xQRH9Jf -u sk_test_example:
```

No webhooks exist: if a refund is `pending`, poll this endpoint with backoff until terminal.

## Update metadata

Only `metadata` is updatable. Merge semantics: supplied keys merge, an empty `metadata[key]=` deletes the key.

```bash
curl https://api.devfluveo.com/v1/refunds/re_3R9k8AzB2xQRH9Jf \
  -u sk_test_example: -H "Idempotency-Key: refund-meta-1" \
  --data-urlencode "metadata[ticket]=sup_5521"
```

## List

Query params: `limit` (1–100), `starting_after`, `ending_before` **only**. Stripe's `charge` /
`payment_intent` filters and `expand[]` are not contracted and return `400`. The list is a read model
that may lag a just-created refund by a few seconds.

```bash
curl -G https://api.devfluveo.com/v1/refunds -u sk_test_example: -d limit=50 -d starting_after=re_3R9k8AzB2xQRH9Jf
```

```json
{ "object": "list", "url": "/v1/refunds", "has_more": false,
  "data": [ { "id": "re_3R9k8AzB2xQRH9Jf", "object": "refund", "amount": 2000, "currency": "usd",
              "payment_intent": "pi_1A9e8AzB2xQRH9JfQu5N", "charge": "ch_3R9k8AzB2xQRH9Jf",
              "status": "succeeded", "reason": null, "created": 1769412345, "metadata": {} } ] }
```

To find refunds for one payment, filter client-side on `payment_intent`.

## Node and Python

```js
const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
const res = await fetch(`${BASE}/v1/refunds`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`,
    "User-Agent": "myshop/1.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Idempotency-Key": `order-9001-refund-1`,
  },
  body: new URLSearchParams({ payment_intent: "pi_1A9e8AzB2xQRH9JfQu5N", amount: "2000", reason: "requested_by_customer" }),
});
const refund = await res.json();
if (!res.ok) throw new Error(`${refund.error.type}: ${refund.error.message}`);
```

```python
import os, requests
BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
r = requests.post(
    f"{BASE}/v1/refunds",
    auth=(os.environ["FLUVEO_API_KEY"], ""),
    headers={"User-Agent": "myshop/1.0", "Idempotency-Key": "order-9001-refund-1"},
    data={"payment_intent": "pi_1A9e8AzB2xQRH9JfQu5N", "amount": 2000, "reason": "requested_by_customer"},
)
refund = r.json()
if not r.ok:
    raise RuntimeError(refund["error"])
```

## Errors

| HTTP | `error.type` / `code` | Cause |
|---|---|---|
| 400 | `invalid_request_error` | Missing/invalid param, unsupported field, amount above refundable balance, bad cursor (`param` set). |
| 400 | `idempotency_error` | Key reused with different parameters or endpoint. |
| 401 | `invalid_request_error` | Bad key. |
| 404 | `invalid_request_error` / `resource_missing` | Refund or PaymentIntent not found for this merchant. |
| 409 | `api_error` | Same key executing concurrently; retry later with the same key. |
| 5xx | `api_error` | Retry with the same key. |
