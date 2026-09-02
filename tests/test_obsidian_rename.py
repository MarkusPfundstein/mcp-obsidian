from unittest.mock import MagicMock, call, patch

import pytest
import requests

from mcp_obsidian.obsidian import Obsidian


def _make_api():
    return Obsidian(api_key="test-key", protocol="http", host="localhost", port=27123)


def _ok_response(status=200, text="# content"):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status.return_value = None
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# _file_exists
# ---------------------------------------------------------------------------

def test_file_exists_returns_true_on_200():
    api = _make_api()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_ok_response(200)):
        assert api._file_exists("notes/a.md") is True


def test_file_exists_returns_false_on_404():
    api = _make_api()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_ok_response(404)):
        assert api._file_exists("notes/missing.md") is False


def test_file_exists_returns_false_on_request_exception():
    api = _make_api()
    with patch("mcp_obsidian.obsidian.requests.get", side_effect=requests.exceptions.ConnectionError()):
        assert api._file_exists("notes/a.md") is False


# ---------------------------------------------------------------------------
# rename_file — guard conditions
# ---------------------------------------------------------------------------

def test_rename_file_raises_on_same_path():
    api = _make_api()
    with pytest.raises(Exception, match="identical"):
        api.rename_file("notes/a.md", "notes/a.md")


def test_rename_file_raises_when_destination_exists():
    api = _make_api()
    with patch.object(api, "_file_exists", return_value=True):
        with pytest.raises(Exception, match="already exists"):
            api.rename_file("notes/a.md", "notes/b.md")


# ---------------------------------------------------------------------------
# rename_file — happy path
# ---------------------------------------------------------------------------

def test_rename_file_happy_path_calls_get_put_delete_in_order():
    api = _make_api()
    calls = []

    with patch.object(api, "_file_exists", return_value=False), \
         patch.object(api, "get_file_contents", side_effect=lambda p: calls.append(("get", p)) or "# body"), \
         patch.object(api, "put_content", side_effect=lambda p, c: calls.append(("put", p, c))), \
         patch.object(api, "delete_file", side_effect=lambda p: calls.append(("delete", p))):
        api.rename_file("notes/a.md", "notes/b.md")

    assert calls == [
        ("get", "notes/a.md"),
        ("put", "notes/b.md", "# body"),
        ("delete", "notes/a.md"),
    ]


# ---------------------------------------------------------------------------
# rename_file — partial failure / rollback
# ---------------------------------------------------------------------------

def test_rename_file_rolls_back_if_delete_fails():
    api = _make_api()
    deleted = []

    def fake_delete(path):
        if path == "notes/a.md":
            raise Exception("delete failed")
        deleted.append(path)

    with patch.object(api, "_file_exists", return_value=False), \
         patch.object(api, "get_file_contents", return_value="# body"), \
         patch.object(api, "put_content"), \
         patch.object(api, "delete_file", side_effect=fake_delete):
        with pytest.raises(Exception, match="Rename failed"):
            api.rename_file("notes/a.md", "notes/b.md")

    assert "notes/b.md" in deleted, "compensating delete of destination must be attempted"


def test_rename_file_re_raises_even_if_compensating_delete_also_fails():
    api = _make_api()

    with patch.object(api, "_file_exists", return_value=False), \
         patch.object(api, "get_file_contents", return_value="# body"), \
         patch.object(api, "put_content"), \
         patch.object(api, "delete_file", side_effect=Exception("always fails")):
        with pytest.raises(Exception, match="Rename failed"):
            api.rename_file("notes/a.md", "notes/b.md")
