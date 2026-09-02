---
name: fluveo-docs
description: Look up the exact Fluveo /v1 API contract (which endpoints exist, their request parameters, and response fields) from the bundled OpenAPI subset. Use when you need to verify whether a Fluveo endpoint or parameter is supported, when the fluveo-integrate skill says "check the contract", when the user asks "does Fluveo support X", or before writing any Fluveo API call you are not certain about.
---

# Fluveo contract lookup

The single source of truth is `spec/openapi.subset.json` at the **plugin root** (sibling of `skills/`).
Only operations in its `paths` exist. Do not trust Stripe docs, SDK method names, or memory for Fluveo.

## List every contracted operation

```bash
python3 - <<'EOF'
import json; d = json.load(open("spec/openapi.subset.json"))
for p, ops in d["paths"].items():
    for m in ops: print(m.upper(), p)
EOF
```

## Show params and response fields for one path

```bash
python3 - <<'EOF'
import json, sys
d = json.load(open("spec/openapi.subset.json")); path = "/v1/payment_intents"    # <- edit
def deref(s):
    while "$ref" in s:
        o = d
        for k in s["$ref"].split("/")[1:]: o = o[k]
        s = o
    return s
for m, op in d["paths"][path].items():
    print("==", m.upper(), path, op.get("operationId"))
    print("  query:", [deref(p)["name"] for p in op.get("parameters", []) if deref(p)["in"] == "query"])
    for ct, v in op.get("requestBody", {}).get("content", {}).items():
        s = deref(v["schema"]); print("  body:", ct, sorted(s.get("properties", {})), "required:", s.get("required"))
    r = op["responses"].get("200", {}).get("content", {}).get("application/json", {}).get("schema")
    if r:
        s = deref(r); props = s.get("properties", {})
        if "data" in props: s = deref(props["data"]["items"]); print("  list of:", sorted(s.get("properties", {})))
        else: print("  response:", sorted(props))
EOF
```

Equivalent with `jq`:

```bash
jq -r '.paths | to_entries[] | .key as $p | .value | keys[] | "\(. | ascii_upcase) \($p)"' spec/openapi.subset.json
jq '.paths["/v1/refunds"].post.requestBody.content["application/x-www-form-urlencoded"].schema' spec/openapi.subset.json
```

## Rules

- Bracket-encode nested body fields (`payment_method_data[card][number]`, `line_items[0][quantity]`).
- A path that is absent from `paths` is **not available** — see the `fluveo-integrate` skill's
  not-available reference (`skills/fluveo-integrate/references/not-available.md`).
- Response schemas often declare only a subset of Stripe's fields; read only declared ones.
- Version pin: `info.version` = `2026-05-27.dahlia` (send it as `Stripe-Version`, or omit the header).
