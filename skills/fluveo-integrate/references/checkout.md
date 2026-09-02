# Hosted Checkout — Checkout Sessions, Payment Links, Branding

Contents: [When to use which](#when-to-use-which) · [Checkout Session endpoints](#checkout-session-endpoints) · [Create a session](#create-a-session) · [Fulfilment by polling](#fulfilment-by-polling) · [Retrieve, list, line items](#retrieve-list-line-items) · [Update](#update) · [Expire](#expire) · [Payment Links](#payment-links) · [Checkout branding](#checkout-branding) · [Node and Python](#node-and-python) · [Rejected parameters](#rejected-parameters)

## When to use which

| Need | Use |
|---|---|
| One-off purchase, you know the cart, customer pays on a Fluveo-hosted page | **Checkout Session** (`/v1/checkout/sessions`) — creates a real PaymentIntent behind it |
| Reusable "pay me" URL to share by email/chat, no per-customer server call | **Payment Link** (`/v1/payment_links`) |
| Server-side card charge with your own PCI-scoped form | PaymentIntents (`payments.md`) |

Both hosted surfaces are card-only, test-mode, `mode=payment` only. No subscriptions/setup mode, no embedded
UI, no tax/discount/shipping calculation.

## Checkout Session endpoints

| Method | Path | Idempotency-Key | Purpose |
|---|---|---|---|
| `POST` | `/v1/checkout/sessions` | 24h journal | Create |
| `GET` | `/v1/checkout/sessions/{session}` | — | Retrieve (authoritative) |
| `POST` | `/v1/checkout/sessions/{session}` | 24h journal | Update `metadata`, `customer_email`, `shipping_details` |
| `GET` | `/v1/checkout/sessions` | — | List |
| `GET` | `/v1/checkout/sessions/{session}/line_items` | — | Line-item snapshot |
| `POST` | `/v1/checkout/sessions/{session}/expire` | 24h journal | Expire an `open` session |

## Create a session

Contracted body fields: `line_items` (required), `success_url` (required), `cancel_url`, `client_reference_id`,
`customer` (`cus_...`), `customer_email`, `customer_update`, `expires_at` (unix, 30 min–24 h ahead; default 24 h),
`metadata`, `mode` (`payment` only), `payment_intent_data[description]`, `payment_intent_data[capture_method]`
(`automatic` | `automatic_async` | `manual`), `payment_method_types[]` (`card` only), `tax_id_collection`,
`ui_mode` (`hosted` only), `branding_settings`.

Line items: `line_items[i][price_data][currency]`, `line_items[i][price_data][unit_amount]`,
`line_items[i][price_data][product_data][name]`, `line_items[i][quantity]`. Single currency, ≤100 items,
quantity ≤ 999999, total ≤ 99,999,999 minor units. Catalog `price` ids are **not** accepted here.

```bash
curl https://api.devfluveo.com/v1/checkout/sessions \
  -u sk_test_example: \
  -H "Idempotency-Key: order-8217-checkout" \
  -d "line_items[0][price_data][currency]=usd" \
  -d "line_items[0][price_data][unit_amount]=2000" \
  --data-urlencode "line_items[0][price_data][product_data][name]=Demo Plan" \
  -d "line_items[0][quantity]=2" \
  -d "mode=payment" \
  --data-urlencode "success_url=https://merchant.example.com/thanks?order=8217" \
  --data-urlencode "cancel_url=https://merchant.example.com/cart" \
  -d "customer_email=buyer@example.com" \
  -d "client_reference_id=order-8217" \
  --data-urlencode "metadata[order_id]=8217" \
  -d "payment_intent_data[capture_method]=automatic"
```

Response `200` (abbreviated):

```json
{
  "id": "cs_6d65726368616e74a1b2c3d4e5f6",
  "object": "checkout.session",
  "status": "open",
  "payment_status": "unpaid",
  "mode": "payment",
  "ui_mode": "hosted_page",
  "url": "https://pay.devfluveo.com/c/cs_6d65726368616e74a1b2c3d4e5f6",
  "amount_subtotal": 4000,
  "amount_total": 4000,
  "currency": "usd",
  "payment_intent": "pi_1A9e8AzB2xQRH9JfQu5N",
  "customer": null,
  "customer_email": "buyer@example.com",
  "client_reference_id": "order-8217",
  "success_url": "https://merchant.example.com/thanks?order=8217",
  "cancel_url": "https://merchant.example.com/cart",
  "expires_at": 1769498745,
  "payment_method_types": ["card"],
  "metadata": { "order_id": "8217" },
  "created": 1769412345,
  "livemode": false
}
```

The hosted page lives on a different host than the API. Always redirect to the returned `url`; never construct it.

Redirect the customer to `url` (HTTP 303). The URL carries no secrets. Store `id` and `payment_intent`
against your order. Live ids are long and hyphenated (e.g. `cs_6d63685f…-7061795f…-5c9dfe42886faa71`); treat
them as opaque and validate only the `cs_` prefix.

`status`: `open` → `complete` | `expired`. `payment_status`: `unpaid` → `paid` (`no_payment_required` is in the
enum but not used for card payments). Both project the backing PaymentIntent.

## Fulfilment by polling

There are **no webhooks**. The `success_url` visit is not proof of payment (the customer can open it directly,
or close the tab before it loads). Fulfil only after a server-side read:

```bash
curl https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6 -u sk_test_example:
# fulfil when "status": "complete" AND "payment_status": "paid"
```

Recommended pattern:

1. On `success_url` load, read `client_reference_id`/`order` from your own query string, look up the session id
   you stored, `GET` the session. If `payment_status == "paid"` mark the order paid (idempotently). Otherwise
   show "processing" and poll.
2. Run a background reconciler that lists `GET /v1/checkout/sessions?status=open` (plus your own "pending"
   orders) and retrieves each until `complete`/`expired`.
3. For `payment_intent_data[capture_method]=manual`, the backing intent lands in `requires_capture`; capture
   it via `POST /v1/payment_intents/{intent}/capture` (`payments.md`). The session reports `complete` once the
   intent succeeds.

### success_url and session ids

Fluveo does **not** substitute a `{CHECKOUT_SESSION_ID}` placeholder in `success_url` — it is passed through as a
literal. The hosted page *may* append `payment_id` and `status` query params when redirecting to `success_url`;
treat them as hints only, never as proof. Put **your** order id in `success_url` and map it to the stored session
id server-side, as in step 1 of the [recommended pattern](#fulfilment-by-polling) above.

## Retrieve, list, line items

```bash
curl https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6 -u sk_test_example:
curl -G https://api.devfluveo.com/v1/checkout/sessions -u sk_test_example: -d limit=20 -d status=open
curl -G https://api.devfluveo.com/v1/checkout/sessions -u sk_test_example: -d payment_intent=pi_1A9e8AzB2xQRH9JfQu5N
curl https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6/line_items -u sk_test_example:
```

List query params: `limit`, `starting_after`, `ending_before`, `customer`, `payment_intent`, `status`,
`created`, `created[gt|gte|lt|lte]`. Line items: `limit`, `starting_after`, `ending_before` (`li_...` cursors).

Line items response (abbreviated):

```json
{ "object": "list", "url": "/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6/line_items", "has_more": false,
  "data": [ { "id": "li_1PzLmN2xQRH9JfQu5Nk3", "object": "item", "description": "Demo Plan", "quantity": 2, "currency": "usd",
              "amount_subtotal": 4000, "amount_total": 4000, "amount_discount": 0, "amount_tax": 0,
              "price": { "id": "price_1PzLkT2xQRH9JfQu5Nq7", "object": "price", "currency": "usd", "unit_amount": 2000,
                         "product": { "id": "prod_QrTmN2xQRH9JfQu", "object": "product", "name": "Demo Plan" } } } ] }
```

## Update

Only `metadata`, `customer_email`, `shipping_details[name]`, `shipping_details[address][...]` are updatable
(`shipping_details` is display/echo context returned at `collected_information.shipping_details`, not a
fraud/AVS signal).

```bash
curl https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6 \
  -u sk_test_example: -H "Idempotency-Key: cs-8217-update-1" \
  --data-urlencode "metadata[order_ref]=8217" -d customer_email=buyer@example.com
```

## Expire

Cancels the backing PaymentIntent and returns the session with `status: "expired"`. Only `open` sessions can be
expired; `complete`/`expired` → `400`.

```bash
curl -X POST https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6/expire \
  -u sk_test_example: -H "Idempotency-Key: cs-8217-expire"
```

## Payment Links

| Method | Path | Idempotency-Key | Purpose |
|---|---|---|---|
| `POST` | `/v1/payment_links` | 24h journal | Create |
| `GET` | `/v1/payment_links/{payment_link}` | — | Retrieve |
| `POST` | `/v1/payment_links/{payment_link}` | resource-local | Update |
| `POST` | `/v1/payment_links/{payment_link}/expire` | resource-local | Expire (no further payments) |
| `GET` | `/v1/payment_links` | — | List |
| `GET` | `/v1/payment_links/{payment_link}/line_items` | — | Line items |

Create accepts **exactly one money shape**: flat `amount` + `currency` (Fluveo extension) **or** 1–20
`line_items[i][price_data][...]` (+ `quantity`). Other fields: `description` (≤1000 chars), `expires_at`
(Fluveo extension, 30 min–30 days; default 24 h), `after_completion` (`[type]=redirect` +
`[redirect][url]`, or `[type]=hosted_confirmation` + `[hosted_confirmation][custom_message]`),
`payment_method_types[]` (`card`), `metadata`, `restrictions[completed_sessions][limit]`, `inactive_message`,
`submit_type` (`auto` | `pay` | `book` | `donate` | `subscribe`). Catalog `price` ids are not accepted.

```bash
curl https://api.devfluveo.com/v1/payment_links \
  -u sk_test_example: -H "Idempotency-Key: plink-invoice-9001" \
  -d amount=4242 -d currency=usd \
  --data-urlencode "description=Order #9001" \
  -d "after_completion[type]=redirect" \
  --data-urlencode "after_completion[redirect][url]=https://merchant.example.com/thanks" \
  --data-urlencode "metadata[order_id]=9001"
```

```json
{
  "id": "plink_R9k8AzB2xQRH9Jf",
  "object": "payment_link",
  "url": "https://api.devfluveo.com/p/plink_R9k8AzB2xQRH9Jf",
  "active": true,
  "amount": 4242,
  "currency": "usd",
  "description": "Order #9001",
  "expires_at": 1769498745,
  "after_completion": { "type": "redirect", "redirect": { "url": "https://merchant.example.com/thanks" } },
  "metadata": { "order_id": "9001" },
  "created": 1769412345,
  "livemode": false
}
```

Share `url`. Update fields: `active`, `expires_at`, `metadata`, `after_completion`, `restrictions`,
`inactive_message`, `submit_type` (`amount`/`currency` are fixed). `active=false` deactivates immediately and
ignores other fields in the same request; `active=true` on a completed/expired link is `400` (create a new link).

```bash
curl https://api.devfluveo.com/v1/payment_links/plink_R9k8AzB2xQRH9Jf -u sk_test_example: -d active=false
curl -X POST https://api.devfluveo.com/v1/payment_links/plink_R9k8AzB2xQRH9Jf/expire -u sk_test_example:
curl -G https://api.devfluveo.com/v1/payment_links -u sk_test_example: -d limit=20 -d status=active
curl https://api.devfluveo.com/v1/payment_links/plink_R9k8AzB2xQRH9Jf/line_items -u sk_test_example:
```

List query params: `limit`, `starting_after`, `ending_before`, `status`. `active` in responses is the
*effective* state (flag true, not expired, completion limit not exhausted).

**Detecting a Payment Link payment:** there is no contracted way to look up the sessions/intents a link created
by link id. Options: (a) put your reference in the link's `metadata` and reconcile via
`GET /v1/checkout/sessions` / `GET /v1/payment_intents` (metadata is on the intent), (b) use
`restrictions[completed_sessions][limit]=1` and watch the link's `active` flip to `false`, (c) prefer a
Checkout Session when you need a firm server-side completion signal.

## Checkout branding

Merchant-wide defaults for the hosted page. Fluveo extension, `GET` + `PUT` (form or JSON body).
Fields: `display_name`, `background_color`, `button_color` (CSS hex), `font_family`, `border_style`
(`rounded` | `pill` | `square`), `logo[type]=url` + `logo[url]`, `icon[type]=url` + `icon[url]`.
`type=file` → `400`.

```bash
curl -X PUT https://api.devfluveo.com/v1/checkout/branding -u sk_test_example: \
  --data-urlencode "display_name=Fluveo Demo" -d "background_color=#ffffff" -d "button_color=#00aa88" \
  -d "logo[type]=url" --data-urlencode "logo[url]=https://merchant.example.com/logo.png"
curl https://api.devfluveo.com/v1/checkout/branding -u sk_test_example:
```

```json
{ "object": "checkout.branding", "display_name": "Fluveo Demo", "background_color": "#ffffff",
  "button_color": "#00aa88", "font_family": "system", "border_style": "rounded",
  "logo": { "type": "url", "url": "https://merchant.example.com/logo.png" }, "icon": null }
```

## Node and Python

```js
// Express-style handler: create a session and redirect
const body = new URLSearchParams({
  "line_items[0][price_data][currency]": "usd",
  "line_items[0][price_data][unit_amount]": "2000",
  "line_items[0][price_data][product_data][name]": "Demo Plan",
  "line_items[0][quantity]": "1",
  mode: "payment",
  success_url: `https://merchant.example.com/thanks?order=${orderId}`,
  cancel_url: "https://merchant.example.com/cart",
  client_reference_id: orderId,
  "metadata[order_id]": orderId,
});
const BASE = process.env.FLUVEO_API_BASE ?? "https://api.devfluveo.com";
const res = await fetch(`${BASE}/v1/checkout/sessions`, {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`,
             "User-Agent": "myshop/1.0",
             "Content-Type": "application/x-www-form-urlencoded",
             "Idempotency-Key": `order-${orderId}-checkout` },
  body,
});
const session = await res.json();
if (!res.ok) throw new Error(session.error.message);
await db.orders.update(orderId, { checkoutSessionId: session.id, paymentIntentId: session.payment_intent });
return reply.redirect(303, session.url);

// Later (success page + reconciler): server-side check
const s = await (await fetch(`${BASE}/v1/checkout/sessions/${session.id}`,
  { headers: { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`, "User-Agent": "myshop/1.0" } })).json();
const paid = s.status === "complete" && s.payment_status === "paid";
```

```python
import os, requests
AUTH = (os.environ["FLUVEO_API_KEY"], "")
BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
UA = {"User-Agent": "myshop/1.0"}
r = requests.post(f"{BASE}/v1/checkout/sessions", auth=AUTH,
    headers={**UA, "Idempotency-Key": f"order-{order_id}-checkout"},
    data={
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": 2000,
        "line_items[0][price_data][product_data][name]": "Demo Plan",
        "line_items[0][quantity]": 1,
        "mode": "payment",
        "success_url": f"https://merchant.example.com/thanks?order={order_id}",
        "client_reference_id": order_id,
        "metadata[order_id]": order_id,
    })
session = r.json()
if not r.ok:
    raise RuntimeError(session["error"])
redirect_url = session["url"]

# reconcile
s = requests.get(f"{BASE}/v1/checkout/sessions/{session['id']}", auth=AUTH, headers=UA).json()
paid = s["status"] == "complete" and s["payment_status"] == "paid"
```

## Rejected parameters

These Stripe Checkout params return `400 invalid_request_error` naming the param (never silently ignored):
`automatic_tax`, `shipping_address_collection`, `shipping_options`, `discounts`, `allow_promotion_codes`,
`subscription_data`, `invoice_creation`, `custom_fields`, `return_url`, `locale`, `mode=subscription`,
`mode=setup`, `ui_mode=embedded`, `line_items[i][price]`, `payment_intent_data[metadata|receipt_email|shipping]`,
`metadata[fluveo_*]`, `metadata[payment_link]`. `cancel_url` is echoed on the object but the hosted page does not
yet render a cancel link.
