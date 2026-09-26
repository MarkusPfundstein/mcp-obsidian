"""Tests for UTF-8 encoding in write requests (issue #135)."""

from unittest.mock import MagicMock, patch

from mcp_obsidian.obsidian import Obsidian


SAMPLE = "Hallo — Größe für Müller-Lüdenscheidt 🚀"


def _make_obsidian():
    return Obsidian(api_key="test-key", protocol="http", host="localhost", port=27123)


def _ok_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


def test_append_content_sends_utf8_bytes_and_charset():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.post", return_value=_ok_response()) as mock_post:
        api.append_content("f.md", SAMPLE)
        kwargs = mock_post.call_args.kwargs
        assert kwargs["data"] == SAMPLE.encode("utf-8")
        assert isinstance(kwargs["data"], (bytes, bytearray))
        assert kwargs["headers"]["Content-Type"] == "text/markdown; charset=utf-8"


def test_patch_content_sends_utf8_bytes_with_plain_content_type():
    """PATCH endpoint rejects charset in Content-Type (error 40012), so we send
    the body as utf-8 bytes but keep the header plain 'text/markdown'."""
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.patch", return_value=_ok_response()) as mock_patch:
        api.patch_content("f.md", "append", "heading", "A::B", SAMPLE)
        kwargs = mock_patch.call_args.kwargs
        assert kwargs["data"] == SAMPLE.encode("utf-8")
        assert isinstance(kwargs["data"], (bytes, bytearray))
        assert kwargs["headers"]["Content-Type"] == "text/markdown"


def test_patch_content_sends_markdown_patch_version_1_header():
    """The Local REST API now supports two PATCH formats (2.0 JSON-instruction
    body vs. this client's deprecated 1.x Target-Type/Target header-driven form)
    and rejects header-driven requests as ambiguous unless they explicitly opt
    into the 1.x format with 'Markdown-Patch-Version: 1'. Confirmed 260926
    against a current Local REST API install — every patch_content call failed
    outright without this header."""
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.patch", return_value=_ok_response()) as mock_patch:
        api.patch_content("f.md", "append", "heading", "A::B", SAMPLE)
        kwargs = mock_patch.call_args.kwargs
        assert kwargs["headers"]["Markdown-Patch-Version"] == "1"


def test_put_content_sends_utf8_bytes_and_charset():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.put", return_value=_ok_response()) as mock_put:
        api.put_content("f.md", SAMPLE)
        kwargs = mock_put.call_args.kwargs
        assert kwargs["data"] == SAMPLE.encode("utf-8")
        assert isinstance(kwargs["data"], (bytes, bytearray))
        assert kwargs["headers"]["Content-Type"] == "text/markdown; charset=utf-8"
