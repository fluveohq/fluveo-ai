# fluveo-ai

Agent skills that let AI coding agents (Claude Code, Codex, Cursor, and any `SKILL.md`-aware agent) integrate a
merchant's software with the **Fluveo payments API** — directly over HTTP, **no SDK required**. The agent reads
the skill, opens the relevant reference, and writes `curl` / `fetch` / `requests` code against
`https://api.devfluveo.com/v1`.

Fluveo's `/v1` is a Stripe-shaped, curated subset (67 operations, pinned to Stripe API `2026-05-27.dahlia`).
The exact contract ships in this repo as `spec/openapi.subset.json`; every endpoint, parameter and response field
must be checked against it. The local validator checks endpoint mentions, links, and safety rules; it does not
prove every parameter or response claim.

## Install

**Claude Code (plugin)**

```bash
claude plugin add https://github.com/fluveohq/fluveo-ai
# or from a local checkout:
claude plugin add /path/to/fluveo-ai
```

**`npx skills add` (Claude Code, Codex, Cursor, others)**

```bash
npx skills add fluveohq/fluveo-ai
# single skill:
npx skills add fluveohq/fluveo-ai --skill fluveo-integrate
```

**Codex** — copy `skills/fluveo-integrate` and `skills/fluveo-docs` into `~/.codex/skills/` (or your
project's `.codex/skills/`) together with `spec/openapi.subset.json` at the parent of `skills/`.

**Cursor** — copy the two skill folders into `.cursor/skills/` in your project (keep `spec/` beside `skills/`),
or reference `skills/fluveo-integrate/SKILL.md` from a Cursor rule.

**Manual (any agent)**

```bash
git clone https://github.com/fluveohq/fluveo-ai
# point your agent at fluveo-ai/skills/fluveo-integrate/SKILL.md
```

The `fluveo-docs` skill expects `spec/openapi.subset.json` at the plugin root (sibling of `skills/`). Keep
that layout when copying.

## Skill index

| Skill | Purpose |
|---|---|
| `skills/fluveo-integrate/SKILL.md` | Main skill: wire format, auth, routing table to references, critical rules, what does not exist. |
| `skills/fluveo-integrate/references/authentication.md` | Base URL, Basic vs Bearer, headers, `Stripe-Version`. |
| `skills/fluveo-integrate/references/payments.md` | PaymentIntents create → confirm → (capture) → retrieve; lifecycle; 3DS; cancel; list; charges; Node + Python. |
| `skills/fluveo-integrate/references/refunds.md` | Full/partial refunds, statuses, idempotency, list. |
| `skills/fluveo-integrate/references/checkout.md` | Checkout Sessions, Payment Links, polling-based fulfilment, expire, branding. |
| `skills/fluveo-integrate/references/events-and-webhooks.md` | Public event reads and webhook endpoint management; delivery-verification limits. |
| `skills/fluveo-integrate/references/payment-methods.md` | Tenant-scoped saved-card list/retrieve; no top-level writes. |
| `skills/fluveo-integrate/references/customers.md` | Customers CRUD, customer payment methods, SetupIntents. |
| `skills/fluveo-integrate/references/billing.md` | Products, prices, invoice items, invoices, hosted invoice URL, subscriptions. |
| `skills/fluveo-integrate/references/balance.md` | Balance and balance-transactions pagination cookbook. |
| `skills/fluveo-integrate/references/errors-and-retries.md` | Error envelope, types/codes, idempotency journal, 429 backoff, reference client. |
| `skills/fluveo-integrate/references/security.md` | Key handling, browser boundary, PCI, `client_secret`, rotation. |
| `skills/fluveo-integrate/references/migrate-from-stripe.md` | Divergence table; pointing stripe-node / stripe-python at Fluveo. |
| `skills/fluveo-integrate/references/not-available.md` | Every Stripe surface that is NOT contracted, with workarounds. |
| `skills/fluveo-docs/SKILL.md` | How to look up the exact contract in `spec/openapi.subset.json` (python / jq snippets). |

## Repository layout

```
README.md
LICENSE                              MIT
.claude-plugin/plugin.json           plugin manifest (name "fluveo")
skills/fluveo-integrate/SKILL.md     main skill
skills/fluveo-integrate/references/  one file per topic (see index)
skills/fluveo-docs/SKILL.md          contract lookup skill
spec/openapi.subset.json             the contracted /v1 operations — source of truth, do not edit
scripts/validate.py                  stdlib validator entry point (test gate)
scripts/public_contract.py           public-only OpenAPI metadata check
scripts/test_public_contract.py      negative fixtures used by --self-test
scripts/webhook_guidance.py          narrow webhook retry/encoding documentation checks
scripts/test_webhook_guidance.py     broken-document fixtures used by --self-test
```

## Validate

```bash
python3 scripts/validate.py              # exit 0 on success
python3 scripts/validate.py --self-test  # checks bad links, unknown endpoints, fake keys, and private spec metadata
```

Checks: skill frontmatter, relative links, every `METHOD /v1/...` example against the OpenAPI subset (with
`not-available.md` required to list only absent paths), no real-looking secrets, plugin manifest, exact public spec metadata shapes, and the explicit webhook
retry exclusion / absence of undeclared webhook form keys. These are narrow literal checks, not a general prose audit.

## Principles

- Raw HTTP first; stripe-node / stripe-python pointed at Fluveo is documented as an alternative.
- Never document an endpoint, parameter or field that is not in `spec/openapi.subset.json`.
- Public event reads and webhook endpoint management are contracted. Delivery verification is not specified
  by this snapshot; do not invent it. Polling remains an option, and a redirect alone never proves payment.
- Secret keys never reach a browser; placeholders are always `sk_test_example`.

## Public contract source and limits

`spec/openapi.subset.json` is an unchanged copy of the public
[Fluveo OpenAPI snapshot](https://github.com/fluveohq/openapi/blob/68e410de7abb12871c02f6fe38f15ab19bed63c9/openapi/spec3.json)
at commit `68e410de7abb12871c02f6fe38f15ab19bed63c9`. Refresh only from a pinned public source, never from private source catalogs or internal implementation data.

The snapshot declares 67 operations. The ten additions are event list/retrieve, payment-method list/retrieve,
and webhook endpoint create/list/retrieve/update/delete/secret rotation. Its public compatibility annotations
mark these merchant-key authenticated and test-only. Endpoint existence does not prove a live environment is ready.

Examples in this repository deliberately retain the **development** base `https://api.devfluveo.com`.
The published contract's general server is `https://api.fluveo.dev`; this is not a request to change the
examples or proof that either host is reachable. Set `FLUVEO_API_BASE` for the environment approved by the owner.

Current contract limits, not claims about private docs:
- SetupIntent list declares a 400 response and no successful list schema; create/update/retrieve/confirm/cancel
  are declared with lifecycle `served` and mode `test_only`. Do not infer production readiness.
- Refund creation declares `payment_intent`, not a `charge` input.
- Billing lists do not declare query parameters. Do not infer Stripe's complete pagination or mutation surface.
- Webhook signature headers, signing algorithm, signed bytes, replay tolerance, delivery retries, event-type
  enumeration and secret-rotation overlap are not specified here. See the webhook reference before implementation.
- The schema's broad upstream PaymentMethod types do not prove support for those payment methods; the public
  list/retrieve descriptions cover saved cards only.

## License

MIT — see `LICENSE`.
