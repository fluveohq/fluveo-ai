# Migrating from Stripe

Contents: [Step 1 — base URL and key](#step-1--base-url-and-key) · [Step 2 — keep only contracted operations](#step-2--keep-only-contracted-operations) · [Divergence table](#divergence-table) · [Pointing stripe-node / stripe-python at Fluveo](#pointing-stripe-node--stripe-python-at-fluveo) · [Webhooks](#webhooks) · [Migration checklist](#migration-checklist)

Fluveo's `/v1` is shape-compatible with a **curated subset** of Stripe API `2026-05-27.dahlia` — same paths,
field names, form encoding, list envelope, error envelope. It is not the whole Stripe API. Migrate operation by
operation against `spec/openapi.subset.json`.

## Step 1 — base URL and key

| | Stripe | Fluveo |
|---|---|---|
| Base URL | `https://api.stripe.com` | `https://api.fluveo.dev` |
| Secret | `STRIPE_SECRET_KEY` (`sk_test_`/`sk_live_`) | `FLUVEO_API_KEY` (`sk_test_*` only) |
| Publishable key | `pk_*` | not issued |
| Restricted key | `rk_*` | not issued |
| Auth | Basic or Bearer | Basic or Bearer (identical) |
| API version header | `Stripe-Version: <any supported>` | omit or exactly `2026-05-27.dahlia`; else `400` |
| Test vs live | by key | by key (only test exists) |
| Connect (`Stripe-Account`) | yes | rejected `400` |

## Step 2 — keep only contracted operations

Keep a Stripe call only if `METHOD /v1/path` exists in the subset (57 operations). Use the `fluveo-docs` skill to
check. Everything else — even if your Stripe SDK has a method for it — is listed in `not-available.md` with a
workaround.

## Divergence table

| Area | Stripe | Fluveo |
|---|---|---|
| Unknown params | silently ignored (mostly) | **named `400`** — audit every call for extra params |
| Unknown list filters | ignored / applied | **`400`** (e.g. `created[gte]`, `currency`, `type` on most lists) |
| `expand[]` | broad | only `balance_transactions` declares it; elsewhere `400` |
| Saved payment methods on PI | `payment_method=pm_...` | **`400`**; inline `payment_method_data[card]` (test) or hosted Checkout |
| Card entry | Stripe.js / Elements with `pk_` | hosted Checkout / Payment Links; Elements needs a `pk_` that is not issued |
| Charges | create/capture/update | read-only projection (`latest_charge`) |
| Refund create | `charge` or `payment_intent` | `payment_intent` only in the contract |
| Refund object | has `livemode` | no `livemode`; `balance_transaction` is `null` |
| Idempotency | 24 h replay on all writes | 24 h byte-for-byte on 14 journaled ops (incl. stored 5xx); resource-local elsewhere; concurrent duplicate → `409 api_error`; ambiguous execution fail-closed |
| Idempotency mismatch | `400 idempotency_error` | same |
| `metadata` | 50 keys / 40 / 500 | same, plus `fluveo_*` prefix reserved (`400`) |
| PaymentIntent list | includes `client_secret`, `next_action` | always `null` in lists; retrieve for flow state |
| List freshness | strongly consistent | read models may lag seconds; retrieve is authoritative |
| `next_action` | many types | only `redirect_to_url`, and only from the test simulator; real PSP → `null` |
| Checkout `mode` | payment/subscription/setup | `payment` only |
| Checkout `ui_mode` | hosted/embedded/custom | hosted only (`ui_mode: "hosted_page"` in responses) |
| Checkout update | metadata only | metadata + `customer_email` + `shipping_details` (additive) |
| Checkout `line_items[][price]` | catalog prices | inline `price_data` only |
| Payment Links | line items with prices | flat `amount`+`currency` **or** inline `price_data`; `expires_at` extension; reactivation of completed/expired link → `400` |
| Checkout branding | dashboard | `GET|PUT /v1/checkout/branding` (extension) |
| Invoice pay | `POST /invoices/{id}/pay` | not available; `hosted_invoice_url` extension |
| Subscriptions | full lifecycle | create/list/retrieve only |
| Products/prices | update/delete | create/list/retrieve only |
| Customer create | many fields | exactly `email`, `name`, `phone`, `description`, `address`, `metadata` |
| Customer list | `email`, `created` | `email` (exact) + Fluveo `search` |
| Customer PMs | `/v1/payment_methods?customer=` or nested | nested only, first page only (`starting_after` → `400`) |
| SetupIntents | contracted | served but `served_uncontracted`; list returns `400` |
| Webhooks | `/v1/webhook_endpoints`, events | **none**; poll |
| Balance | `available`, `pending`, `instant_available`… | `instant_available`/`connect_reserved` always empty |
| Disputes, payouts, transfers, Radar, Issuing, Terminal, Tax | yes | none |
| Error messages | may include internals | redacted; branch on `type`/`code` |

## Pointing stripe-node / stripe-python at Fluveo

Officially supported as an alternative to raw HTTP; the SDK's transport, encoding and error classes work.
Caveats: SDK method presence ≠ server support (a call outside the subset returns `404`/`400`), and set
`apiVersion` exactly.

```js
import Stripe from "stripe";
const fluveo = new Stripe(process.env.FLUVEO_API_KEY, {
  host: "api.fluveo.dev",
  protocol: "https",
  port: 443,
  apiVersion: "2026-05-27.dahlia",
  maxNetworkRetries: 0, // do your own retries so the same Idempotency-Key is reused deliberately
});
const pi = await fluveo.paymentIntents.create(
  { amount: 4242, currency: "usd", metadata: { order_id: "ord_9001" } },
  { idempotencyKey: "order-9001-create" },
);
```

```python
import os, stripe
stripe.api_key = os.environ["FLUVEO_API_KEY"]
stripe.api_base = "https://api.fluveo.dev"
stripe.api_version = "2026-05-27.dahlia"
stripe.max_network_retries = 0

pi = stripe.PaymentIntent.create(
    amount=4242, currency="usd", metadata={"order_id": "ord_9001"},
    idempotency_key="order-9001-create",
)
```

Do not use `stripe.webhooks.constructEvent` against Fluveo — there is no delivery surface. Do not call
`paymentMethods.*`, `charges.create`, `subscriptions.cancel`, `invoices.pay`, `disputes.*`, `payouts.*`.

## Webhooks

Your Stripe webhook handler has no Fluveo counterpart today. Replace it with a poller:

- Checkout: reconcile `GET /v1/checkout/sessions/{session}` (`status`, `payment_status`).
- Card payments: reconcile `GET /v1/payment_intents/{intent}` (`status`).
- Refunds: `GET /v1/refunds/{refund}` (`status`).
- Invoices/subscriptions: `GET /v1/invoices/{invoice}` / `GET /v1/subscriptions/{subscription}`.

Keep the handler code idempotent so it can be re-wired when webhooks are promoted. Never register
`/v1/webhook_endpoints` or read `/v1/events` with a merchant key.

## Migration checklist

- [ ] Replace base URL and key; remove `Stripe-Account`/Connect logic.
- [ ] Set `Stripe-Version` to `2026-05-27.dahlia` or remove it.
- [ ] For each call: confirm the operation is in the subset; strip undeclared params and list filters.
- [ ] Replace `payment_method=pm_...` flows with hosted Checkout or inline test cards.
- [ ] Replace webhooks with polling; never fulfil on redirect alone.
- [ ] Stop reading undeclared response fields (e.g. `charges.data` on a PaymentIntent, `refund.livemode`).
- [ ] Make retries reuse the same `Idempotency-Key`; handle `409`.
- [ ] Remove browser code that expects a `pk_` key.
