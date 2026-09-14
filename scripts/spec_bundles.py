"""Require every skill to ship the same contract bytes."""
import hashlib
from pathlib import Path


def check_spec_bundles(root, report):
    skills = Path(root) / "skills"
    if not skills.is_dir():
        report.fail(9, str(skills), "skills directory missing")
        return
    copies = []
    before = len(report.failures)
    for skill in sorted(skills.iterdir()):
        if not skill.is_dir():
            continue
        path = skill / "spec/openapi.subset.json"
        if not path.is_file():
            report.fail(9, str(path), "skill contract missing")
            continue
        copies.append(hashlib.sha256(path.read_bytes()).hexdigest())
    if not copies:
        report.fail(9, str(skills), "no skill contracts found")
    elif len(set(copies)) != 1:
        report.fail(9, str(skills), "skill contract sha256 mismatch")
    if len(report.failures) == before:
        report.ok(9, f"{len(copies)} skill contract copies have identical sha256")
