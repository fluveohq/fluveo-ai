#!/usr/bin/env python3
"""Validate the fluveo-ai repository. Stdlib only. Exit 0 on success.

Checks:
  1. skills/*/SKILL.md frontmatter has non-empty name (== dir name) and description.
  2. Relative markdown links / <references/x.md> / `references/x.md` inside skills resolve.
  3. Every /v1 path in an HTTP/curl example line matches the OpenAPI subset (method+path),
     except paths listed in references/not-available.md, which must NOT be in the spec.
  4. No real-looking sk_test_/sk_live_ keys (other than sk_test_example / sk_test_...) or whsec_ secrets.
  5. .claude-plugin/plugin.json parses and has name/version/description.

Usage: python3 scripts/validate.py [--root DIR] [--self-test]
"""
import json
import os
import re
import sys
import tempfile

ID_PREFIXES = ("pi", "cus", "cs", "re", "ch", "plink", "seti", "prod", "price", "in", "sub", "txn", "ii", "pm", "li", "bt", "evt", "we")
# Matches `GET /v1/x`, and table rows like | `GET` | `/v1/x` | (backticks/pipes/whitespace between method and path).
METHOD_PATH_RE = re.compile(r"\b(GET|POST|PUT|DELETE)`?[\s|`]*(/v1/[^\s`|)\]\"',>]+)")
URL_PATH_RE = re.compile(r"(?:api\.devfluveo\.com|api\.fluveo\.dev|localhost:8080)(/v1/[^\s`|)\]\"',>]+)")
STALE_HOST = "api.fluveo.dev"
EXPLICIT_METHOD_RE = re.compile(r"-X\s+(GET|POST|PUT|DELETE)")
SECRET_RE = re.compile(r"sk_(?:test|live)_[A-Za-z0-9]{8,}")
WHSEC_RE = re.compile(r"whsec_[A-Za-z0-9]{8,}")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
ANGLE_REF_RE = re.compile(r"<(references/[^>\s]+)>")
TICK_REF_RE = re.compile(r"`(references/[A-Za-z0-9_./-]+\.md)`")


class Report:
    def __init__(self):
        self.failures = []
        self.summary = []

    def fail(self, check, where, msg):
        self.failures.append((check, where, msg))

    def ok(self, check, msg):
        self.summary.append((check, msg))


def normalise_path(path):
    path = path.split("?", 1)[0].rstrip("/.")
    out = []
    for seg in path.split("/"):
        if not seg:
            continue
        if seg.startswith("{") or seg.startswith(":") or seg.startswith("$") or seg.startswith("<"):
            out.append("{x}")
            continue
        head = seg.split("_", 1)[0]
        if "_" in seg and head in ID_PREFIXES:
            out.append("{x}")
            continue
        if seg == "...":
            out.append("{x}")
            continue
        out.append(seg)
    return "/" + "/".join(out)


def load_spec_ops(spec_path):
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    ops = set()
    for path, methods in spec.get("paths", {}).items():
        norm = re.sub(r"\{[^}]+\}", "{x}", path)
        for method in methods:
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                ops.add((method.upper(), norm))
    return ops


def skill_md_files(root):
    skills_dir = os.path.join(root, "skills")
    found = []
    for dirpath, _dirs, files in os.walk(skills_dir):
        for name in sorted(files):
            if name.endswith(".md"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def check_frontmatter(root, rep):
    skills_dir = os.path.join(root, "skills")
    count = 0
    if not os.path.isdir(skills_dir):
        rep.fail(1, skills_dir, "skills/ directory missing")
        return
    for entry in sorted(os.listdir(skills_dir)):
        skill_file = os.path.join(skills_dir, entry, "SKILL.md")
        if not os.path.isfile(skill_file):
            rep.fail(1, os.path.join(skills_dir, entry), "SKILL.md missing")
            continue
        count += 1
        with open(skill_file, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        if not lines or lines[0].strip() != "---":
            rep.fail(1, f"{skill_file}:1", "frontmatter must start with ---")
            continue
        fields = {}
        end = None
        for idx, line in enumerate(lines[1:], start=2):
            if line.strip() == "---":
                end = idx
                break
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
            if m:
                fields[m.group(1)] = m.group(2).strip().strip("\"'")
        if end is None:
            rep.fail(1, f"{skill_file}:1", "frontmatter not closed with ---")
            continue
        name = fields.get("name", "")
        if not name:
            rep.fail(1, f"{skill_file}:1", "frontmatter missing non-empty name")
        elif name != entry:
            rep.fail(1, f"{skill_file}:1", f"frontmatter name {name!r} != directory {entry!r}")
        if not fields.get("description"):
            rep.fail(1, f"{skill_file}:1", "frontmatter missing non-empty description")
    rep.ok(1, f"{count} SKILL.md file(s) with valid frontmatter")


def check_links(root, rep):
    count = 0
    for md in skill_md_files(root):
        skill_root = md
        while os.path.basename(os.path.dirname(skill_root)) != "skills" and os.path.dirname(skill_root) != skill_root:
            skill_root = os.path.dirname(skill_root)
        skill_root = os.path.dirname(skill_root) if os.path.isfile(skill_root) else skill_root
        with open(md, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                targets = []
                for m in LINK_RE.finditer(line):
                    t = m.group(1)
                    if t.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    targets.append(t)
                targets += ANGLE_REF_RE.findall(line)
                targets += TICK_REF_RE.findall(line)
                for t in targets:
                    t = t.split("#", 1)[0]
                    if not t:
                        continue
                    count += 1
                    candidates = [
                        os.path.normpath(os.path.join(os.path.dirname(md), t)),
                        os.path.normpath(os.path.join(skill_root, t)),
                        os.path.normpath(os.path.join(root, t)),
                    ]
                    if not any(os.path.exists(c) for c in candidates):
                        rep.fail(2, f"{md}:{lineno}", f"broken link {t!r}")
    rep.ok(2, f"{count} relative link(s) resolved")


def extract_endpoints(line):
    """Yield (method_or_None, normalised_path) for HTTP/curl example mentions on a line."""
    found = []
    for m in METHOD_PATH_RE.finditer(line):
        found.append((m.group(1), normalise_path(m.group(2))))
    explicit = EXPLICIT_METHOD_RE.search(line)
    for m in URL_PATH_RE.finditer(line):
        method = explicit.group(1) if explicit else None
        found.append((method, normalise_path(m.group(1))))
    return found


def check_endpoints(root, rep):
    spec_path = os.path.join(root, "spec", "openapi.subset.json")
    if not os.path.isfile(spec_path):
        rep.fail(3, spec_path, "spec/openapi.subset.json missing")
        return
    ops = load_spec_ops(spec_path)
    spec_paths = {p for _m, p in ops}

    not_available = set()
    for md in skill_md_files(root):
        if os.path.basename(md) != "not-available.md":
            continue
        with open(md, encoding="utf-8") as fh:
            for line in fh:
                for method, path in extract_endpoints(line):
                    not_available.add((method, path))
    na_paths_any = {p for m, p in not_available if m is None}
    na_method_paths = {(m, p) for m, p in not_available if m is not None}

    checked = 0
    for md in skill_md_files(root):
        with open(md, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                for method, path in extract_endpoints(line):
                    checked += 1
                    where = f"{md}:{lineno}"
                    excluded = path in na_paths_any or (method, path) in na_method_paths or (
                        method is None and any(p == path for _m, p in na_method_paths)
                    )
                    if excluded:
                        if method is not None:
                            if (method, path) in ops:
                                rep.fail(3, where, f"{method} {path} is listed as not-available but IS in the spec")
                        elif path in spec_paths and path in na_paths_any:
                            rep.fail(3, where, f"{path} is listed as not-available but IS in the spec")
                        continue
                    if method is not None:
                        if (method, path) not in ops:
                            rep.fail(3, where, f"{method} {path} not in spec/openapi.subset.json")
                    elif path not in spec_paths:
                        rep.fail(3, where, f"{path} not in spec/openapi.subset.json")
    rep.ok(3, f"{checked} endpoint mention(s) checked against {len(ops)} spec operations; {len(not_available)} not-available entries")


def check_secrets(root, rep):
    scanned = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "spec")]
        for name in files:
            if not name.endswith((".md", ".json", ".py", ".txt")):
                continue
            fp = os.path.join(dirpath, name)
            if os.path.abspath(fp) == os.path.abspath(__file__):
                continue
            scanned += 1
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    for m in SECRET_RE.finditer(line):
                        if m.group(0) in ("sk_test_example",):
                            continue
                        rep.fail(4, f"{fp}:{lineno}", f"real-looking secret key {m.group(0)!r}")
                    for m in WHSEC_RE.finditer(line):
                        rep.fail(4, f"{fp}:{lineno}", f"real-looking webhook secret {m.group(0)!r}")
    rep.ok(4, f"{scanned} file(s) scanned for secrets")


def check_plugin(root, rep):
    fp = os.path.join(root, ".claude-plugin", "plugin.json")
    if not os.path.isfile(fp):
        rep.fail(5, fp, "plugin.json missing")
        return
    try:
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        rep.fail(5, f"{fp}:{exc.lineno}", f"invalid JSON: {exc.msg}")
        return
    for key in ("name", "version", "description"):
        if not isinstance(data.get(key), str) or not data.get(key):
            rep.fail(5, fp, f"plugin.json missing non-empty {key!r}")
    rep.ok(5, f"plugin.json ok ({data.get('name')} {data.get('version')})")


def check_stale_host(root, rep):
    hits = 0
    for md in skill_md_files(root):
        with open(md, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if STALE_HOST in line:
                    hits += 1
                    rep.fail(6, f"{md}:{lineno}", f"stale host {STALE_HOST!r}; use api.devfluveo.com")
    if not hits:
        rep.ok(6, f"no stale host {STALE_HOST!r} in skills/**/*.md")


def run(root):
    rep = Report()
    check_frontmatter(root, rep)
    check_links(root, rep)
    check_endpoints(root, rep)
    check_secrets(root, rep)
    check_plugin(root, rep)
    check_stale_host(root, rep)
    return rep


def print_report(rep):
    for check, msg in rep.summary:
        print(f"[check {check}] OK   {msg}")
    for check, where, msg in rep.failures:
        print(f"[check {check}] FAIL {where}: {msg}")
    print(f"{len(rep.failures)} failure(s)")


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "spec"))
        os.makedirs(os.path.join(tmp, ".claude-plugin"))
        os.makedirs(os.path.join(tmp, "skills", "broken", "references"))
        with open(os.path.join(tmp, "spec", "openapi.subset.json"), "w") as fh:
            json.dump({"paths": {"/v1/payment_intents": {"post": {}}, "/v1/payment_intents/{intent}": {"get": {}}}}, fh)
        with open(os.path.join(tmp, ".claude-plugin", "plugin.json"), "w") as fh:
            json.dump({"name": "x", "version": "0.0.1", "description": "d"}, fh)
        with open(os.path.join(tmp, "skills", "broken", "SKILL.md"), "w") as fh:
            fh.write("---\nname: broken\ndescription: deliberately broken\n---\n"
                     "See [missing](references/missing.md).\n"
                     "POST /v1/payment_intents\n"
                     "GET /v1/payment_intents/pi_1A9e8AzB2xQRH9JfQu5N\n"
                     "POST /v1/webhook_endpoints\n"
                     "| `POST` | `/v1/payment_intents/{intent}/apply_thing` | table row |\n"
                     "curl https://api.fluveo.dev/v1/disputes -u sk_test_51Habcdefghijklmnop:\n")
        with open(os.path.join(tmp, "skills", "broken", "references", "not-available.md"), "w") as fh:
            fh.write("- `POST /v1/payment_intents` (wrongly listed)\n")
        rep = run(tmp)
        kinds = {(c, m.split(" ")[0] if c == 3 else "") for c, _w, m in rep.failures}
        got_link = any(c == 2 for c, _w, _m in rep.failures)
        got_unknown = any(c == 3 and "not in spec" in m for c, _w, m in rep.failures)
        got_na_conflict = any(c == 3 and "IS in the spec" in m for c, _w, m in rep.failures)
        got_key = any(c == 4 for c, _w, _m in rep.failures)
        got_stale = any(c == 6 for c, _w, _m in rep.failures)
        print_report(rep)
        assert got_link, "self-test: bad link not caught"
        assert got_unknown, "self-test: unknown endpoint not caught"
        assert got_na_conflict, "self-test: not-available conflict not caught"
        assert got_key, "self-test: fake key not caught"
        assert got_stale, "self-test: stale host not caught"
        unknown_paths = {m for c, _w, m in rep.failures if c == 3 and "not in spec" in m}
        assert not any("GET /v1/payment_intents/{x} not" in m for m in unknown_paths), "self-test: id normalisation failed"
        assert any("/v1/disputes" in m for m in unknown_paths), "self-test: URL-form endpoint not caught"
        assert any("/v1/payment_intents/{x}/apply_thing" in m for m in unknown_paths), "self-test: table-row endpoint not caught"
        print("self-test passed")


def main(argv):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "--root" in argv:
        root = os.path.abspath(argv[argv.index("--root") + 1])
    if "--self-test" in argv:
        self_test()
        return 0
    rep = run(root)
    print_report(rep)
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
