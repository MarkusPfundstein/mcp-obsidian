"""Basic integration tests to ensure core functionality works before refactoring."""
import pytest
import os
from unittest.mock import patch, MagicMock
import json

# Prevent loading .env file during tests
with patch.dict(os.environ, {}, clear=True):
    os.environ["OBSIDIAN_API_KEY"] = "test-api-key"
    from mcp_obsidian.obsidian import Obsidian
    from mcp_obsidian import server
    from mcp_obsidian.tools import ListFilesInVaultToolHandler

class TestBasicFunctionality:
    """Test basic functionality to ensure nothing breaks during refactoring."""
    
    def test_obsidian_client_creation(self):
        """Test that we can create an Obsidian client."""
        client = Obsidian(api_key="test-key", host="localhost", port=8080)
        assert client.api_key == "test-key"
        assert client.host == "localhost"
        assert client.port == 8080
        
    def test_tool_handler_exists(self):
        """Test that tool handlers are registered."""
        assert "obsidian_list_files_in_vault" in server.tool_handlers
        assert "obsidian_get_file_contents" in server.tool_handlers
        assert "obsidian_simple_search" in server.tool_handlers
        
    @patch('mcp_obsidian.tools.obsidian.Obsidian')
    def test_simple_tool_execution(self, mock_obsidian_class):
        """Test that a simple tool can be executed."""
        # Setup mock
        mock_client = MagicMock()
        mock_obsidian_class.return_value = mock_client
        mock_client.list_files_in_vault.return_value = [
            {"path": "test.md", "type": "file"}
        ]
        
        # Execute tool
        handler = ListFilesInVaultToolHandler()
        result = handler.run_tool({})
        
        # Verify
        assert len(result) == 1
        assert result[0].type == "text"
        # The result should be JSON
        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert data[0]["path"] == "test.md"
    
    @pytest.mark.asyncio
    async def test_server_list_tools(self):
        """Test that server can list tools."""
        tools = await server.list_tools()
        assert len(tools) > 0
        # Check that tools have required properties
        for tool in tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
    
    def test_environment_configuration(self):
        """Test that environment variables are properly used."""
        with patch.dict(os.environ, {
            "OBSIDIAN_API_KEY": "env-key",
            "OBSIDIAN_HOST": "env-host",
            "OBSIDIAN_PORT": "9999",
            "OBSIDIAN_PROTOCOL": "http"
        }):
            client = Obsidian(
                api_key="env-key",
                host=os.getenv("OBSIDIAN_HOST", "127.0.0.1"),
                port=int(os.getenv("OBSIDIAN_PORT", "27124")),
                protocol=os.getenv("OBSIDIAN_PROTOCOL", "https")
            )
            assert client.host == "env-host"
            assert client.port == 9999
            assert client.protocol == "http"