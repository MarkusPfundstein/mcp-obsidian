import asyncio
from collections.abc import Awaitable
from typing import TypeVar
from unittest.mock import MagicMock, patch

import pytest
import requests


from mcp_obsidian import server, tools
from mcp_obsidian.obsidian import Obsidian, validate_vault_path


def _make_obsidian():
    return Obsidian(api_key="test-key", protocol="http", host="localhost", port=27123)


def _ok_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    return resp


def _json_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def _text_response(text):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# 1. validate_vault_path unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_path,expected",
    [
        ("a.md", "a.md"),
        ("notes/a.md", "notes/a.md"),
        ("deep/nested/dir/note.md", "deep/nested/dir/note.md"),
        ("notes/./sub/doc.md", "notes/sub/doc.md"),
        ("notes/a.md/", "notes/a.md"),
        ("My Notes 2026/Daily Note.md", "My Notes 2026/Daily Note.md"),
        ("Größe für Müller-Lüdenscheidt 🚀.md", "Größe für Müller-Lüdenscheidt 🚀.md"),
        ("C#.md", "C#.md"),
        ("Discount 50%.md", "Discount 50%.md"),
        ("file-1_2.md", "file-1_2.md"),
    ],
)
def test_validate_vault_path_accepts_valid_files(valid_path, expected):
    assert validate_vault_path(valid_path, is_dir=False) == expected


@pytest.mark.parametrize(
    "valid_dir,expected",
    [
        ("", ""),
        (".", ""),
        ("/", ""),
        ("notes", "notes"),
        ("notes/", "notes"),
        ("nested/folder", "nested/folder"),
        ("nested/folder/", "nested/folder"),
        ("My Notes", "My Notes"),
    ],
)
def test_validate_vault_path_accepts_valid_directories(valid_dir, expected):
    assert validate_vault_path(valid_dir, is_dir=True) == expected


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../secret.txt",
        "../../admin/secret.txt",
        "..",
        "notes/../../secret.txt",
        "notes/../secret.txt",
        "foo/bar/../../../etc/passwd",
        "notes/../",
        "./../secret.txt",
    ],
)
def test_validate_vault_path_rejects_parent_traversal(traversal_path):
    with pytest.raises(ValueError, match="Path traversal|Path resolves outside"):
        validate_vault_path(traversal_path)


@pytest.mark.parametrize(
    "absolute_path",
    [
        "/etc/passwd",
        "/notes/a.md",
        "//etc/passwd",
        "/../../etc/passwd",
        "///root/secret",
    ],
)
def test_validate_vault_path_rejects_absolute_paths(absolute_path):
    with pytest.raises(ValueError, match="Absolute path"):
        validate_vault_path(absolute_path)


@pytest.mark.parametrize(
    "encoded_path",
    [
        "%2e%2e/secret.txt",
        "%2e%2e%2fsecret.txt",
        "%2e%2e%5csecret.txt",
        ".%2e/secret.txt",
        "%252e%252e/secret.txt",
        "%252e%252e%252fsecret.txt",
        "%25252e%25252e/secret.txt",
        "notes/%2e%2e/secret.txt",
        "notes/%252e%252e/secret.txt",
        # Six layers of encoding: still changing after the five-pass cap,
        # so it is rejected fail-closed (see Copilot review on the PR).
        "..%25252525252Fsecret.txt",
    ],
)
def test_validate_vault_path_rejects_url_encoded_traversals(encoded_path):
    with pytest.raises(ValueError, match="Path traversal|Path resolves outside|excessively nested"):
        validate_vault_path(encoded_path)


@pytest.mark.parametrize(
    "windows_path",
    [
        r"..\..\secret.txt",
        r"..\secret.txt",
        r"notes\..\secret.txt",
        r"C:\secret.txt",
        r"C:/secret.txt",
        r"D:\vault\note.md",
        r"\\server\share\file.txt",
    ],
)
def test_validate_vault_path_rejects_windows_traversal_and_drive_letters(windows_path):
    with pytest.raises(ValueError, match="Path traversal|Absolute"):
        validate_vault_path(windows_path)


@pytest.mark.parametrize(
    "null_byte_path",
    [
        "notes/secret.txt\x00.md",
        "notes/%00secret.txt",
        "\x00/evil",
    ],
)
def test_validate_vault_path_rejects_null_bytes(null_byte_path):
    with pytest.raises(ValueError, match="null bytes"):
        validate_vault_path(null_byte_path)


@pytest.mark.parametrize("empty_file", ["", "   ", "."])
def test_validate_vault_path_rejects_empty_filepath(empty_file):
    with pytest.raises(ValueError, match="Filepath cannot be empty"):
        validate_vault_path(empty_file, is_dir=False)


@pytest.mark.parametrize("non_string", [None, 123, [], {}, True])
def test_validate_vault_path_rejects_non_string_types(non_string):
    with pytest.raises(ValueError, match="Vault path must be a string"):
        validate_vault_path(non_string)


# ---------------------------------------------------------------------------
# 2. Obsidian client method validation & no-outbound-request tests
# ---------------------------------------------------------------------------


def test_list_files_in_dir_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get") as mock_get:
        with pytest.raises(ValueError, match="Path traversal"):
            api.list_files_in_dir("../../admin")
        mock_get.assert_not_called()


def test_get_file_contents_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get") as mock_get:
        with pytest.raises(ValueError, match="Path traversal"):
            api.get_file_contents("../../admin/secret.txt")
        with pytest.raises(ValueError, match="Path traversal"):
            api.get_file_contents("%2e%2e/secret.txt")
        with pytest.raises(ValueError, match="Absolute path"):
            api.get_file_contents("/etc/passwd")
        with pytest.raises(ValueError, match="Absolute Windows path"):
            api.get_file_contents(r"C:\Windows\win.ini")
        mock_get.assert_not_called()


def test_append_content_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.post") as mock_post:
        with pytest.raises(ValueError, match="Path traversal"):
            api.append_content("../../secret.txt", "evil data")
        mock_post.assert_not_called()


def test_patch_content_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.patch") as mock_patch:
        with pytest.raises(ValueError, match="Path traversal"):
            api.patch_content("../../secret.txt", "append", "heading", "H1", "evil data")
        mock_patch.assert_not_called()


def test_put_content_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.put") as mock_put:
        with pytest.raises(ValueError, match="Path traversal"):
            api.put_content("../../secret.txt", "evil data")
        mock_put.assert_not_called()


def test_delete_file_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.delete") as mock_delete:
        with pytest.raises(ValueError, match="Path traversal"):
            api.delete_file("../../secret.txt")
        mock_delete.assert_not_called()


def test_get_frontmatter_rejects_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get") as mock_get:
        with pytest.raises(ValueError, match="Path traversal"):
            api.get_frontmatter("../../secret.txt")
        mock_get.assert_not_called()


def test_search_by_tag_rejects_traversal_in_dirpath():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.post") as mock_post:
        with pytest.raises(ValueError, match="Path traversal"):
            api.search_by_tag("project", dirpath="../../etc")
        mock_post.assert_not_called()


def test_get_batch_file_contents_records_error_without_calling_server_for_traversal():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("valid content")) as mock_get:
        result = api.get_batch_file_contents(["../../secret.txt", "valid.md"])

    # Traversal entry must have an error message
    assert "# ../../secret.txt\n\nError reading file: Path traversal ('..') is not allowed" in result
    # Valid file must succeed
    assert "# valid.md\n\nvalid content" in result
    # Only 1 HTTP call made (for valid.md), traversal was blocked locally
    assert mock_get.call_count == 1
    assert mock_get.call_args.args[0] == "http://localhost:27123/vault/valid.md"


# ---------------------------------------------------------------------------
# 3. URL encoding of path segments in outbound requests
# ---------------------------------------------------------------------------


def test_outbound_urls_properly_encode_spaces_and_special_characters():
    api = _make_obsidian()

    # Space in filename
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("text")) as mock_get:
        api.get_file_contents("notes/My Note.md")
        assert mock_get.call_args.args[0] == "http://localhost:27123/vault/notes/My%20Note.md"

    # Hash in filename (# must be %23, not URL fragment)
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("text")) as mock_get:
        api.get_file_contents("notes/C#.md")
        assert mock_get.call_args.args[0] == "http://localhost:27123/vault/notes/C%23.md"

    # Unicode / umlaut in filename
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("text")) as mock_get:
        api.get_file_contents("notes/Über.md")
        assert mock_get.call_args.args[0] == "http://localhost:27123/vault/notes/%C3%9Cber.md"

    # Directory with space
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_json_response({"files": []})) as mock_get:
        api.list_files_in_dir("My Notes")
        assert mock_get.call_args.args[0] == "http://localhost:27123/vault/My%20Notes/"

    # Directory root
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_json_response({"files": []})) as mock_get:
        api.list_files_in_dir("")
        assert mock_get.call_args.args[0] == "http://localhost:27123/vault/"


# ---------------------------------------------------------------------------
# 4. MCP tool execution & server.call_tool end-to-end integration tests
# ---------------------------------------------------------------------------


T = TypeVar("T")


async def _await(awaitable: Awaitable[T]) -> T:
    return await awaitable


def _call_tool(name: str, arguments: dict):
    return asyncio.run(_await(server.call_tool(name, arguments)))



@pytest.mark.parametrize(
    "tool_name,arguments",
    [
        ("obsidian_get_file_contents", {"filepath": "../../admin/secret.txt"}),
        ("obsidian_get_file_contents", {"filepath": "%2e%2e/secret.txt"}),
        ("obsidian_get_file_contents", {"filepath": "/etc/passwd"}),
        ("obsidian_list_files_in_dir", {"dirpath": "../../admin"}),
        ("obsidian_list_files_in_dir", {"dirpath": "/etc"}),
        ("obsidian_put_content", {"filepath": "../../secret.txt", "content": "data"}),
        ("obsidian_append_content", {"filepath": "../../secret.txt", "content": "data"}),
        (
            "obsidian_patch_content",
            {
                "filepath": "../../secret.txt",
                "operation": "append",
                "target_type": "heading",
                "target": "H",
                "content": "data",
            },
        ),
        ("obsidian_delete_file", {"filepath": "../../secret.txt", "confirm": True}),
        ("obsidian_get_frontmatter", {"filepath": "../../secret.txt"}),
        ("obsidian_search_by_tag", {"tag": "project", "dirpath": "../../admin"}),
    ],
)
def test_server_call_tool_blocks_traversal_payloads(tool_name, arguments):
    with patch("mcp_obsidian.obsidian.requests.get") as mock_get, \
         patch("mcp_obsidian.obsidian.requests.post") as mock_post, \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put, \
         patch("mcp_obsidian.obsidian.requests.patch") as mock_patch, \
         patch("mcp_obsidian.obsidian.requests.delete") as mock_delete:
        with pytest.raises(RuntimeError, match="Caught Exception. Error: (Path traversal|Absolute)"):
            _call_tool(tool_name, arguments)

        # No request must ever be sent over HTTP
        mock_get.assert_not_called()
        mock_post.assert_not_called()
        mock_put.assert_not_called()
        mock_patch.assert_not_called()
        mock_delete.assert_not_called()


def test_search_by_tag_root_dirpath_omits_glob():
    api = _make_obsidian()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = []

    with patch("mcp_obsidian.obsidian.requests.post", return_value=resp) as mock_post:
        api.search_by_tag("tasks", dirpath=".")


@pytest.mark.parametrize(
    "payload",
    [
        "..%c0%af",  # overlong UTF-8 for '/'
        "%c0%ae%c0%ae/",  # overlong UTF-8 for '..'
        "%c0%ae/%c0%ae/x",
        "notes/..%c0%af/x",
        "..%c0%af..%c0%afsecret.txt",
        "%e0%80%ae%e0%80%ae/",  # another overlong encoding of '..'
        "%25%32%35%32%65%25%32%35%32%65",  # triple-nested encoding of '..'
        "%25252e%25252e%25252f",  # triple-nested encoding of '../'
    ],
)
def test_validate_vault_path_rejects_invalid_utf8_and_nested_encoding(payload):
    with pytest.raises(ValueError):
        validate_vault_path(payload)
    with pytest.raises(ValueError):
        validate_vault_path(payload, is_dir=True)


@pytest.mark.parametrize(
    "payload",
    [
        "..%c0%af",
        "%c0%ae%c0%ae/secret.txt",
        "notes/..%c0%af/x",
    ],
)
@pytest.mark.parametrize(
    "tool_name,argument_name,extra_arguments",
    [
        ("obsidian_get_file_contents", "filepath", {}),
        ("obsidian_list_files_in_dir", "dirpath", {}),
        ("obsidian_put_content", "filepath", {"content": "data"}),
        ("obsidian_delete_file", "filepath", {"confirm": True}),
        ("obsidian_get_frontmatter", "filepath", {}),
    ],
)
def test_server_call_tool_blocks_overlong_utf8_payloads(tool_name, argument_name, extra_arguments, payload):
    arguments = {argument_name: payload, **extra_arguments}
    with patch("mcp_obsidian.obsidian.requests.get") as mock_get, \
         patch("mcp_obsidian.obsidian.requests.post") as mock_post, \
         patch("mcp_obsidian.obsidian.requests.put") as mock_put, \
         patch("mcp_obsidian.obsidian.requests.delete") as mock_delete:
        with pytest.raises(RuntimeError, match="Caught Exception. Error:"):
            _call_tool(tool_name, arguments)

        mock_get.assert_not_called()
        mock_post.assert_not_called()
        mock_put.assert_not_called()
        mock_delete.assert_not_called()


