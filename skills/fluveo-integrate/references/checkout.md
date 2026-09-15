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

A `200` from Checkout Session or payment link creation is not proof the account can take payments.
Session creation can succeed before approval, returning `open` / `unpaid` and a `url` that renders a card form.
Check `GET /v1/balance` at startup or in a health check using [authentication](authentication.md#getting-a-key);
do not send buyers to a hosted page while the account is not enabled.

**Persist first.** Create and commit your order row with your own order id and the `Idempotency-Key` you will
use **before** the POST. Store the returned `id`, `payment_intent` and `url` against it right after the response.
If a timeout, unknown outcome or crash loses the response, retry the unchanged request with the **same** key
within the 24 h journal window to recover the original result, store it, then read the session. Follow the bounded
[retry policy](errors-and-retries.md#retry-policy); if unresolved, stop and alert the owner, never create with a fresh key.

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

Give the buyer their merchant order URL or a confirmation email before or independently of sending them to
`url` (HTTP 303); do not build a flow that waits for them to come back. The URL carries no secrets. Today, after
payment the hosted page shows "Paid successfully", "We have successfully received your payment" and "Ref Id: pay_..."
and stays there, with no link or button back to the merchant. Store `id`, `payment_intent` and `url`
against your order. Live ids are long and hyphenated (e.g. `cs_6d63685f…-7061795f…-5c9dfe42886faa71`); treat
them as opaque and validate only the `cs_` prefix.

`status`: `open` → `complete` | `expired`. `payment_status`: `unpaid` → `paid` (`no_payment_required` is in the
enum but not used for card payments). Both project the backing PaymentIntent.

## Fulfilment by polling

Public [events and webhook endpoints](events-and-webhooks.md) are available, but delivery verification
is not specified by this snapshot. Drive the paid transition with server-side reads from polling or a scheduled
reconciler, never from a success-page visit. A redirect alone is never proof of payment. Fulfil only after a
server-side read shows `status == "complete"` **and** `payment_status == "paid"`; compare `amount_total` and
`currency` against your order (and require `livemode == false` in test). The paid state can lag the hosted confirmation by seconds:
an `open` / `unpaid` read shortly after payment means poll again, not failure.

```bash
curl https://api.devfluveo.com/v1/checkout/sessions/cs_6d65726368616e74a1b2c3d4e5f6 -u sk_test_example:
# fulfil when "status": "complete" AND "payment_status": "paid"
```

Recommended pattern:

1. From your scheduled poller or reconciler, look up the session id stored against each pending order and `GET`
   the session. If `status == "complete"` **and** `payment_status == "paid"`, and the amount/currency match,
   mark the order paid (idempotently). Otherwise keep `open` / `unpaid` orders processing and poll again.
   The merchant order page can show this stored result; its visit must not drive the paid transition.
2. Run a background reconciler that lists `GET /v1/checkout/sessions?status=open` (plus your own "pending"
   orders) and retrieves each until `complete`/`expired`.
3. For `payment_intent_data[capture_method]=manual`, the backing intent lands in `requires_capture`; capture
   it via `POST /v1/payment_intents/{intent}/capture` (`payments.md`). The session reports `complete` once the
   intent succeeds.

### success_url and session ids

Fluveo does **not** substitute a `{CHECKOUT_SESSION_ID}` placeholder in `success_url` — it is passed through as a
literal. Today `success_url` is informational only: the buyer stays on the Fluveo confirmation page, rather than
returning to the merchant. Neither a localhost nor an HTTPS `success_url` caused a redirect within 90 seconds
in the observed tests. Put **your** order id in `success_url` and map it to the stored session id server-side;
give the buyer their order link before checkout or send a confirmation email independently of any redirect.
`http://localhost` success/cancel URLs are accepted in test mode for local development.

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
// Express-style handler; balance check passed, buyer already has their order link.
const idempotencyKey = `order-${orderId}-checkout`;
// Commit before POST; on recovery reuse this order, key and unchanged request (24 h).
await db.orders.create({ id: orderId, idempotencyKey });
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
             "Idempotency-Key": idempotencyKey },
  body,
});
const session = await res.json();
if (!res.ok) throw new Error(session.error.message);
await db.orders.update(orderId, { checkoutSessionId: session.id, paymentIntentId: session.payment_intent, url: session.url });
return reply.redirect(303, session.url);

// Later (scheduled poller/reconciler, not a success-page visit): server-side check
const s = await (await fetch(`${BASE}/v1/checkout/sessions/${session.id}`,
  { headers: { Authorization: `Bearer ${process.env.FLUVEO_API_KEY}`, "User-Agent": "myshop/1.0" } })).json();
const paid = s.status === "complete" && s.payment_status === "paid";
// Before fulfilment, also compare s.amount_total and s.currency to the order and s.livemode to false.
```

```python
import os, requests
AUTH = (os.environ["FLUVEO_API_KEY"], "")
BASE = os.environ.get("FLUVEO_API_BASE", "https://api.devfluveo.com")
UA = {"User-Agent": "myshop/1.0"}
# Balance check passed; buyer already has their order link.
idempotency_key = f"order-{order_id}-checkout"
# Commit before POST; on recovery reuse this order, key and unchanged request (24 h).
db.orders.create({"id": order_id, "idempotencyKey": idempotency_key})
r = requests.post(f"{BASE}/v1/checkout/sessions", auth=AUTH,
    headers={**UA, "Idempotency-Key": idempotency_key},
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
db.orders.update(order_id, {"checkoutSessionId": session["id"],
    "paymentIntentId": session["payment_intent"], "url": session["url"]})
redirect_url = session["url"]

# Scheduled poller/reconciler, not a success-page visit
s = requests.get(f"{BASE}/v1/checkout/sessions/{session['id']}", auth=AUTH, headers=UA).json()
paid = s["status"] == "complete" and s["payment_status"] == "paid"
# Before fulfilment, also compare s["amount_total"] and s["currency"] to the order and s["livemode"] to False.
```

## Rejected parameters

These Stripe Checkout params return `400 invalid_request_error` naming the param (never silently ignored):
`automatic_tax`, `shipping_address_collection`, `shipping_options`, `discounts`, `allow_promotion_codes`,
`subscription_data`, `invoice_creation`, `custom_fields`, `return_url`, `locale`, `mode=subscription`,
`mode=setup`, `ui_mode=embedded`, `line_items[i][price]`, `payment_intent_data[metadata|receipt_email|shipping]`,
`metadata[fluveo_*]`, `metadata[payment_link]`. `cancel_url` is echoed on the object but the hosted page does not
yet render a cancel link.
