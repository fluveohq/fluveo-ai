"""Reject private Fluveo metadata anywhere in the bundled public contract."""
import json
import os
import re

PUBLIC_COMPATIBILITY_VALUES = {
    "audience": {"merchant_public"},
    "auth_policy": {"stripe_secret_key"},
    "idempotency_policy": {"not_applicable", "required_on_retryable_write"},
    "lifecycle": {"served"},
    "mode_policy": {"test_only"},
}
PUBLIC_RESERVED_POLICIES = {
    "case_insensitive_fluveo_prefix", "case_insensitive_fluveo_prefix_and_payment_link",
}


def compatibility_is_public(value):
    expected = set(PUBLIC_COMPATIBILITY_VALUES) | {"stripe_reference"}
    if not isinstance(value, dict) or set(value) != expected:
        return False
    for field, allowed in PUBLIC_COMPATIBILITY_VALUES.items():
        if not isinstance(value[field], str) or value[field] not in allowed:
            return False
    reference = value["stripe_reference"]
    return reference is None or (
        isinstance(reference, str)
        and re.fullmatch(r"https://docs\.stripe\.com/api/[A-Za-z0-9_/-]+", reference) is not None
    )


def extension_is_public(name, value):
    if name == "x-fluveo-compatibility":
        return compatibility_is_public(value)
    if name == "x-fluveo-key-max-length":
        return type(value) is int and value == 40
    if name == "x-fluveo-reserved-key-policy":
        return isinstance(value, str) and value in PUBLIC_RESERVED_POLICIES
    if name == "x-fluveo-stripe-api-version-pin":
        return isinstance(value, str) and value == "2026-05-27.dahlia"
    return False


def metadata_errors(value, location="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = location + "." + key
            if key.startswith("x-fluveo-") and not extension_is_public(key, child):
                yield child_location
            yield from metadata_errors(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from metadata_errors(child, f"{location}[{index}]")


def check_public_contract(root, report):
    path = os.path.join(root, "spec", "openapi.subset.json")
    if not os.path.isfile(path):
        report.fail(7, path, "public contract missing")
        return
    with open(path, encoding="utf-8") as stream:
        spec = json.load(stream)
    errors = list(metadata_errors(spec))
    for location in errors:
        report.fail(7, path, "non-public contract metadata at " + location)
    if not errors:
        report.ok(7, "bundled contract contains only approved public Fluveo metadata")
