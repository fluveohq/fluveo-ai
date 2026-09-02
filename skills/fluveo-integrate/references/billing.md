# Billing — Products, Prices, Invoice Items, Invoices, Subscriptions

Contents: [Scope](#scope) · [Endpoints](#endpoints) · [Products](#products) · [Prices](#prices) · [Invoice items](#invoice-items) · [Invoices](#invoices) · [Hosted invoice URL](#hosted-invoice-url) · [Subscriptions](#subscriptions) · [Node and Python](#node-and-python) · [Not available](#not-available)

## Scope

The Billing surface is served by a sidecar and is deliberately narrow: **create / list / retrieve** for products,
prices, subscriptions; **create only** for invoice items; **create / list / retrieve / finalize /
hosted_invoice_url** for invoices. No update, delete, cancel, void, send or pay operations. Invoice payment happens
on the hosted invoice page, never through `POST /v1/invoices/{invoice}/pay` (not available).

Response schemas in the subset declare only a small set of fields (listed per resource below). Servers may
return more Stripe fields, but only read the declared ones.

Send `Idempotency-Key` on POSTs; Billing writes are **not** in the 24 h byte-for-byte journal — treat a retry as
"probably safe, verify by list/retrieve afterwards".

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/products` | Create product |
| `GET` | `/v1/products` | List products |
| `GET` | `/v1/products/{product}` | Retrieve product |
| `POST` | `/v1/prices` | Create price |
| `GET` | `/v1/prices` | List prices |
| `GET` | `/v1/prices/{price}` | Retrieve price |
| `POST` | `/v1/invoiceitems` | Create pending invoice item |
| `POST` | `/v1/invoices` | Create draft invoice (sweeps pending items) |
| `GET` | `/v1/invoices` | List invoices |
| `GET` | `/v1/invoices/{invoice}` | Retrieve invoice |
| `POST` | `/v1/invoices/{invoice}/finalize` | Finalize (draft → open) |
| `GET` | `/v1/invoices/{invoice}/hosted_invoice_url` | Hosted payment page URL (Fluveo extension) |
| `POST` | `/v1/subscriptions` | Create subscription + first invoice |
| `GET` | `/v1/subscriptions` | List subscriptions |
| `GET` | `/v1/subscriptions/{subscription}` | Retrieve subscription |

No query parameters are declared on the Billing list operations in the subset; the resource docs say `limit`
(1–100, default 10), `starting_after`, `ending_before` work. Send nothing else.

## Products

Body: `name` (required), `description`, `metadata[key]`. Declared response fields: `id` (`prod_...`), `object`,
`name`, `description`, `active`.

```bash
curl https://api.fluveo.dev/v1/products -u sk_test_example: -H "Idempotency-Key: prod-pro-plan" \
  --data-urlencode "name=Pro Plan" --data-urlencode "description=Monthly Pro subscription"
curl https://api.fluveo.dev/v1/products/prod_N5xG3aBcDeFgHi -u sk_test_example:
curl -G https://api.fluveo.dev/v1/products -u sk_test_example: -d limit=20
```

```json
{ "id": "prod_N5xG3aBcDeFgHi", "object": "product", "name": "Pro Plan", "description": "Monthly Pro subscription", "active": true }
```

## Prices

Body: `product` (required), `currency` (required, lowercase), `unit_amount` (required, minor units),
`recurring[interval]` (`day` | `week` | `month` | `year`), `recurring[interval_count]`, `metadata`. Omit
`recurring` for a one-time price. Declared response: `id` (`price_...`), `object`, `product`, `currency`,
`unit_amount`, `active`, `recurring`.

```bash
curl https://api.fluveo.dev/v1/prices -u sk_test_example: -H "Idempotency-Key: price-pro-monthly" \
  -d product=prod_N5xG3aBcDeFgHi -d currency=usd -d unit_amount=2900 \
  -d "recurring[interval]=month" -d "recurring[interval_count]=1"
curl https://api.fluveo.dev/v1/prices/price_1N5xH2aBcDeFgHiJ -u sk_test_example:
curl -G https://api.fluveo.dev/v1/prices -u sk_test_example: -d limit=20
```

```json
{ "id": "price_1N5xH2aBcDeFgHiJ", "object": "price", "product": "prod_N5xG3aBcDeFgHi", "currency": "usd",
  "unit_amount": 2900, "active": true, "recurring": { "interval": "month", "interval_count": 1 } }
```

## Invoice items

Body: `customer` (required), `amount` (minor units; negative = credit) **or** `price`, `description`, `metadata`.
A pending item (no invoice yet) is swept into the customer's next invoice at create/finalize. Declared response:
`id` (`ii_...`), `object`, `customer`.

```bash
curl https://api.fluveo.dev/v1/invoiceitems -u sk_test_example: -H "Idempotency-Key: ii-order-77-1" \
  -d customer=cus_9R8e8AzB2xQRH9Jf -d amount=1500 --data-urlencode "description=Setup fee"
```

```json
{ "id": "ii_1N5xJ4aBcDeFgHiK", "object": "invoiceitem", "customer": "cus_9R8e8AzB2xQRH9Jf" }
```

There is no list/retrieve/delete for invoice items; keep the returned `id` yourself.

## Invoices

Create body: `customer` (required), `collection_method` (`send_invoice` | `charge_automatically`; use
`send_invoice` for the hosted page flow), `due_date` (unix; only with `send_invoice`, else `400 invalid_due_date`),
`default_payment_method`, `mandate`, `description`, `footer`, `metadata`. Free-text fields are scanned for
card-number-like digit runs and rejected.

Declared response fields: `id` (`in_...`), `object`, `customer`, `status` (`draft` | `open` | `paid` | `void` |
`uncollectible`), `collection_method`, `currency`, `total`, `amount_due`, `amount_paid`, `lines[]`
(`id`, `object: "line_item"`, `description`, `amount`, `currency`), `subscription`, `payment_intent`, `number`
(assigned at finalize), `due_date`, `description`, `footer`.

```bash
# 1. draft (sweeps the customer's pending invoice items)
curl https://api.fluveo.dev/v1/invoices -u sk_test_example: -H "Idempotency-Key: inv-order-77" \
  -d customer=cus_9R8e8AzB2xQRH9Jf -d collection_method=send_invoice -d due_date=1772000000 \
  --data-urlencode "description=Order 77"
# 2. finalize -> status open, number assigned
curl -X POST https://api.fluveo.dev/v1/invoices/in_1N5xK6aBcDeFgHiL/finalize -u sk_test_example: \
  -H "Idempotency-Key: inv-order-77-finalize"
# 3. read
curl https://api.fluveo.dev/v1/invoices/in_1N5xK6aBcDeFgHiL -u sk_test_example:
curl -G https://api.fluveo.dev/v1/invoices -u sk_test_example: -d limit=20
```

Create response (abbreviated):

```json
{ "id": "in_1N5xK6aBcDeFgHiL", "object": "invoice", "customer": "cus_9R8e8AzB2xQRH9Jf", "status": "draft",
  "collection_method": "send_invoice", "currency": "usd", "total": 1500, "amount_due": 1500, "amount_paid": 0,
  "due_date": 1772000000, "description": "Order 77",
  "lines": [ { "id": "ii_1N5xJ4aBcDeFgHiK", "object": "line_item", "description": "Setup fee", "amount": 1500, "currency": "usd" } ] }
```

Finalize response (declared fields only): `{ "id": "in_1N5xK6aBcDeFgHiL", "object": "invoice", "status": "open", "total": 1500, "payment_intent": null }`.

Track payment by polling `GET /v1/invoices/{invoice}` until `status == "paid"` (`amount_paid == total`).

## Hosted invoice URL

```bash
curl https://api.fluveo.dev/v1/invoices/in_1N5xK6aBcDeFgHiL/hosted_invoice_url -u sk_test_example:
```

```json
{ "invoice": "in_1N5xK6aBcDeFgHiL", "hosted_invoice_url": "/i/opaque-signed-token" }
```

`hosted_invoice_url` is **site-relative to the API origin** (prefix `https://api.fluveo.dev`). It carries no
secrets; send it to the customer.

## Subscriptions

Create body: `customer` (required), `items[0][price]` (required), `items[0][quantity]`, `collection_method`,
`payment_behavior` (`default_incomplete` default | `error_if_incomplete` | `allow_incomplete`),
`default_payment_method`, `mandate`, `start_date` (unix), `trial_period_days` (1–730), `cancel_at` (unix),
`metadata`. With the default `default_incomplete`, the subscription is created `incomplete` together with its
first invoice; the customer pays via that invoice's hosted page.

Declared response: `id` (`sub_...`), `object`, `customer`, `status` (`incomplete` | `incomplete_expired` |
`trialing` | `active` | `past_due` | `unpaid` | `canceled`), `latest_invoice`, `current_period_start`,
`current_period_end`, `cancel_at_period_end`, `canceled_at`, `cancel_at`, `trial_end`, `items` (list of
`subscription_item` with `price`, `quantity`).

```bash
curl https://api.fluveo.dev/v1/subscriptions -u sk_test_example: -H "Idempotency-Key: sub-user-501-pro" \
  -d customer=cus_9R8e8AzB2xQRH9Jf -d "items[0][price]=price_1N5xH2aBcDeFgHiJ" -d "items[0][quantity]=1" \
  -d payment_behavior=default_incomplete
curl https://api.fluveo.dev/v1/subscriptions/sub_1N5xM8aBcDeFgHiN -u sk_test_example:
curl -G https://api.fluveo.dev/v1/subscriptions -u sk_test_example: -d limit=20
```

```json
{ "id": "sub_1N5xM8aBcDeFgHiN", "object": "subscription", "customer": "cus_9R8e8AzB2xQRH9Jf", "status": "incomplete",
  "latest_invoice": "in_1N5xN0aBcDeFgHiP", "current_period_start": 1769412345, "current_period_end": 1772090745,
  "cancel_at_period_end": false, "canceled_at": null, "cancel_at": null, "trial_end": null,
  "items": { "object": "list", "url": "/v1/subscription_items?subscription=sub_1N5xM8aBcDeFgHiN",
             "data": [ { "id": "si_1N5xM8aBcDeFgHiQ", "object": "subscription_item", "quantity": 1,
                         "price": { "id": "price_1N5xH2aBcDeFgHiJ", "object": "price", "product": "prod_N5xG3aBcDeFgHi",
                                    "currency": "usd", "unit_amount": 2900, "active": true,
                                    "recurring": { "interval": "month", "interval_count": 1 } } } ] } }
```

Flow: create → read `latest_invoice` → `GET /v1/invoices/{invoice}/hosted_invoice_url` → send to customer →
poll `GET /v1/subscriptions/{subscription}` until `status == "active"`.

**There is no cancel or update.** To stop a subscription today, set `cancel_at` at creation time, or contact
Fluveo support; do not call `POST /v1/subscriptions/{subscription}/cancel` or `DELETE` (not available).

## Node and Python

```js
const H = { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`, "Content-Type": "application/x-www-form-urlencoded" };
const post = (path, form, key) => fetch("https://api.fluveo.dev" + path, { method: "POST",
  headers: { ...H, "Idempotency-Key": key }, body: new URLSearchParams(form) }).then(r => r.json());

const product = await post("/v1/products", { name: "Pro Plan" }, "prod-pro-plan");
const price = await post("/v1/prices", { product: product.id, currency: "usd", unit_amount: "2900", "recurring[interval]": "month" }, "price-pro-monthly");
const sub = await post("/v1/subscriptions", { customer: "cus_9R8e8AzB2xQRH9Jf", "items[0][price]": price.id }, "sub-user-501-pro");
const hosted = await (await fetch(`https://api.fluveo.dev/v1/invoices/${sub.latest_invoice}/hosted_invoice_url`, { headers: H })).json();
const payUrl = "https://api.fluveo.dev" + hosted.hosted_invoice_url;
```

```python
import os, requests
AUTH = (os.environ["FLUVEO_API_KEY"], ""); BASE = "https://api.fluveo.dev"
def post(path, data, key): return requests.post(BASE + path, auth=AUTH, data=data, headers={"Idempotency-Key": key}).json()

item = post("/v1/invoiceitems", {"customer": "cus_9R8e8AzB2xQRH9Jf", "amount": 1500, "description": "Setup fee"}, "ii-order-77-1")
inv = post("/v1/invoices", {"customer": "cus_9R8e8AzB2xQRH9Jf", "collection_method": "send_invoice", "due_date": 1772000000}, "inv-order-77")
inv = post(f"/v1/invoices/{inv['id']}/finalize", {}, "inv-order-77-finalize")
hosted = requests.get(f"{BASE}/v1/invoices/{inv['id']}/hosted_invoice_url", auth=AUTH).json()
pay_url = BASE + hosted["hosted_invoice_url"]
```

## Not available

`POST /v1/products/{product}` (update), `DELETE /v1/products/{product}`, `POST /v1/prices/{price}`,
`GET|DELETE /v1/invoiceitems/{invoiceitem}`, `GET /v1/invoiceitems`, `POST /v1/invoices/{invoice}` (update),
`POST /v1/invoices/{invoice}/pay`, `/void`, `/send`, `DELETE /v1/invoices/{invoice}`,
`POST /v1/subscriptions/{subscription}` (update), `DELETE /v1/subscriptions/{subscription}`,
`POST /v1/subscriptions/{subscription}/cancel`, subscription items, subscription schedules, coupons, promotion
codes, credit notes, tax rates, quotes. See `not-available.md`.
