---
name: fluveo-integrate
description: Integrate a merchant's software with the Fluveo payments API over raw HTTP (no SDK). Use whenever the user wants to accept payments, charge a card, take a payment, create a payment intent, confirm or capture a payment, authorize now and capture later, refund a payment (full or partial), build a checkout, use hosted checkout or Checkout Sessions, create a payment link, save a customer or card, list charges, check balance or balance transactions, create products, prices, invoices or subscriptions, migrate from Stripe to Fluveo, or mentions Fluveo, api.fluveo.dev, sk_test keys, Stripe-compatible payments, PaymentIntent, refund, checkout session, or payment link. Also use when handling Fluveo API errors, idempotency keys, retries, 3DS / requires_action, or asking what Fluveo does or does not support.
---

# Fluveo integration (raw HTTP, no SDK)

Fluveo exposes a **Stripe-shaped `/v1` API**. You call it directly with HTTP; no client library is required.
Only the 57 operations in `spec/openapi.subset.json` (plugin root) are contracted. Everything else is
"not available" — see `references/not-available.md`. **Read the relevant reference file before writing code.**

## Wire format (memorise this block)

```
Base URL      https://api.fluveo.dev            (local dev: http://localhost:8080)
Auth          HTTP Basic  -u sk_test_example:   (key as username, EMPTY password, keep the colon)
          or  Authorization: Bearer sk_test_example
Keys          only sk_test_* exist today. No sk_live_*, no pk_*, no rk_*. Mode comes from the key, not the host.
Writes        Content-Type: application/x-www-form-urlencoded, Stripe bracket syntax: metadata[order_id]=ord_1
Reads         query string (?limit=10&starting_after=pi_...). Lists: { object:"list", data:[], has_more, url }
Responses     JSON, Stripe field names. Errors: { "error": { "type", "code", "message", "param" } }
Stripe-Version  omit it, or send exactly 2026-05-27.dahlia. Anything else -> 400 invalid_stripe_version
Idempotency-Key send on every write; reuse the SAME key when retrying a 5xx/timeout (see errors-and-retries.md)
Amounts       integers in the smallest currency unit (4242 = $42.42); currency is lowercase ISO 4217
Test card     4242424242424242, exp 12/2030, cvc 123 — test mode only, inline via payment_method_data[card][...]
```

## Routing table — what are you building?

| Building… | Read first | Endpoints |
|---|---|---|
| Charge a card server-side, authorize/capture, cancel, 3DS | `references/payments.md` | `/v1/payment_intents` (+ `/confirm`, `/capture`, `/cancel`), `/v1/charges` (read-only) |
| Refund (full/partial), refund status | `references/refunds.md` | `/v1/refunds` |
| Hosted checkout page, payment links, fulfilment, branding | `references/checkout.md` | `/v1/checkout/sessions`, `/v1/payment_links`, `/v1/checkout/branding` |
| Customers, saved cards, SetupIntents | `references/customers.md` | `/v1/customers`, `/v1/customers/{id}/payment_methods`, `/v1/setup_intents` |
| Catalog, invoices, subscriptions | `references/billing.md` | `/v1/products`, `/v1/prices`, `/v1/invoiceitems`, `/v1/invoices`, `/v1/subscriptions` |
| Balance, ledger, reconciliation, pagination | `references/balance.md` | `/v1/balance`, `/v1/balance_transactions` |
| Auth headers, key handling | `references/authentication.md`, `references/security.md` | — |
| Error handling, retries, idempotency, 429 | `references/errors-and-retries.md` | — |
| Porting existing Stripe code / stripe-node / stripe-python | `references/migrate-from-stripe.md` | — |
| "Does Fluveo support X?" | `references/not-available.md` | — |
| Exact parameter/field contract for one operation | use the `fluveo-docs` skill (`spec/openapi.subset.json`) | — |

## Critical rules

1. **Never invent endpoints, parameters, or response fields.** Unknown params return a named `400` (never ignored).
   Only read response fields declared in `spec/openapi.subset.json`; treat anything else as absent.
2. **No webhooks.** `/v1/webhook_endpoints` and `/v1/events` are not merchant-public. Poll `GET` on the
   single object (PaymentIntent, Checkout Session, Refund) to learn state. Never fulfil an order on a
   `success_url` visit alone — retrieve the object server-side and check `status` / `payment_status`.
3. **Secret keys stay on the server.** Never place `sk_test_*` in browser/mobile code, logs, or git.
   Never log `client_secret`. Never write card numbers into `metadata`, `description`, or logs.
4. **Saved `pm_*` ids on a PaymentIntent return 400.** Use inline `payment_method_data[type]=card` +
   `payment_method_data[card][number|exp_month|exp_year|cvc]` (test mode) or hosted Checkout.
5. **Idempotency.** PaymentIntent create/update/confirm/capture/cancel, Refund create/update, Customer
   create/update, Checkout Session create/update/expire, and Payment Link create have a 24h byte-for-byte
   replay journal (stored 5xx included). Same key + different body = `400 idempotency_error`.
6. **Lifecycle.** `requires_payment_method → (confirm) → requires_action | processing → succeeded`.
   With `capture_method=manual`: `→ requires_capture → (capture) → succeeded`; partial capture auto-refunds
   the remainder. `cancel` releases an uncaptured hold.
7. **Metadata.** ≤50 keys, key ≤40 chars, value ≤500 chars. The `fluveo_` key prefix is reserved (400).
8. **Lists** reject unsupported filters with `400` and may lag a just-written object by seconds; the
   single-object `GET` is authoritative. Cursors: `starting_after` / `ending_before` (mutually exclusive).
9. **Don't branch on `message` text.** Branch on `error.type` then `error.code`; `param` names the field.
10. Prefer raw HTTP (`curl`, `fetch`, `requests`). stripe-node / stripe-python can be pointed at
    Fluveo as an alternative (see `references/migrate-from-stripe.md`), but never rely on SDK method presence
    as proof that an endpoint exists.

## What does NOT exist (do not use, do not document as available)

Full list with workarounds in `references/not-available.md`. Highlights:

- Webhooks: `/v1/webhook_endpoints`, `/v1/events` → poll instead.
- Top-level `/v1/payment_methods` (create/attach/detach/retrieve) → only `GET /v1/customers/{customer}/payment_methods`.
- `POST /v1/charges`, charge capture/update → use PaymentIntents. Charges are read-only.
- Disputes, payouts, transfers, Connect, `Stripe-Account` header.
- `POST /v1/subscriptions/{subscription}/cancel` and subscription update; `POST /v1/invoices/{invoice}/pay`; invoice void/send.
- Product/price update or delete; invoiceitem list/retrieve/delete.
- Checkout `mode=subscription|setup`, `ui_mode=embedded`, `automatic_tax`, discounts, shipping options, `locale`.
- `sk_live_*`, `pk_*`, `rk_*` keys; Fluveo Elements in the browser needs a publishable key, which is not issued today.
- `expand[]` on most resources; `created[...]`/`type`/`currency` filters on most lists.

## Minimal end-to-end (server-side card charge)

```bash
# 1. create + confirm in one call (test card, automatic capture)
curl https://api.fluveo.dev/v1/payment_intents -u sk_test_example: \
  -H "Idempotency-Key: order-9001-charge" \
  -d amount=4242 -d currency=usd -d confirm=true \
  -d "payment_method_data[type]=card" \
  -d "payment_method_data[card][number]=4242424242424242" \
  -d "payment_method_data[card][exp_month]=12" \
  -d "payment_method_data[card][exp_year]=2030" \
  -d "payment_method_data[card][cvc]=123" \
  --data-urlencode "metadata[order_id]=ord_9001"
# 2. read status until terminal
curl https://api.fluveo.dev/v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N -u sk_test_example:
# 3. refund if needed
curl https://api.fluveo.dev/v1/refunds -u sk_test_example: \
  -H "Idempotency-Key: order-9001-refund-1" -d payment_intent=pi_1A9e8AzB2xQRH9JfQu5N -d amount=2000
```

Prefer hosted Checkout (`references/checkout.md`) when the merchant has no PCI-scoped card form.
