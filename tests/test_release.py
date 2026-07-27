from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_documented_install import (
    SMOKE_TEST_END,
    SMOKE_TEST_START,
    documented_install_command,
    documented_source,
)


def test_readme_install_examples_use_one_immutable_source():
    readme = Path("README.md").read_text(encoding="utf-8")
    source = documented_source(readme)

    assert source.startswith(
        "git+https://github.com/julZanozina/documentation-mcp.git@"
    )
    assert documented_install_command(readme) == [
        "uvx",
        "--refresh",
        "--from",
        source,
        "documentation-mcp",
        "--help",
    ]


def test_documented_source_rejects_inconsistent_refs():
    readme = """
git+https://github.com/julZanozina/documentation-mcp.git@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
git+https://github.com/julZanozina/documentation-mcp.git@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"""

    with pytest.raises(ValueError, match="different immutable refs"):
        documented_source(readme)


def test_documented_source_accepts_version_release_tag():
    readme = (
        "git+https://github.com/julZanozina/"
        "documentation-mcp.git@v0.1.0a1"
    )

    assert documented_source(readme).endswith("@v0.1.0a1")


def test_documented_install_command_rejects_command_drift():
    source = (
        "git+https://github.com/julZanozina/"
        "documentation-mcp.git@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    readme = f"""
{source}
{SMOKE_TEST_START}
```zsh
uvx --from '{source}' wrong-command --help
```
{SMOKE_TEST_END}
"""

    with pytest.raises(ValueError, match="differs from the canonical command"):
        documented_install_command(readme)


def test_documented_install_command_requires_one_marked_block():
    source = (
        "git+https://github.com/julZanozina/"
        "documentation-mcp.git@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    with pytest.raises(ValueError, match="exactly one marked"):
        documented_install_command(source)
