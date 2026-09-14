# Events and webhook endpoints

Source: [public OpenAPI at `68e410d`](https://github.com/fluveohq/openapi/blob/68e410de7abb12871c02f6fe38f15ab19bed63c9/openapi/spec3.json),
bundled as `spec/openapi.subset.json` in this skill folder (the directory containing `SKILL.md`). These eight operations are merchant-public and test-only.
Use the owning merchant's server-side `sk_test_*` key with Basic (empty password) or Bearer authentication.
Do not add merchant IDs, `Stripe-Account`, admin credentials, or processor headers to cross tenants.
Human account setup and approved payments onboarding remain prerequisites; see [Authentication](authentication.md).

## Event reads

| Operation | Declared query parameters |
|---|---|
| `GET /v1/events` | `limit`, `starting_after`, `ending_before`, `type`, `object` |
| `GET /v1/events/{event_id}` | none |

Development examples (do not silently replace this host with the published general server):

```bash
curl -G https://api.devfluveo.com/v1/events -u "$FLUVEO_API_KEY:" \
  -H 'User-Agent: myshop/1.0' -d limit=10
curl https://api.devfluveo.com/v1/events/evt_example -u "$FLUVEO_API_KEY:" \
  -H 'User-Agent: myshop/1.0'
```

The response is an Event list or one Event. Declared fields include `id`, `type`, `created`, `livemode`,
`data`, `pending_webhooks`, and optional `api_version` / `request`. The schema leaves `data` open-ended:
do not assume a specific nested payload or supported event-type list. Treat event contents as sensitive.

## Endpoint management

| Operation | Declared input |
|---|---|
| `POST /v1/webhook_endpoints` | required `url`; optional `enabled_events`, `description`, `metadata` |
| `GET /v1/webhook_endpoints` | query `limit` only; no declared cursors |
| `GET /v1/webhook_endpoints/{endpoint_id}` | endpoint ID |
| `POST /v1/webhook_endpoints/{endpoint_id}` | `url`, `enabled_events`, `description`, `metadata`, `disabled` |
| `DELETE /v1/webhook_endpoints/{endpoint_id}` | endpoint ID |
| `POST /v1/webhook_endpoints/{endpoint_id}/rotate_secret` | endpoint ID; no request body declared |

The body schemas declare an `enabled_events` array and `metadata` string map, but this snapshot does not
declare their form serialization. Do not invent bracket keys; obtain public wire-format documentation before
sending those optional fields. The snapshot also does not enumerate accepted event names or define wildcard
behavior: obtain a public specification before choosing subscriptions.
Endpoint objects include `id`, `url`, `status` (`enabled` or `disabled`), `enabled_events`, `created`, and
`livemode`. Create and rotate return a new signing secret **once**. Store that secret directly in a server-side
secret manager; never print response bodies, log it, commit it, or send it to a browser. Update explicitly omits
`secret`. Do not depend on later reads to recover a secret. Use only an HTTPS receiver controlled by the merchant.

These writes declare `idempotency_policy: not_applicable`; do not assume the payment-write replay guarantee
or blindly repeat create/rotation after a lost response. Reconcile what can be read and ask the owner before
repeating a secret rotation whose result is unknown.

## Delivery verification is not specified here

The public snapshot does **not** specify a signature header, algorithm, signed bytes, timestamp tolerance,
delivery retries, ordering, replay rules, or rotation overlap. Do not invent a verifier or assume Stripe's SDK
verification helper applies. Endpoint management support alone does not prove an active delivery works.
Do not trust an unverified incoming payload to fulfil an order. Obtain precise public delivery documentation
before enabling such a handler; polling the owning merchant's object remains an option.

Never fulfil solely on an event claim or a browser redirect. Read the relevant payment/session server-side
with the same merchant key and compare its status, amount, currency and your order reference. Make order
updates safe to repeat so repeated observations cannot fulfil twice.
