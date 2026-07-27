#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
from pathlib import Path


DOCUMENTED_SOURCE_RE = re.compile(
    r"git\+https://github\.com/julZanozina/documentation-mcp\.git@"
    r"([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?)"
)
SMOKE_TEST_START = "<!-- documentation-mcp-install-smoke-test:start -->"
SMOKE_TEST_END = "<!-- documentation-mcp-install-smoke-test:end -->"


def documented_source(readme: str) -> str:
    refs = DOCUMENTED_SOURCE_RE.findall(readme)
    if not refs:
        raise ValueError("README has no immutable commit or version-tag installation ref")
    if len(set(refs)) != 1:
        raise ValueError("README installation examples use different immutable refs")
    return f"git+https://github.com/julZanozina/documentation-mcp.git@{refs[0]}"


def documented_install_command(readme: str) -> list[str]:
    if readme.count(SMOKE_TEST_START) != 1 or readme.count(SMOKE_TEST_END) != 1:
        raise ValueError("README must contain exactly one marked installation smoke test")
    marked = readme.split(SMOKE_TEST_START, 1)[1].split(SMOKE_TEST_END, 1)[0]
    match = re.fullmatch(r"\s*```(?:zsh|bash|sh)\n(.*?)```\s*", marked, re.DOTALL)
    if match is None:
        raise ValueError("Marked installation smoke test must contain one shell code block")

    command = match.group(1).replace("\\\n", " ")
    arguments = shlex.split(command)
    expected = [
        "uvx",
        "--refresh",
        "--from",
        documented_source(readme),
        "documentation-mcp",
        "--help",
    ]
    if arguments != expected:
        raise ValueError("Marked installation smoke test differs from the canonical command")
    return arguments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate the documented source without downloading it",
    )
    args = parser.parse_args()

    command = documented_install_command(
        Path("README.md").read_text(encoding="utf-8")
    )
    if not args.check_only:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
