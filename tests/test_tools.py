"""Tests for tool handlers."""
import pytest
import json
from unittest.mock import MagicMock, patch
from mcp_obsidian.tools import (
    ListFilesInVaultToolHandler,
    ListFilesInDirToolHandler,
    GetFileContentsToolHandler,
    SearchToolHandler,
    AppendContentToolHandler,
    DeleteFileToolHandler
)

class TestListFilesInVaultToolHandler:
    """Test the ListFilesInVaultToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = ListFilesInVaultToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_list_files_in_vault"
        assert "vault" in tool.description.lower()
        assert tool.inputSchema["required"] == []
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool(self, mock_obsidian_class):
        """Test running the list files in vault tool."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.list_files_in_vault.return_value = [
            {"path": "file1.md", "type": "file"},
            {"path": "folder1", "type": "directory"}
        ]
        
        handler = ListFilesInVaultToolHandler()
        result = handler.run_tool({})
        
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert len(data) == 2
        assert data[0]["path"] == "file1.md"

class TestListFilesInDirToolHandler:
    """Test the ListFilesInDirToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = ListFilesInDirToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_list_files_in_dir"
        assert "directory" in tool.description.lower()
        assert "dirpath" in tool.inputSchema["required"]
        
    def test_run_tool_missing_dirpath(self):
        """Test running tool without required dirpath."""
        handler = ListFilesInDirToolHandler()
        
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({})
        assert "dirpath argument missing" in str(exc_info.value)
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool_with_dirpath(self, mock_obsidian_class):
        """Test running the list files in dir tool."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.list_files_in_dir.return_value = [
            {"path": "subfolder/file2.md", "type": "file"}
        ]
        
        handler = ListFilesInDirToolHandler()
        result = handler.run_tool({"dirpath": "subfolder"})
        
        mock_client.list_files_in_dir.assert_called_once_with("subfolder")
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data[0]["path"] == "subfolder/file2.md"

class TestGetFileContentsToolHandler:
    """Test the GetFileContentsToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = GetFileContentsToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_get_file_contents"
        assert "filepath" in tool.inputSchema["required"]
        
    def test_run_tool_missing_filepath(self):
        """Test running tool without required filepath."""
        handler = GetFileContentsToolHandler()
        
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({})
        assert "filepath argument missing" in str(exc_info.value)
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool_with_filepath(self, mock_obsidian_class):
        """Test getting file contents."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.get_file_contents.return_value = "# Test Content\n\nThis is a test."
        
        handler = GetFileContentsToolHandler()
        result = handler.run_tool({"filepath": "test.md"})
        
        mock_client.get_file_contents.assert_called_once_with("test.md")
        assert len(result) == 1
        assert result[0].text == "# Test Content\n\nThis is a test."

class TestSearchToolHandler:
    """Test the SearchToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = SearchToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_search"
        assert "search" in tool.description.lower()
        assert "query" in tool.inputSchema["required"]
        
    def test_run_tool_missing_query(self):
        """Test running tool without required query."""
        handler = SearchToolHandler()
        
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({})
        assert "query argument missing" in str(exc_info.value)
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool_with_query(self, mock_obsidian_class):
        """Test searching with query."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.search.return_value = [
            {
                "filename": "note1.md",
                "matches": [{"match": {"text": "found text"}, "line": 5}]
            }
        ]
        
        handler = SearchToolHandler()
        result = handler.run_tool({"query": "test query"})
        
        mock_client.search.assert_called_once_with("test query")
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data[0]["filename"] == "note1.md"

class TestAppendContentToolHandler:
    """Test the AppendContentToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = AppendContentToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_append_content"
        assert "append" in tool.description.lower()
        assert "filepath" in tool.inputSchema["required"]
        assert "content" in tool.inputSchema["required"]
        
    def test_run_tool_missing_args(self):
        """Test running tool without required arguments."""
        handler = AppendContentToolHandler()
        
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({})
        assert "filepath argument missing" in str(exc_info.value)
        
        with pytest.raises(RuntimeError) as exc_info:
            handler.run_tool({"filepath": "test.md"})
        assert "content argument missing" in str(exc_info.value)
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool_with_args(self, mock_obsidian_class):
        """Test appending content."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.append_content.return_value = {"message": "Content appended"}
        
        handler = AppendContentToolHandler()
        result = handler.run_tool({
            "filepath": "test.md",
            "content": "New content to append"
        })
        
        mock_client.append_content.assert_called_once_with(
            "test.md", 
            "New content to append"
        )
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["message"] == "Content appended"

class TestDeleteFileToolHandler:
    """Test the DeleteFileToolHandler."""
    
    def test_tool_description(self):
        """Test tool description."""
        handler = DeleteFileToolHandler()
        tool = handler.get_tool_description()
        
        assert tool.name == "obsidian_delete_file"
        assert "delete" in tool.description.lower()
        assert "filepath" in tool.inputSchema["required"]
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_run_tool_with_filepath(self, mock_obsidian_class):
        """Test deleting a file."""
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.delete_file.return_value = {"message": "File deleted"}
        
        handler = DeleteFileToolHandler()
        result = handler.run_tool({"filepath": "test.md"})
        
        mock_client.delete_file.assert_called_once_with("test.md")
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["message"] == "File deleted"