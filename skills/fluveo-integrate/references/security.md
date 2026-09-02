# Security

Contents: [Secret keys](#secret-keys) · [Browser boundary](#browser-boundary) · [Card data and PCI](#card-data-and-pci) · [client_secret](#client_secret) · [Logging and metadata](#logging-and-metadata) · [Rotation and incident response](#rotation-and-incident-response) · [Transport and headers](#transport-and-headers) · [Fulfilment integrity](#fulfilment-integrity)

## Secret keys

- `sk_test_*` is a **server-side** credential with full merchant authority. Only `sk_test_*` exists today.
- Read it from an environment variable / secret manager (`FLUVEO_API_KEY`). Never hard-code, never commit,
  never paste into tickets or chat. Use `sk_test_example` as the placeholder in docs and tests.
- One key per deployment/environment so a leak can be revoked without downtime elsewhere.
- Do not invent `sk_live_*`, `pk_*` or `rk_*` values; they are rejected and their appearance in code is a smell.

## Browser boundary

- **Never ship a secret key to a browser, mobile app, or any client-side bundle.** Every `/v1` call goes from
  your server.
- Fluveo's hosted Checkout Session `url` and Payment Link `url` are safe to give to browsers: they carry no key
  material or `client_secret`.
- Fluveo Elements (`@fluveo/elements`) is a browser package that takes a *publishable* key and a PaymentIntent
  `client_secret`. Publishable keys are not issued today, so do not build on it yet — and never work around
  that by passing an `sk_test_*` key to `loadFluveo()`.

## Card data and PCI

- Inline `payment_method_data[card][...]` is accepted in **test mode only**; it exists so servers can drive the
  flow with test cards like `4242424242424242`. Do not design a production path where real PANs transit your
  servers unless you are PCI-scoped for it.
- Prefer hosted Checkout / Payment Links: card entry happens on Fluveo's page.
- Never write PAN, CVC or expiry into `metadata`, `description`, `footer`, logs, error reports, request
  recordings, or CI artifacts. Billing free-text fields are actively scanned and rejected if they contain
  card-like digit runs.
- Card data is not part of the idempotency fingerprint; do not rely on it to detect a different card on retry.

## client_secret

`client_secret` on PaymentIntents / SetupIntents is flow state that lets a holder act on the intent. Treat it like
a secret: never log it, never put it in URLs or query strings, never store it beyond the flow. List endpoints
return it as `null` on purpose. Idempotent replay bodies can contain it — do not persist replay bodies.

## Logging and metadata

- Log: request id/path, HTTP status, `error.type`, `error.code`, `error.param`, your own order id, object ids
  (`pi_`, `re_`, `cs_`).
- Do not log: `Authorization` header, request bodies of confirm/setup calls, `client_secret`, raw `message`
  to end users.
- Metadata is merchant-visible and returned on every read: put only non-sensitive references (order ids,
  user ids). Keys starting with `fluveo_` are reserved and rejected.

## Rotation and incident response

1. Create a new key in the dashboard.
2. Deploy the new key (env var / secret manager) to all services.
3. Revoke the old key. Revocation takes effect for new requests within ≤5 s; in-flight requests complete.
4. On suspected exposure: revoke first, then rotate — treat any key that touched a browser, a public repo, a
   log aggregator, or a chat tool as compromised.

## Transport and headers

- Always `https://api.fluveo.dev`; `http://localhost:8080` only for local dev.
- Send exactly one credential. Do not add `api-key`, `Stripe-Account`, connected-account or processor headers.
- `Idempotency-Key` values are not secret but should be unguessable enough that another system in your org
  cannot collide with them (prefix with the service/operation name).

## Fulfilment integrity

- Never fulfil on a redirect (`success_url`, `return_url`, `after_completion`) alone. Retrieve the PaymentIntent
  / Checkout Session server-side and check `status` / `payment_status`.
- Make order state transitions idempotent: a poller and a success-page handler may both observe `paid`.
- Amounts are integers in minor units — never floats. Compare `amount_received` against what you expected.
- Validate `livemode` is what you expect for the environment (always `false` today).
