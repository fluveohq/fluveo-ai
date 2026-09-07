# Saved payment methods (read-only)

Source: [public OpenAPI at `68e410d`](https://github.com/fluveohq/openapi/blob/68e410de7abb12871c02f6fe38f15ab19bed63c9/openapi/spec3.json).
Use raw HTTP from your server with the owning merchant's `sk_test_*` key (Basic with empty password or Bearer).
The public descriptions scope these reads to that merchant and mode and describe saved, masked cards.
Never use admin keys, processor credentials, or browser secrets to read another merchant's cards.

| Operation | Declared inputs |
|---|---|
| `GET /v1/payment_methods` | `limit`, `starting_after`, `ending_before`, `customer`, `type` |
| `GET /v1/payment_methods/{payment_method_id}` | payment-method ID |

```bash
# Development host, not the published general server. Use a customer owned by this merchant.
curl -G https://api.devfluveo.com/v1/payment_methods -u "$FLUVEO_API_KEY:" \
  -H 'User-Agent: myshop/1.0' -d customer=cus_example -d type=card -d limit=10
curl https://api.devfluveo.com/v1/payment_methods/pm_example -u "$FLUVEO_API_KEY:" \
  -H 'User-Agent: myshop/1.0'
```

List responses use `object`, `data`, `has_more`, and `url`; retrieve returns one PaymentMethod.
Use returned IDs as opaque strings. Read only declared response fields, and handle optional card details as
optional. Do not log card data or customer details. The shared response schema contains many upstream method
types; that does not establish Fluveo support beyond the saved-card behavior described for these operations.

Top-level create, update, attach, detach and delete are not contracted. Availability of list/retrieve does not
make `payment_method=pm_...` a supported PaymentIntent input. See [Customers and SetupIntents](customers.md)
for the separate nested customer list and test-mode save-card flow, and [Payments](payments.md) for supported
payment creation. Human account setup and approved payments onboarding remain required; see
[Authentication](authentication.md).
