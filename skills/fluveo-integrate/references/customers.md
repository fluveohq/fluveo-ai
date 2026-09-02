# Customers, saved payment methods, SetupIntents

Contents: [Endpoints](#endpoints) · [Create](#create) · [Retrieve / update / delete](#retrieve--update--delete) · [List](#list) · [Customer payment methods](#customer-payment-methods) · [SetupIntents (save a card)](#setupintents-save-a-card) · [Using a saved card](#using-a-saved-card) · [Node and Python](#node-and-python)

## Endpoints

| Method | Path | Idempotency-Key | Purpose |
|---|---|---|---|
| `POST` | `/v1/customers` | 24h journal | Create |
| `GET` | `/v1/customers/{customer}` | — | Retrieve |
| `POST` | `/v1/customers/{customer}` | 24h journal | Update |
| `DELETE` | `/v1/customers/{customer}` | — | Delete (tombstone) |
| `GET` | `/v1/customers` | — | List |
| `GET` | `/v1/customers/{customer}/payment_methods` | — | List saved cards (first page only) |
| `POST` | `/v1/setup_intents` | resource-local | Create SetupIntent |
| `GET` | `/v1/setup_intents/{setup_intent}` | — | Retrieve |
| `POST` | `/v1/setup_intents/{setup_intent}` | resource-local | Update |
| `POST` | `/v1/setup_intents/{setup_intent}/confirm` | resource-local | Confirm |
| `POST` | `/v1/setup_intents/{setup_intent}/cancel` | resource-local | Cancel |
| `GET` | `/v1/setup_intents` | — | **Declared, but returns a named 400** (see below) |

## Create

Exactly six accepted fields: `email`, `name`, `phone`, `description`, `address[line1|line2|city|state|postal_code|country]`,
`metadata[key]`. `payment_method`, `shipping`, `invoice_settings` etc. → named `400`.

```bash
curl https://api.fluveo.dev/v1/customers \
  -u sk_test_example: \
  -H "Idempotency-Key: signup-user-501" \
  -d email=ada@example.com \
  --data-urlencode "name=Ada Lovelace" \
  -d phone=+15551234567 \
  --data-urlencode "address[line1]=123 Analytical Engine Way" \
  -d "address[city]=London" -d "address[country]=GB" \
  --data-urlencode "metadata[user_id]=501"
```

```json
{
  "id": "cus_9R8e8AzB2xQRH9Jf",
  "object": "customer",
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "phone": "+15551234567",
  "description": null,
  "address": { "line1": "123 Analytical Engine Way", "line2": null, "city": "London", "state": null, "postal_code": null, "country": "GB" },
  "balance": 0,
  "currency": null,
  "default_source": null,
  "delinquent": false,
  "shipping": null,
  "metadata": { "user_id": "501" },
  "created": 1769349712,
  "livemode": false
}
```

Store `id`; it is stable. Idempotent create: same key + same body within 24 h returns the same `cus_*`
(`Idempotent-Replayed: true`); after 24 h a new customer would be created.

## Retrieve / update / delete

```bash
curl https://api.fluveo.dev/v1/customers/cus_9R8e8AzB2xQRH9Jf -u sk_test_example:

curl https://api.fluveo.dev/v1/customers/cus_9R8e8AzB2xQRH9Jf -u sk_test_example: \
  -H "Idempotency-Key: cus-501-update-3" \
  -d email=ada@newdomain.example --data-urlencode "metadata[tier]=gold"

curl -X DELETE https://api.fluveo.dev/v1/customers/cus_9R8e8AzB2xQRH9Jf -u sk_test_example:
```

Update uses metadata patch semantics (empty `metadata[key]=` deletes; bare `metadata=` clears all).
Delete returns the tombstone `{ "id": "cus_9R8e8AzB2xQRH9Jf", "object": "customer", "deleted": true }`, clears
PII (`email`, `name`, `phone`, `address`), keeps historical payments/refunds attached to the id, excludes the
customer from lists, and makes later updates `404 resource_missing`. Retrieve of a deleted customer returns the
same tombstone — check `deleted` before reading other fields.

## List

Query params: `limit` (1–100), `starting_after`, `ending_before`, `email` (exact match; empty value → 400),
`search` (Fluveo extension: case-insensitive substring over name, email, id). Other filters → `400`.
The list is a projection that can lag a just-created customer; retrieve is authoritative.

```bash
curl -G https://api.fluveo.dev/v1/customers -u sk_test_example: -d email=ada@example.com
curl -G https://api.fluveo.dev/v1/customers -u sk_test_example: -d limit=50 -d starting_after=cus_9R8e8AzB2xQRH9Jf
```

## Customer payment methods

`GET /v1/customers/{customer}/payment_methods` — the **only** contracted PaymentMethod operation. Query params:
`limit` (1–100) and optional `type=card`. `starting_after`, `ending_before`, `expand[]` → named `400`, so only
the first page is reachable even if `has_more` is `true`.

```bash
curl -G https://api.fluveo.dev/v1/customers/cus_9R8e8AzB2xQRH9Jf/payment_methods -u sk_test_example: -d type=card -d limit=10
```

```json
{ "object": "list", "url": "/v1/customers/cus_9R8e8AzB2xQRH9Jf/payment_methods", "has_more": false,
  "data": [ { "id": "pm_1N3T00LkdIwHu7ixRdxpVI1Q", "object": "payment_method", "type": "card",
              "customer": "cus_9R8e8AzB2xQRH9Jf", "created": 1769349900, "livemode": false, "metadata": {},
              "billing_details": { "address": { "city": null, "country": null, "line1": null, "line2": null, "postal_code": null, "state": null }, "email": null, "name": null, "phone": null },
              "card": { "brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030, "funding": "credit", "country": "US", "fingerprint": null } } ] }
```

Never returns PAN/CVC. `metadata` is always `{}`. Top-level `/v1/payment_methods` (retrieve, attach, detach,
create, delete) is **not available** — see `not-available.md`.

## SetupIntents (save a card)

SetupIntents are served in test mode and declared in the OpenAPI subset, but Fluveo labels them
`served_uncontracted`: no parity, stability or SDK guarantee. Do not build a production dependency on them yet.
Body fields (create/update/confirm): `customer`, `confirm`, `currency`, `description`, `metadata`,
`payment_method_data[type]=card` + `payment_method_data[card][number|exp_month|exp_year|cvc]`,
`payment_method_data[billing_details]`, `receipt_email`, `return_url`, `setup_future_usage`
(`off_session` | `on_session`), `client_secret`. Cancel body: `cancellation_reason`.

```bash
curl https://api.fluveo.dev/v1/setup_intents \
  -u sk_test_example: -H "Idempotency-Key: seti-user-501-1" \
  -d customer=cus_9R8e8AzB2xQRH9Jf -d confirm=true -d setup_future_usage=off_session \
  -d "payment_method_data[type]=card" \
  -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" \
  -d "payment_method_data[card][exp_year]=2030" \
  -d "payment_method_data[card][cvc]=123"
```

```json
{
  "id": "seti_1A9e8AzB2xQRH9JfQu5N",
  "object": "setup_intent",
  "status": "succeeded",
  "customer": "cus_9R8e8AzB2xQRH9Jf",
  "payment_method": "pm_1N3T00LkdIwHu7ixRdxpVI1Q",
  "payment_method_types": ["card"],
  "usage": "off_session",
  "client_secret": "seti_1A9e8AzB2xQRH9JfQu5N_secret_REDACTED",
  "next_action": null,
  "last_setup_error": null,
  "mandate": null,
  "metadata": {},
  "created": 1769349900,
  "livemode": false
}
```

`status` enum: `requires_payment_method`, `requires_confirmation`, `requires_action`, `processing`,
`succeeded`, `canceled`. Retrieve / confirm / cancel:

```bash
curl https://api.fluveo.dev/v1/setup_intents/seti_1A9e8AzB2xQRH9JfQu5N -u sk_test_example:
curl https://api.fluveo.dev/v1/setup_intents/seti_1A9e8AzB2xQRH9JfQu5N/confirm -u sk_test_example: \
  -d "payment_method_data[type]=card" -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" -d "payment_method_data[card][exp_year]=2030" -d "payment_method_data[card][cvc]=123"
curl https://api.fluveo.dev/v1/setup_intents/seti_1A9e8AzB2xQRH9JfQu5N/cancel -u sk_test_example: -d cancellation_reason=abandoned
```

**`GET /v1/setup_intents` (list)** is declared with `limit`/`starting_after`/`ending_before`/`customer` but its
only documented response is a `400` error envelope (contract test "authenticated-safe-400"). Do not use it; list
a customer's saved cards via `GET /v1/customers/{customer}/payment_methods` instead.

## Using a saved card

Today a saved `pm_*` **cannot** be passed to `POST /v1/payment_intents` or `/confirm` (`payment_method=pm_...`
→ named `400`). So the practical value of a saved card is: showing "Visa •••• 4242" to the customer, and
`setup_future_usage` on a PaymentIntent for future promotion. To charge again, either collect the card again
(inline `payment_method_data` in test mode) or send the customer through hosted Checkout with `customer=cus_...`.
Re-check `not-available.md` for updates before assuming this changed.

## Node and Python

```js
const r = await fetch("https://api.fluveo.dev/v1/customers", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`,
             "Content-Type": "application/x-www-form-urlencoded",
             "Idempotency-Key": `signup-user-${userId}` },
  body: new URLSearchParams({ email, name, "metadata[user_id]": String(userId) }),
});
const customer = await r.json();
if (!r.ok) throw new Error(customer.error.message);
```

```python
import os, requests
AUTH = (os.environ["FLUVEO_API_KEY"], "")
customer = requests.post("https://api.fluveo.dev/v1/customers", auth=AUTH,
    headers={"Idempotency-Key": f"signup-user-{user_id}"},
    data={"email": email, "name": name, "metadata[user_id]": user_id}).json()
cards = requests.get(f"https://api.fluveo.dev/v1/customers/{customer['id']}/payment_methods",
    auth=AUTH, params={"type": "card", "limit": 10}).json()["data"]
```
