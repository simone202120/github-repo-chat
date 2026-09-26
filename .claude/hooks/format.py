"""PostToolUse hook: formats and auto-fixes a Python file right after Claude edits it."""

import json
import shutil
import subprocess
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    path = payload.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py") or not shutil.which("uv"):
        return
    for args in (["ruff", "format", path], ["ruff", "check", "--fix", "--quiet", path]):
        subprocess.run(["uv", "run", "--quiet", *args], capture_output=True, check=False)


if __name__ == "__main__":
    main()
