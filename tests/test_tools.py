import json
from unittest.mock import patch

import pytest

from mcp_obsidian import tools


def _text(result):
    assert len(result) == 1
    return result[0].text


def _run_handler(handler, method_name, args, return_value=None):
    with patch("mcp_obsidian.tools.obsidian.Obsidian") as mock_cls:
        api = mock_cls.return_value
        getattr(api, method_name).return_value = return_value
        result = handler.run_tool(args)
    mock_cls.assert_called_once_with(api_key="test-key", host="127.0.0.1")
    return result, api


def test_base_tool_handler_requires_overrides():
    handler = tools.ToolHandler("base")

    with pytest.raises(NotImplementedError):
        handler.get_tool_description()
    with pytest.raises(NotImplementedError):
        handler.run_tool({})


def test_list_files_in_vault_handler_returns_json():
    result, api = _run_handler(tools.ListFilesInVaultToolHandler(), "list_files_in_vault", {}, ["a.md"])

    api.list_files_in_vault.assert_called_once_with()
    assert json.loads(_text(result)) == ["a.md"]


def test_list_files_in_dir_handler_validates_and_calls_api():
    handler = tools.ListFilesInDirToolHandler()
    with pytest.raises(RuntimeError, match="dirpath"):
        handler.run_tool({})

    result, api = _run_handler(handler, "list_files_in_dir", {"dirpath": "notes"}, ["a.md"])
    api.list_files_in_dir.assert_called_once_with("notes")
    assert json.loads(_text(result)) == ["a.md"]


def test_get_file_contents_handler_json_encodes_content():
    handler = tools.GetFileContentsToolHandler()
    with pytest.raises(RuntimeError, match="filepath"):
        handler.run_tool({})

    result, api = _run_handler(handler, "get_file_contents", {"filepath": "a.md"}, "# Title")
    api.get_file_contents.assert_called_once_with("a.md")
    assert json.loads(_text(result)) == "# Title"


def test_search_handler_formats_matches_and_defaults_context_length():
    api_results = [
        {
            "filename": "a.md",
            "score": 0.75,
            "matches": [{"context": "abc needle def", "match": {"start": 4, "end": 10}}],
        },
        {"filename": "b.md"},
    ]
    handler = tools.SearchToolHandler()
    with pytest.raises(RuntimeError, match="query"):
        handler.run_tool({})

    result, api = _run_handler(handler, "search", {"query": "needle"}, api_results)
    api.search.assert_called_once_with("needle", 100)
    assert json.loads(_text(result)) == [
        {
            "filename": "a.md",
            "score": 0.75,
            "matches": [{"context": "abc needle def", "match_position": {"start": 4, "end": 10}}],
        },
        {"filename": "b.md", "score": 0, "matches": []},
    ]


def test_search_handler_passes_custom_context_length():
    handler = tools.SearchToolHandler()
    _, api = _run_handler(handler, "search", {"query": "needle", "context_length": 7}, [])
    api.search.assert_called_once_with("needle", 7)


def test_append_content_handler_validates_and_calls_api():
    handler = tools.AppendContentToolHandler()
    with pytest.raises(RuntimeError, match="filepath and content"):
        handler.run_tool({"filepath": "a.md"})

    result, api = _run_handler(handler, "append_content", {"filepath": "a.md", "content": "body"})
    api.append_content.assert_called_once_with("a.md", "body")
    assert _text(result) == "Successfully appended content to a.md"


def test_patch_content_handler_validates_and_calls_api():
    handler = tools.PatchContentToolHandler()
    with pytest.raises(RuntimeError, match="filepath, operation"):
        handler.run_tool({"filepath": "a.md"})

    args = {
        "filepath": "a.md",
        "operation": "append",
        "target_type": "heading",
        "target": "Title",
        "content": "body",
    }
    result, api = _run_handler(handler, "patch_content", args)
    api.patch_content.assert_called_once_with("a.md", "append", "heading", "Title", "body")
    assert _text(result) == "Successfully patched content in a.md"


def test_put_content_handler_validates_and_calls_api():
    handler = tools.PutContentToolHandler()
    with pytest.raises(RuntimeError, match="filepath and content"):
        handler.run_tool({"content": "body"})

    result, api = _run_handler(handler, "put_content", {"filepath": "a.md", "content": "body"})
    api.put_content.assert_called_once_with("a.md", "body")
    assert _text(result) == "Successfully uploaded content to a.md"


def test_delete_file_handler_requires_confirmation():
    handler = tools.DeleteFileToolHandler()
    with pytest.raises(RuntimeError, match="filepath"):
        handler.run_tool({})
    with pytest.raises(RuntimeError, match="confirm"):
        handler.run_tool({"filepath": "a.md", "confirm": False})

    result, api = _run_handler(handler, "delete_file", {"filepath": "a.md", "confirm": True})
    api.delete_file.assert_called_once_with("a.md")
    assert _text(result) == "Successfully deleted a.md"


def test_complex_search_handler_validates_and_returns_json():
    handler = tools.ComplexSearchToolHandler()
    query = {"glob": ["*.md", {"var": "path"}]}
    with pytest.raises(RuntimeError, match="query"):
        handler.run_tool({})

    result, api = _run_handler(handler, "search_json", {"query": query}, [{"filename": "a.md"}])
    api.search_json.assert_called_once_with(query)
    assert json.loads(_text(result)) == [{"filename": "a.md"}]


def test_search_by_tag_handler_validates_and_returns_paths():
    handler = tools.SearchByTagToolHandler()
    with pytest.raises(RuntimeError, match="tag"):
        handler.run_tool({})

    result, api = _run_handler(
        handler,
        "search_by_tag",
        {"tag": "project", "dirpath": "work"},
        ["work/a.md"],
    )
    api.search_by_tag.assert_called_once_with("project", "work")
    assert json.loads(_text(result)) == ["work/a.md"]


def test_get_frontmatter_handler_validates_and_returns_json():
    handler = tools.GetFrontmatterToolHandler()
    with pytest.raises(RuntimeError, match="filepath"):
        handler.run_tool({})

    result, api = _run_handler(handler, "get_frontmatter", {"filepath": "a.md"}, {"tags": ["x"]})
    api.get_frontmatter.assert_called_once_with("a.md")
    assert json.loads(_text(result)) == {"tags": ["x"]}


def test_batch_get_file_contents_handler_validates_and_returns_text():
    handler = tools.BatchGetFileContentsToolHandler()
    with pytest.raises(RuntimeError, match="filepaths"):
        handler.run_tool({})

    result, api = _run_handler(handler, "get_batch_file_contents", {"filepaths": ["a.md"]}, "# a.md")
    api.get_batch_file_contents.assert_called_once_with(["a.md"])
    assert _text(result) == "# a.md"


def test_periodic_notes_handler_validates_period_and_type():
    handler = tools.PeriodicNotesToolHandler()
    with pytest.raises(RuntimeError, match="period"):
        handler.run_tool({})
    with pytest.raises(RuntimeError, match="Invalid period"):
        handler.run_tool({"period": "hourly"})
    with pytest.raises(RuntimeError, match="Invalid type"):
        handler.run_tool({"period": "daily", "type": "summary"})

    result, api = _run_handler(handler, "get_periodic_note", {"period": "daily"}, "body")
    api.get_periodic_note.assert_called_once_with("daily", "content")
    assert _text(result) == "body"


def test_periodic_notes_handler_passes_metadata_type():
    handler = tools.PeriodicNotesToolHandler()
    _, api = _run_handler(handler, "get_periodic_note", {"period": "weekly", "type": "metadata"}, "{}")
    api.get_periodic_note.assert_called_once_with("weekly", "metadata")


def test_recent_periodic_notes_handler_validates_inputs():
    handler = tools.RecentPeriodicNotesToolHandler()
    with pytest.raises(RuntimeError, match="period"):
        handler.run_tool({})
    with pytest.raises(RuntimeError, match="Invalid period"):
        handler.run_tool({"period": "hourly"})
    with pytest.raises(RuntimeError, match="Invalid limit"):
        handler.run_tool({"period": "daily", "limit": 0})
    with pytest.raises(RuntimeError, match="Invalid include_content"):
        handler.run_tool({"period": "daily", "include_content": "yes"})

    result, api = _run_handler(
        handler,
        "get_recent_periodic_notes",
        {"period": "daily", "limit": 2, "include_content": True},
        [{"path": "d.md"}],
    )
    api.get_recent_periodic_notes.assert_called_once_with("daily", 2, True)
    assert json.loads(_text(result)) == [{"path": "d.md"}]


def test_recent_changes_handler_validates_inputs():
    handler = tools.RecentChangesToolHandler()
    with pytest.raises(RuntimeError, match="Invalid limit"):
        handler.run_tool({"limit": "10"})
    with pytest.raises(RuntimeError, match="Invalid days"):
        handler.run_tool({"days": 0})

    result, api = _run_handler(handler, "get_recent_changes", {"limit": 3, "days": 30}, [{"filename": "a.md"}])
    api.get_recent_changes.assert_called_once_with(3, 30)
    assert json.loads(_text(result)) == [{"filename": "a.md"}]


def test_recent_changes_handler_uses_defaults():
    handler = tools.RecentChangesToolHandler()
    _, api = _run_handler(handler, "get_recent_changes", {}, [])
    api.get_recent_changes.assert_called_once_with(10, 90)


# ---------------------------------------------------------------------------
# _validate_vault_path — security
# ---------------------------------------------------------------------------

def test_validate_vault_path_accepts_simple_path():
    assert tools._validate_vault_path("notes/a.md") == "notes/a.md"


def test_validate_vault_path_strips_leading_slash():
    assert tools._validate_vault_path("/notes/a.md") == "notes/a.md"


def test_validate_vault_path_rejects_dotdot_segment():
    with pytest.raises(RuntimeError, match=r"\.\."):
        tools._validate_vault_path("../secret.md")


def test_validate_vault_path_rejects_dotdot_in_middle():
    with pytest.raises(RuntimeError, match=r"\.\."):
        tools._validate_vault_path("notes/../../etc/passwd")


def test_validate_vault_path_rejects_backslash_traversal():
    with pytest.raises(RuntimeError, match=r"\.\."):
        tools._validate_vault_path("notes\\..\\secret.md")


# ---------------------------------------------------------------------------
# RenameFileToolHandler
# ---------------------------------------------------------------------------

def test_rename_file_handler_missing_args_raises():
    handler = tools.RenameFileToolHandler()
    with pytest.raises(RuntimeError, match="filepath and new_filepath"):
        handler.run_tool({})
    with pytest.raises(RuntimeError, match="filepath and new_filepath"):
        handler.run_tool({"filepath": "a.md"})
    with pytest.raises(RuntimeError, match="filepath and new_filepath"):
        handler.run_tool({"new_filepath": "b.md"})


def test_rename_file_handler_rejects_non_md_source():
    handler = tools.RenameFileToolHandler()
    with pytest.raises(RuntimeError, match="Only .md"):
        handler.run_tool({"filepath": "image.png", "new_filepath": "image2.png"})


def test_rename_file_handler_rejects_non_md_destination():
    handler = tools.RenameFileToolHandler()
    with pytest.raises(RuntimeError, match="Only .md"):
        handler.run_tool({"filepath": "a.md", "new_filepath": "b.txt"})


def test_rename_file_handler_rejects_path_traversal_in_source():
    handler = tools.RenameFileToolHandler()
    with pytest.raises(RuntimeError, match=r"\.\."):
        handler.run_tool({"filepath": "../../secret.md", "new_filepath": "b.md"})


def test_rename_file_handler_rejects_path_traversal_in_destination():
    handler = tools.RenameFileToolHandler()
    with pytest.raises(RuntimeError, match=r"\.\."):
        handler.run_tool({"filepath": "a.md", "new_filepath": "../outside.md"})


def test_rename_file_handler_happy_path():
    handler = tools.RenameFileToolHandler()
    result, api = _run_handler(handler, "rename_file", {"filepath": "a.md", "new_filepath": "b.md"})
    api.rename_file.assert_called_once_with("a.md", "b.md")
    assert "a.md" in _text(result) and "b.md" in _text(result)


def test_rename_file_handler_strips_leading_slash_before_calling_api():
    handler = tools.RenameFileToolHandler()
    _, api = _run_handler(handler, "rename_file", {"filepath": "/a.md", "new_filepath": "/sub/b.md"})
    api.rename_file.assert_called_once_with("a.md", "sub/b.md")
