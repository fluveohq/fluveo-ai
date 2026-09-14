"""Pin the webhook exceptions in the shared guides to the public contract."""
import json
from pathlib import Path

RETRY_REFERENCES = ("errors-and-retries.md", "authentication.md", "migrate-from-stripe.md")
EXCLUSION = "Webhook endpoint create/update/delete/secret rotation have no declared replay behavior (`not_applicable`)."
NO_RETRY_CLIENT = "Do not use the generic retry client for these writes."


def webhook_writes(spec):
    return [operation for path, methods in spec.get("paths", {}).items()
            if path.startswith("/v1/webhook_endpoints")
            for method, operation in methods.items() if method in ("post", "delete")]


def check_retry_exclusions(operations, references, report):
    for operation in operations:
        policy = operation.get("x-fluveo-compatibility", {}).get("idempotency_policy")
        if policy != "not_applicable":
            report.fail(8, "webhook contract", "review guidance: webhook replay policy changed")
    for name in RETRY_REFERENCES:
        path = references / name
        text = " ".join(path.read_text(encoding="utf-8").split()) if path.is_file() else ""
        if EXCLUSION not in text or NO_RETRY_CLIENT not in text:
            report.fail(8, str(path), "missing explicit webhook retry exclusion")


def check_form_examples(operations, references, report):
    path = references / "events-and-webhooks.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    for field in ("enabled_events", "metadata"):
        undeclared = any(
            field not in media.get("encoding", {})
            for operation in operations
            for media in operation.get("requestBody", {}).get("content", {}).values()
        )
        if undeclared and field + "[" in text:
            report.fail(8, str(path), "undeclared webhook form encoding: " + field + "[")


def check_webhook_guidance(root, report):
    path = Path(root) / "skills/fluveo-integrate/spec/openapi.subset.json"
    if not path.is_file():
        return
    operations = webhook_writes(json.loads(path.read_text(encoding="utf-8")))
    if not operations:
        return
    references = Path(root) / "skills/fluveo-integrate/references"
    before = len(report.failures)
    check_retry_exclusions(operations, references, report)
    check_form_examples(operations, references, report)
    if len(report.failures) == before:
        report.ok(8, "webhook retry exclusions and form examples match the public snapshot")
