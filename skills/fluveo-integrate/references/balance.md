# Balance and balance transactions

Contents: [Endpoints](#endpoints) · [Balance](#balance) · [Balance transactions](#balance-transactions) · [Pagination cookbook](#pagination-cookbook) · [Reconciling a payment](#reconciling-a-payment) · [Errors](#errors)

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/balance` | Current available / pending funds per currency |
| `GET` | `/v1/balance_transactions` | Ledger entries (charges, refunds, fees…) |
| `GET` | `/v1/balance_transactions/{id}` | One ledger entry |

Read-only; no `Idempotency-Key` needed. Money truth is the ledger, not the PaymentIntent list.

## Balance

```bash
curl https://api.devfluveo.com/v1/balance -u sk_test_example:
```

```json
{
  "object": "balance",
  "livemode": false,
  "available": [ { "amount": 423800, "currency": "usd", "source_types": { "card": 423800 } } ],
  "pending":   [ { "amount": 12450,  "currency": "usd", "source_types": { "card": 12450 } } ],
  "instant_available": [],
  "connect_reserved": []
}
```

`available` may be negative (refunds/chargebacks/fees exceeding funds). `pending` = captured, not yet
promoted to available. `instant_available` / `connect_reserved` are always empty (no Instant Payouts, no Connect).
Amounts are minor units.

## Balance transactions

Query params: `limit` (1–100, default 10), `starting_after`, `ending_before`, `source` (exact merchant-facing
source id, e.g. `ch_...`), `expand[]`. **Not** supported (→ `400`): `created[gt|gte|lt|lte]`, `type`, `currency`,
`payout`. An unknown `source` is a `400`, never an empty list.

```bash
curl -G https://api.devfluveo.com/v1/balance_transactions -u sk_test_example: -d limit=5
curl -G https://api.devfluveo.com/v1/balance_transactions -u sk_test_example: -d source=ch_3R9k8AzB2xQRH9Jf
curl https://api.devfluveo.com/v1/balance_transactions/txn_R9k8AzB2xQRH9Jf -u sk_test_example:
```

```json
{
  "object": "list", "url": "/v1/balance_transactions", "has_more": false,
  "data": [
    { "id": "txn_R9k8AzB2xQRH9Jf", "object": "balance_transaction",
      "amount": 4242, "fee": 115, "net": 4127, "currency": "usd",
      "type": "charge", "source": "ch_3R9k8AzB2xQRH9Jf", "status": "available",
      "created": 1769412345, "available_on": 1769671545, "description": "Charge ch_3R9k8AzB2xQRH9Jf" }
  ]
}
```

`type` values you will see: `charge`, `refund`, `payout`, `application_fee`, `dispute`, `dispute_reversal`,
`adjustment`. For a charge, `net = amount − fee − reserve`. `available_on` is ledger availability, not bank
settlement. Ids may be `txn_...` or `bt_...`.

## Pagination cookbook

Newest first. Pass the last `id` of a page as `starting_after`; stop when `has_more` is `false` (or `data` is
empty). Never send both cursors. Cursors are merchant-scoped; a foreign/unknown cursor is `400`.

```bash
# curl: repeat until has_more is false
curl -G https://api.devfluveo.com/v1/balance_transactions -u sk_test_example: -d limit=100 -d starting_after=txn_R9k8AzB2xQRH9Jf
```

```js
async function* balanceTransactions(limit = 100) {
  const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
  const headers = { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`, "User-Agent": "myshop/1.0" };
  let startingAfter;
  for (;;) {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (startingAfter) qs.set("starting_after", startingAfter);
    const res = await fetch(`${BASE}/v1/balance_transactions?${qs}`, { headers });
    const page = await res.json();
    if (!res.ok) throw new Error(`${page.error.type}: ${page.error.message}`);
    for (const txn of page.data) yield txn;
    if (!page.has_more || page.data.length === 0) return;
    startingAfter = page.data[page.data.length - 1].id;
  }
}
for await (const txn of balanceTransactions()) console.log(txn.id, txn.type, txn.net, txn.currency);
```

```python
import os, requests
AUTH = (os.environ["FLUVEO_API_KEY"], "")
BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
UA = {"User-Agent": "myshop/1.0"}

def balance_transactions(limit=100):
    params = {"limit": limit}
    while True:
        r = requests.get(f"{BASE}/v1/balance_transactions", auth=AUTH, params=params, headers=UA)
        page = r.json()
        if not r.ok:
            raise RuntimeError(page["error"])
        yield from page["data"]
        if not page["has_more"] or not page["data"]:
            return
        params["starting_after"] = page["data"][-1]["id"]

for txn in balance_transactions():
    print(txn["id"], txn["type"], txn["net"], txn["currency"])
```

The same loop works for every list endpoint (`/v1/refunds`, `/v1/customers`, `/v1/payment_intents`, …) —
only the supported filters differ. Handle `429` (`Retry-After`) and `503 ledger_unavailable` with backoff
inside the loop and resume with the same cursor.

## Reconciling a payment

1. `GET /v1/payment_intents/{intent}` → `latest_charge` (`ch_...`).
2. `GET /v1/balance_transactions?source=ch_...` → the `charge` row (`fee`, `net`, `available_on`) and, after a
   refund, a `refund` row.
3. `GET /v1/balance` to confirm the aggregate. Refund objects currently carry `balance_transaction: null`, so
   join via `source` on the charge side.

## Errors

| HTTP | `error.code` | Cause |
|---|---|---|
| 400 | `invalid_request_error` | Unsupported filter (`created`, `type`, `currency`, `payout`), bad cursor, unknown `source`. |
| 401 | `invalid_request_error` | Bad key. |
| 404 | `resource_missing` | Unknown balance transaction id. |
| 503 | `ledger_unavailable` | Ledger service unreachable; retry with backoff (never returns a fake zero balance). |
