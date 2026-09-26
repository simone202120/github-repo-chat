"""PreToolUse hook: blocks access to secret files and dangerous shell commands."""

import json
import re
import sys

SECRET_PATH = re.compile(
    r"(^|[\\/])\.env(\.(?!example\b)[\w.-]+)?$|\.(pem|key)$|[\\/]secrets?[\\/]"
)
SECRET_IN_COMMAND = re.compile(r"(^|[\s'\"/\\])\.env(\.(?!example\b)[\w.-]+)?(?=$|[\s'\";|&])")
DANGEROUS_COMMANDS = [
    (
        re.compile(r"git\s+push\b.*(--force\b|--force-with-lease\b|\s-f\b)"),
        "force push is not allowed",
    ),
    (
        re.compile(r"git\s+push\b.*\b(origin\s+)?(HEAD:)?main\b"),
        "push to main is not allowed: open a PR",
    ),
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r"),
        "rm -rf is not allowed",
    ),
]


def block(reason: str) -> None:
    print(f"Blocked by project hook: {reason}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})

    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if path and SECRET_PATH.search(path):
        block(f"access to secret file '{path}'")

    command = tool_input.get("command", "")
    if command:
        if SECRET_IN_COMMAND.search(command):
            block("shell access to .env files")
        for pattern, reason in DANGEROUS_COMMANDS:
            if pattern.search(command):
                block(reason)


if __name__ == "__main__":
    main()
