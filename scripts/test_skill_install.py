"""Run the published lookup snippets from a consumer folder, not this repo."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def check_snippets(consumer, skill):
    text = (skill / "SKILL.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
    assert len(blocks) == 3, "expected list, fields, and jq examples"
    for index, block in enumerate(blocks):
        block = re.sub(r'^export SKILL_DIR=.*$', '', block, flags=re.M)
        result = subprocess.run(
            ["bash", "-e", "-c", block], cwd=consumer,
            env={**os.environ, "SKILL_DIR": str(skill)},
            text=True, capture_output=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        if index == 0:
            assert len(result.stdout.splitlines()) == 67, result.stdout
            print(result.stdout, end="")
            print("consumer list-operations snippet: 67 operations")
        elif index == 1:
            assert "== POST /v1/payment_intents" in result.stdout
        else:
            assert "GET /v1/refunds" in result.stdout and '"$ref"' in result.stdout
    print("consumer snippets passed (list, fields, jq)")


def self_test():
    source = Path(__file__).resolve().parents[1] / "skills/fluveo-docs"
    with tempfile.TemporaryDirectory(prefix="fluveo-consumer-") as directory:
        consumer = Path(directory)
        skill = consumer / ".agents/skills/fluveo-docs"
        shutil.copytree(source, skill)
        check_snippets(consumer, skill)


if __name__ == "__main__":
    self_test()
