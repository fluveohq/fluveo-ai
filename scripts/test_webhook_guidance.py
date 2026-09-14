"""Small broken-document fixtures for the public webhook guidance checks."""
import json
from pathlib import Path
import tempfile

WARNING = (
    "Webhook endpoint create/update/delete/secret rotation have no declared replay behavior (`not_applicable`).\n"
    "Do not use the generic retry client for these writes.\n"
)
REFERENCES = ("errors-and-retries.md", "authentication.md", "migrate-from-stripe.md")


def test_webhook_not_applicable_retry_guidance(run, root):
    path = root / "skills/fluveo-integrate/spec/openapi.subset.json"
    original = path.read_text()
    spec = json.loads(original)
    writes = [op for methods in spec["paths"].values()
              for method, op in methods.items() if method in ("post", "delete")]
    assert len(writes) == 4
    assert all(op["x-fluveo-compatibility"]["idempotency_policy"] == "not_applicable" for op in writes)
    references = root / "skills/fluveo-integrate/references"
    for name in REFERENCES:
        document = references / name
        document.write_text("Idempotency-Key is accepted on POST writes. Always retry with the same key.\n")
        try:
            assert any(c == 8 and str(document) == where for c, where, _ in run(root).failures), name
        finally:
            document.write_text(WARNING)
    writes[0]["x-fluveo-compatibility"]["idempotency_policy"] = "required_on_retryable_write"
    path.write_text(json.dumps(spec))
    try:
        assert any(c == 8 and "policy changed" in msg for c, _, msg in run(root).failures)
    finally:
        path.write_text(original)


def test_webhook_form_examples_require_declared_encoding(run, root):
    path = root / "skills/fluveo-integrate/references/events-and-webhooks.md"
    original = path.read_text()
    path.write_text("Send enabled_events[0] and metadata[order_source].\n")
    try:
        messages = [msg for check, _, msg in run(root).failures if check == 8]
        assert "undeclared webhook form encoding: enabled_events[" in messages
        assert "undeclared webhook form encoding: metadata[" in messages
    finally:
        path.write_text(original)


def self_test(run):
    source = Path(__file__).resolve().parents[1] / "skills/fluveo-integrate/spec/openapi.subset.json"
    spec = json.loads(source.read_text(encoding="utf-8"))
    spec["paths"] = {path: methods for path, methods in spec["paths"].items()
                     if path.startswith("/v1/webhook_endpoints")}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "skills/fluveo-integrate/spec").mkdir(parents=True)
        (root / "skills/fluveo-integrate/spec/openapi.subset.json").write_text(json.dumps(spec))
        references = root / "skills/fluveo-integrate/references"
        references.mkdir(parents=True, exist_ok=True)
        for name in REFERENCES:
            (references / name).write_text(WARNING)
        (references / "events-and-webhooks.md").write_text("Optional form serialization is unspecified.\n")
        assert not any(c == 8 for c, _, _ in run(root).failures)
        test_webhook_not_applicable_retry_guidance(run, root)
        test_webhook_form_examples_require_declared_encoding(run, root)
    print("webhook-guidance self-test passed (3 bad guides, changed policy, 2 undeclared wire keys rejected)")
