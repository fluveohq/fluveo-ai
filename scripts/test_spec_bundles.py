"""Exercise per-skill contract checks through the validator entry point."""
from pathlib import Path
import tempfile


def self_test(run):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assert any(c == 9 and "directory missing" in msg for c, _, msg in run(root).failures)
        (root / "skills").mkdir()
        assert any(c == 9 and "no skill contracts" in msg for c, _, msg in run(root).failures)
        paths = [root / "skills" / name / "spec/openapi.subset.json"
                 for name in ("fluveo-integrate", "fluveo-docs", "future-skill")]
        for path in paths:
            path.parent.mkdir(parents=True)
            path.write_text('{"paths": {}}')
        assert not any(c == 9 for c, _, _ in run(root).failures)
        for path in paths:
            path.write_text('{"paths": {}}\n')
            assert any(c == 9 and "sha256" in msg for c, _, msg in run(root).failures), (
                "self-test: spec copy drift not caught: " + str(path)
            )
            path.write_text('{"paths": {}}')
            path.unlink()
            assert any(c == 9 and str(path) == where for c, where, _ in run(root).failures), (
                "self-test: missing skill spec not caught: " + str(path)
            )
            path.write_text('{"paths": {}}')
    print("spec-bundles self-test passed (sha256 drift and missing copy caught for all 3 skills; clean accepted)")


if __name__ == "__main__":
    from validate import run
    self_test(run)
