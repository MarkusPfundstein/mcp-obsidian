from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_obsidian.obsidian import Obsidian


def _make_obsidian():
    return Obsidian(api_key="test-key", protocol="http", host="localhost", port=27123)


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


def _http_error_response(content=b'{"errorCode": 40149, "message": "bad key"}'):
    resp = requests.Response()
    resp.status_code = 401
    resp._content = content
    return resp


def test_constructor_defaults_to_https_for_unknown_protocol():
    api = Obsidian(api_key="key", protocol="ftp", host="host", port=1)
    assert api.get_base_url() == "https://host:1"


def test_constructor_allows_http_protocol():
    api = _make_obsidian()
    assert api.get_base_url() == "http://localhost:27123"


def test_get_headers_uses_bearer_token():
    assert _make_obsidian()._get_headers() == {"Authorization": "Bearer test-key"}


def test_safe_call_formats_http_error_json_body():
    api = _make_obsidian()
    error = requests.HTTPError(response=_http_error_response())

    with pytest.raises(Exception, match="Error 40149: bad key"):
        api._safe_call(MagicMock(side_effect=error))


def test_safe_call_handles_http_error_empty_body():
    api = _make_obsidian()
    error = requests.HTTPError(response=_http_error_response(b""))

    with pytest.raises(Exception, match="Error -1: <unknown>"):
        api._safe_call(MagicMock(side_effect=error))


def test_safe_call_handles_http_error_non_json_body():
    api = _make_obsidian()
    error = requests.HTTPError(response=_http_error_response(b"not json"))

    with pytest.raises(Exception, match="Error -1: <unknown>"):
        api._safe_call(MagicMock(side_effect=error))


def test_safe_call_handles_http_error_without_response():
    api = _make_obsidian()
    error = requests.HTTPError("no response")

    with pytest.raises(Exception, match="Error -1: <unknown>"):
        api._safe_call(MagicMock(side_effect=error))


def test_safe_call_wraps_request_exception():
    api = _make_obsidian()

    with pytest.raises(Exception, match="Request failed: boom"):
        api._safe_call(MagicMock(side_effect=requests.exceptions.Timeout("boom")))


def test_list_files_in_vault_hits_root_vault_endpoint():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_json_response({"files": ["a.md"]})) as mock_get:
        assert api.list_files_in_vault() == ["a.md"]

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "http://localhost:27123/vault/"
    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert mock_get.call_args.kwargs["verify"] is False
    assert mock_get.call_args.kwargs["timeout"] == (3, 6)


def test_list_files_in_dir_hits_directory_endpoint():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_json_response({"files": ["b.md"]})) as mock_get:
        assert api.list_files_in_dir("notes") == ["b.md"]

    assert mock_get.call_args.args[0] == "http://localhost:27123/vault/notes/"


def test_get_file_contents_returns_text():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("# Title")) as mock_get:
        assert api.get_file_contents("notes/a.md") == "# Title"

    assert mock_get.call_args.args[0] == "http://localhost:27123/vault/notes/a.md"


def test_search_posts_simple_query_params():
    api = _make_obsidian()
    payload = [{"filename": "a.md"}]
    with patch("mcp_obsidian.obsidian.requests.post", return_value=_json_response(payload)) as mock_post:
        assert api.search("needle", context_length=42) == payload

    assert mock_post.call_args.args[0] == "http://localhost:27123/search/simple/"
    assert mock_post.call_args.kwargs["params"] == {"query": "needle", "contextLength": 42}


def test_delete_file_uses_delete_method():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.delete", return_value=_json_response({})) as mock_delete:
        assert api.delete_file("notes/a.md") is None

    assert mock_delete.call_args.args[0] == "http://localhost:27123/vault/notes/a.md"


def test_search_json_posts_jsonlogic_payload():
    api = _make_obsidian()
    query = {"glob": ["*.md", {"var": "path"}]}
    payload = [{"filename": "a.md", "result": True}]
    with patch("mcp_obsidian.obsidian.requests.post", return_value=_json_response(payload)) as mock_post:
        assert api.search_json(query) == payload

    kwargs = mock_post.call_args.kwargs
    assert mock_post.call_args.args[0] == "http://localhost:27123/search/"
    assert kwargs["json"] == query
    assert kwargs["headers"]["Content-Type"] == "application/vnd.olrapi.jsonlogic+json"


def test_get_periodic_note_content_uses_plain_accept_headers():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response("daily text")) as mock_get:
        assert api.get_periodic_note("daily") == "daily text"

    assert mock_get.call_args.args[0] == "http://localhost:27123/periodic/daily/"
    assert "Accept" not in mock_get.call_args.kwargs["headers"]


def test_get_periodic_note_metadata_sets_note_json_accept_header():
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_text_response('{"path":"daily.md"}')) as mock_get:
        assert api.get_periodic_note("daily", type="metadata") == '{"path":"daily.md"}'

    assert mock_get.call_args.kwargs["headers"]["Accept"] == "application/vnd.olrapi.note+json"


def test_get_recent_periodic_notes_sends_query_params():
    api = _make_obsidian()
    payload = [{"path": "daily.md"}]
    with patch("mcp_obsidian.obsidian.requests.get", return_value=_json_response(payload)) as mock_get:
        assert api.get_recent_periodic_notes("daily", limit=3, include_content=True) == payload

    assert mock_get.call_args.args[0] == "http://localhost:27123/periodic/daily/recent"
    assert mock_get.call_args.kwargs["params"] == {"limit": 3, "includeContent": True}


def test_get_recent_changes_posts_dataview_query():
    api = _make_obsidian()
    payload = [{"filename": "a.md"}]
    with patch("mcp_obsidian.obsidian.requests.post", return_value=_json_response(payload)) as mock_post:
        assert api.get_recent_changes(limit=7, days=14) == payload

    kwargs = mock_post.call_args.kwargs
    assert mock_post.call_args.args[0] == "http://localhost:27123/search/"
    assert kwargs["headers"]["Content-Type"] == "application/vnd.olrapi.dataview.dql+txt"
    assert kwargs["data"] == b"TABLE file.mtime\nWHERE file.mtime >= date(today) - dur(14 days)\nSORT file.mtime DESC\nLIMIT 7"


def test_get_batch_file_contents_includes_successes_and_errors():
    api = _make_obsidian()
    with patch.object(api, "get_file_contents", side_effect=["alpha", Exception("missing"), "gamma"]):
        result = api.get_batch_file_contents(["a.md", "b.md", "c.md"])

    assert "# a.md\n\nalpha\n\n---\n\n" in result
    assert "# b.md\n\nError reading file: missing\n\n---\n\n" in result
    assert "# c.md\n\ngamma\n\n---\n\n" in result


def test_patch_content_sends_markdown_patch_version_header():
    """Local REST API >= 5.0.0 rejects PATCH without an explicit
    Markdown-Patch-Version header (error 40084)."""
    api = _make_obsidian()
    with patch("mcp_obsidian.obsidian.requests.patch", return_value=_json_response({})) as mock_patch:
        api.patch_content("f.md", "append", "heading", "A::B", "x")

    headers = mock_patch.call_args.kwargs["headers"]
    assert headers["Markdown-Patch-Version"] == "1"
    assert headers["Operation"] == "append"
    assert headers["Target-Type"] == "heading"
