# fluveo-ai

Agent skills that let AI coding agents (Claude Code, Codex, Cursor, and any `SKILL.md`-aware agent) integrate a
merchant's software with the **Fluveo payments API** — directly over HTTP, **no SDK required**. The agent reads
the skill, opens the relevant reference, and writes `curl` / `fetch` / `requests` code against
`https://api.fluveo.dev/v1`.

Fluveo's `/v1` is a Stripe-shaped, curated subset (57 operations, pinned to Stripe API `2026-05-27.dahlia`).
The exact contract ships in this repo as `spec/openapi.subset.json`; every endpoint, parameter and response field
in the skills is validated against it.

## Install
**Claude Code (plugin)**

```bash
claude plugin add https://github.com/leanrails-inc/fluveo-ai
# or from a local checkout:
claude plugin add /path/to/fluveo-ai
```

**`npx skills add` (Claude Code, Codex, Cursor, others)**

```bash
npx skills add leanrails-inc/fluveo-ai
# single skill:
npx skills add leanrails-inc/fluveo-ai --skill fluveo-integrate
```

**Codex** — copy `skills/fluveo-integrate` and `skills/fluveo-docs` into `~/.codex/skills/` (or your
project's `.codex/skills/`) together with `spec/openapi.subset.json` at the parent of `skills/`.

**Cursor** — copy the two skill folders into `.cursor/skills/` in your project (keep `spec/` beside `skills/`),
or reference `skills/fluveo-integrate/SKILL.md` from a Cursor rule.

**Manual (any agent)**

```bash
git clone https://github.com/leanrails-inc/fluveo-ai
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
scripts/validate.py                  stdlib validator (test gate)
```

## Validate

```bash
python3 scripts/validate.py              # exit 0 on success
python3 scripts/validate.py --self-test  # proves the validator catches bad links, unknown endpoints, fake keys
```

Checks: skill frontmatter, relative links, every `METHOD /v1/...` example against the OpenAPI subset (with
`not-available.md` required to list only absent paths), no real-looking secrets, plugin manifest.

## Principles

- Raw HTTP first; stripe-node / stripe-python pointed at Fluveo is documented as an alternative.
- Never document an endpoint, parameter or field that is not in `spec/openapi.subset.json`.
- Webhooks are not merchant-public; the skills teach polling and never fulfilling on a redirect alone.
- Secret keys never reach a browser; placeholders are always `sk_test_example`.

## Known doc gaps

Where the Fluveo prose docs and `spec/openapi.subset.json` disagree, the OpenAPI wins for endpoint existence and
the docs win for behaviour. Disagreements found while writing the skills:

- **Operation count.** The task brief says 61 contracted operations; the shipped `spec/openapi.subset.json`
  contains 57. The skills describe the 57.
- **`GET /v1/setup_intents`** is declared in the spec (query `limit`, `starting_after`, `ending_before`,
  `customer`) but its only documented response is a `400` error envelope, and `docs/api/v1/setup_intents.md`
  says list/cancel are not mounted while the spec declares `POST /v1/setup_intents/{setup_intent}/cancel`.
  The skill documents cancel as available (spec wins) and list as "declared but returns 400".
- **SetupIntents status.** Docs label SetupIntents `served_uncontracted`; the spec includes them with
  `lifecycle: served`. The skill includes them with a prominent "no parity/stability guarantee" warning.
- **Refund by `charge`.** The refund cookbook says "against the PaymentIntent (or a `charge`)"; `RefundCreate`
  in the spec only declares `payment_intent`. The skill documents `payment_intent` only and a resolve-the-charge
  workaround.
- **Payment Link idempotency mismatch code.** `payment_links.md` says key reuse with different params is
  `409 idempotency_error`; `stripe-divergences.md` and every other resource say `400 idempotency_error`. The
  skill states `400` (the cross-cutting rule) and `409 api_error` for concurrent execution.
- **Idempotency journal scope.** `errors.md` lists fifteen journaled mutations including two Payout operations;
  payouts are not in the spec, so the skill lists the fourteen that are contracted.
- **Billing list parameters.** `products.md` / `prices.md` / `invoices.md` / `subscriptions.md` describe
  `limit` / `starting_after` / `ending_before`, and mention `POST /v1/products/{product}`,
  `POST /v1/prices/{price}`, invoice-item list/retrieve/delete, and a subscription `renew` extension, but the spec
  declares no query parameters on Billing lists and none of those extra operations. The skill lists only
  contracted operations and notes the pagination params as documented-but-undeclared.
- **Billing `Stripe-Version`.** Billing docs mention `2024-09-30.acacia`; the platform policy is exactly
  `2026-05-27.dahlia` or omit. The skill follows the platform policy.
- **Checkout Session `url` / Payment Link `url` host.** Docs show `http://localhost:8080/c/...` and
  `https://pay.fluveo.com/p/...` respectively; the spec describes `{base}/c/{cs_id}` and `{base}/p/{plink_id}`.
  Examples use `https://api.fluveo.dev` as the base; treat the returned `url` as opaque.
- **`created` filters.** `stripe-divergences.md` says `created[...]` is unsupported on lists, but the spec declares
  `created`, `created[gt|gte|lt|lte]` on `GET /v1/checkout/sessions` only. The skill allows them only there.
- **`expand[]`.** Declared only on `GET /v1/balance_transactions`; docs mention `expand[]=payment_intent` on
  Checkout Session retrieve. The skill does not advertise `expand[]` on sessions.
- **Fluveo Elements.** `sdks/elements/README.md` uses `pk_test_...`; the API docs say publishable keys are not
  issued. The skill describes Elements only and tells agents not to build on it yet.
- **`Retry-After` on 409.** The idempotent-retries cookbook says a `409 idempotency_error` carries
  `Retry-After`; `stripe-divergences.md` says the concurrent case is `409 api_error`. The skill handles both
  by honouring `Retry-After` when present and retrying the same key.

## License

MIT — see `LICENSE`.
