# Not available — Stripe surfaces that do NOT exist on Fluveo

Contents: [How to read this](#how-to-read-this) · [Webhooks and events](#webhooks-and-events) · [Payment methods](#payment-methods) · [Charges](#charges) · [PaymentIntents / SetupIntents](#paymentintents--setupintents) · [Refunds](#refunds) · [Checkout](#checkout) · [Payment Links](#payment-links) · [Customers](#customers) · [Billing](#billing) · [Money movement and risk](#money-movement-and-risk) · [Keys and platform](#keys-and-platform) · [Everything else](#everything-else)

## How to read this

Every path below is **absent from `spec/openapi.subset.json`**. Calling one returns `404` (often
`code: unsupported_operation`), `400`, or `503` — never a fabricated success. Do not document them as available,
do not add them to client wrappers, and do not use SDK method presence as evidence they exist.

## Webhooks and events

| Not available | Workaround |
|---|---|
| `POST /v1/webhook_endpoints`, `GET /v1/webhook_endpoints`, `GET /v1/webhook_endpoints/{webhook_endpoint}`, `POST /v1/webhook_endpoints/{webhook_endpoint}`, `DELETE /v1/webhook_endpoints/{webhook_endpoint}` | Poll: `/v1/payment_intents/{intent}` (GET), `/v1/checkout/sessions/{session}` (GET), `/v1/refunds/{refund}` (GET), `/v1/invoices/{invoice}` (GET), `/v1/subscriptions/{subscription}` (GET). Run a background reconciler over open sessions / pending orders. |
| `GET /v1/events`, `GET /v1/events/{id}` | Same — poll objects. |
| Signature verification (`Stripe-Signature`, `whsec_` secrets) | Nothing to verify; SDK helpers only work on payloads you supply. Never embed a webhook secret expecting deliveries. |

## Payment methods

| Not available | Workaround |
|---|---|
| `POST /v1/payment_methods`, `GET /v1/payment_methods`, `GET /v1/payment_methods/{payment_method}`, `POST /v1/payment_methods/{payment_method}`, `POST /v1/payment_methods/{payment_method}/attach`, `POST /v1/payment_methods/{payment_method}/detach`, `DELETE /v1/payment_methods/{payment_method}` | Only `/v1/customers/{customer}/payment_methods` (GET) (first page, card only) is contracted. Save cards via SetupIntents (uncontracted). |
| `payment_method=pm_...` on PaymentIntent create/confirm | Inline `payment_method_data[type]=card` + card fields (test mode) or hosted Checkout with `customer=`. |
| `POST /v1/tokens`, `POST /v1/sources`, `/v1/customers/{customer}/sources` | Use hosted Checkout / Payment Links. |
| Non-card payment method types (`pix`, `boleto`, `sepa_debit`, wallets…) | Card only today. |

## Charges

| Not available | Workaround |
|---|---|
| `POST /v1/charges`, `POST /v1/charges/{charge}`, `POST /v1/charges/{charge}/capture` | PaymentIntents: `/v1/payment_intents` (POST) (+`/capture`). Charges are read-only via `latest_charge`. |
| `GET /v1/charges/search`, `GET /v1/payment_intents/search`, `GET /v1/customers/search` | List + client-side filtering; customers list has `email` and `search` params. |

## PaymentIntents / SetupIntents

| Not available | Workaround |
|---|---|
| `POST /v1/payment_intents/{intent}/increment_authorization`, `/apply_customer_balance`, `/verify_microdeposits` | Cancel and re-authorize a new intent. |
| `payment_method_types[]` other than `card`, `automatic_payment_methods`, `payment_method_options`, `shipping`, `transfer_data`, `application_fee_amount`, `statement_descriptor` (non-suffix), `expand[]` on PI | Not accepted (`400`). Use `statement_descriptor_suffix`. |
| SetupIntent list (`/v1/setup_intents` list operation is declared, but only a `400` response is documented) | List the customer's cards: `/v1/customers/{customer}/payment_methods` (GET). |
| `POST /v1/setup_intents/{setup_intent}/verify_microdeposits` | — |
| Real-PSP 3DS `next_action` types (`use_stripe_sdk`, etc.) | Only test-simulator `redirect_to_url`; treat `requires_action` from a real PSP as fail-closed. |

## Refunds

| Not available | Workaround |
|---|---|
| `POST /v1/refunds/{refund}/cancel` | Contact support. |
| `charge=ch_...` on refund create; `charge` / `payment_intent` filters on the refunds list; `expand[]` | Resolve the charge to its `payment_intent` first; filter the list client-side. |
| `GET /v1/charges/{charge}/refunds` | `/v1/refunds` (GET) + client-side filter on `charge`. |

## Checkout

| Not available | Workaround |
|---|---|
| `mode=subscription`, `mode=setup` | `mode=payment`; subscriptions via Billing + hosted invoice URL. |
| `ui_mode=embedded`, `ui_mode=custom`, `return_url`, `client_secret`-based embedded checkout | Redirect to the hosted `url`. |
| `line_items[][price]` (catalog price ids), `line_items[][adjustable_quantity]` | Inline `price_data`. |
| `automatic_tax`, `tax_rates`, `discounts`, `allow_promotion_codes`, `shipping_address_collection`, `shipping_options`, `invoice_creation`, `custom_fields`, `custom_text`, `consent_collection`, `phone_number_collection`, `locale`, `subscription_data`, `after_expiration`, `payment_method_options`, `payment_intent_data[metadata|receipt_email|shipping|setup_future_usage]` | All named `400`. Compute totals yourself and pass a single line item. |
| `cancel_url` link on the hosted page | Echoed on the object only; not rendered yet. |

## Payment Links

| Not available | Workaround |
|---|---|
| `line_items[][price]` (catalog prices), `application_fee_*`, `automatic_tax`, `allow_promotion_codes`, `shipping_*`, `subscription_data`, `custom_fields`, `phone_number_collection`, `tax_id_collection`, `transfer_data` | Flat `amount`+`currency` or inline `price_data`. |
| Reactivating a completed/expired link (`active=true`) | Create a new link (`400` otherwise). |
| Listing sessions/intents created by a link | Put a reference in `metadata`; reconcile via `/v1/checkout/sessions` (GET) / `/v1/payment_intents` (GET). |

## Customers

| Not available | Workaround |
|---|---|
| `payment_method`, `shipping`, `invoice_settings`, `tax_exempt`, `preferred_locales`, `balance`, `source` on create/update | Named `400`; only `email`, `name`, `phone`, `description`, `address`, `metadata`. |
| `GET /v1/customers/{customer}/balance_transactions`, `/cash_balance`, `/tax_ids`, `/sources`, `/discount` | — |
| `created[...]` filter on the customers list; `starting_after` / `ending_before` on the customer payment-methods list | Use `email`/`search`; first page only for payment methods. |

## Billing

| Not available | Workaround |
|---|---|
| `POST /v1/products/{product}` (update), `DELETE /v1/products/{product}` | Create a new product; keep your own "archived" flag. |
| `POST /v1/prices/{price}` (update) | Create a new price. |
| `GET /v1/invoiceitems`, `GET /v1/invoiceitems/{invoiceitem}`, `POST /v1/invoiceitems/{invoiceitem}`, `DELETE /v1/invoiceitems/{invoiceitem}` | Store the `ii_` id yourself; add a negative-amount item to offset. |
| `POST /v1/invoices/{invoice}` (update), `POST /v1/invoices/{invoice}/pay`, `POST /v1/invoices/{invoice}/void`, `POST /v1/invoices/{invoice}/send`, `POST /v1/invoices/{invoice}/mark_uncollectible`, `DELETE /v1/invoices/{invoice}`, `GET /v1/invoices/upcoming`, `GET /v1/invoices/{invoice}/lines` | Finalize → `/v1/invoices/{invoice}/hosted_invoice_url` (GET) → customer pays on the hosted page; poll `status`. Lines are inline on the invoice object. |
| `POST /v1/subscriptions/{subscription}` (update), `DELETE /v1/subscriptions/{subscription}`, `POST /v1/subscriptions/{subscription}/cancel`, `POST /v1/subscriptions/{subscription}/resume`, `/v1/subscription_items`, `/v1/subscription_schedules` | Set `cancel_at` at create time; otherwise contact support. |
| `/v1/coupons`, `/v1/promotion_codes`, `/v1/credit_notes`, `/v1/tax_rates`, `/v1/tax_ids`, `/v1/quotes`, `/v1/plans` | Not served. Represent discounts as negative invoice items. |

## Money movement and risk

| Not available | Workaround |
|---|---|
| `/v1/disputes`, `POST /v1/disputes/{dispute}`, `POST /v1/disputes/{dispute}/close` | Disputes appear as `type: "dispute"` rows in `/v1/balance_transactions` (GET); handle evidence via the dashboard/support. |
| `/v1/payouts`, `POST /v1/payouts/{payout}/cancel` | Payouts appear as `type: "payout"` balance transactions; scheduling via dashboard. |
| `/v1/transfers`, `/v1/topups`, `/v1/application_fees`, `/v1/accounts`, `/v1/account_links`, Connect / `Stripe-Account` header | Not served. |
| `/v1/radar/early_fraud_warnings`, `/v1/radar/value_lists`, `/v1/reviews` | Not served. |
| `/v1/issuing/*`, `/v1/terminal/*`, `/v1/tax/*`, `/v1/identity/*`, `/v1/climate/*`, `/v1/financial_connections/*`, `/v1/treasury/*` | Not served. |
| `created[gt|gte|lt|lte]`, `type`, `currency`, `payout` filters on the balance-transactions list | `source=` filter + client-side filtering. |

## Keys and platform

| Not available | Workaround |
|---|---|
| `sk_live_*` keys / live mode | Test mode only; do not build environment switches that assume a live key exists. |
| `pk_*` publishable keys, `rk_*` restricted keys | Server-side only; hosted pages for card entry. |
| Fluveo Elements in production (`@fluveo/elements` needs `pk_`) | Hosted Checkout / Payment Links. Never pass an `sk_` key to a browser package. |
| `/v1/files`, `/v1/file_links` (and `logo[type]=file` in branding) | `logo[type]=url` with a hosted image. |
| `/v1/test_helpers/*`, test clocks | Use the `4242424242424242` test card and real time. |
| `/v1/mandates`, `/v1/apple_pay/domains`, `/v1/ephemeral_keys`, `/v1/customer_sessions`, `/v1/payment_method_configurations`, `/v1/payment_method_domains` | Not served. |
| Any `/v2/*` path from a merchant key | Not part of the Stripe-shaped contract. |

## Everything else

If a `METHOD /v1/path` is not in `spec/openapi.subset.json`, assume it is not available. Run the `fluveo-docs`
skill's snippet to check before writing code, and prefer telling the user "Fluveo does not expose X today; here is
the closest supported flow" over guessing.
