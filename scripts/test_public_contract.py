"""Public metadata fixtures exercised through validate.py's real run entry."""
import json
import os


def compatibility(**updates):
    return {
        "audience": "merchant_public", "auth_policy": "stripe_secret_key",
        "idempotency_policy": "not_applicable", "lifecycle": "served",
        "mode_policy": "test_only", "stripe_reference": None, **updates,
    }


def invalid_metadata():
    yield "catalog", {"x-fluveo-mounted-catalog": {}}
    yield "source", {"x-fluveo-source-resolution": {}}
    yield "nested-source", {"nested": [{"x-fluveo-source-resolution": {}}]}
    yield "unknown-extension", {"x-fluveo-private-future-data": {}}
    yield "compatibility-list", {"x-fluveo-compatibility": [compatibility()]}
    yield "extra-field", {"x-fluveo-compatibility": compatibility(source_file="not-public")}
    missing = compatibility()
    del missing["audience"]
    yield "missing-field", {"x-fluveo-compatibility": missing}
    for field in ("audience", "auth_policy", "idempotency_policy", "lifecycle", "mode_policy"):
        for value in ({"source_file": "not-public"}, ["merchant_public"], "not-public"):
            yield field + repr(value), {"x-fluveo-compatibility": compatibility(**{field: value})}
    for value in ({"source_file": "not-public"}, [], "https://private.example/api/events"):
        yield "stripe-reference" + repr(value), {"x-fluveo-compatibility": compatibility(stripe_reference=value)}
    for key, invalid in (
        ("x-fluveo-key-max-length", ({}, [], 40.0, "40", True, 41)),
        ("x-fluveo-reserved-key-policy", ({}, [], "not-public")),
        ("x-fluveo-stripe-api-version-pin", ({}, [], "wrong-version")),
    ):
        for value in invalid:
            yield key + repr(value), {key: value}


def self_test(run, root):
    path = os.path.join(root, "skills", "fluveo-integrate", "spec", "openapi.subset.json")
    with open(path, encoding="utf-8") as stream:
        original = json.load(stream)
    count = 0
    try:
        for label, fixture in invalid_metadata():
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({**original, **fixture}, stream)
            assert any(check == 7 for check, _, _ in run(root).failures), (
                "self-test: private contract metadata not caught: " + label
            )
            count += 1
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({**original, "x-fluveo-compatibility": compatibility()}, stream)
        assert not any(check == 7 for check, _, _ in run(root).failures)
        os.remove(path)
        assert any(check == 7 for check, _, _ in run(root).failures)
    finally:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(original, stream)
    print(f"public-contract self-test passed ({count} rejected fixtures; clean accepted; missing rejected)")
