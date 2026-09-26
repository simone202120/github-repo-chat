"""SessionStart hook: prints branch, working tree status and open PRs to orient a new session."""

import shutil
import subprocess


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def main() -> None:
    print(f"Branch: {run('git', 'branch', '--show-current') or '(detached)'}")
    print(f"Working tree:\n{run('git', 'status', '--short') or '  clean'}")
    print(f"Recent commits:\n{run('git', 'log', '--oneline', '-5')}")
    if shutil.which("gh"):
        prs = run("gh", "pr", "list", "--limit", "10")
        print(f"Open PRs:\n{prs or '  none'}")


if __name__ == "__main__":
    main()
