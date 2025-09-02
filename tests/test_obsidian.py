"""Tests for the Obsidian API client."""
import pytest
import responses
from mcp_obsidian.obsidian import Obsidian

class TestObsidianClient:
    """Test the Obsidian API client."""
    
    def test_initialization(self):
        """Test Obsidian client initialization."""
        client = Obsidian(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.host == "127.0.0.1"
        assert client.port == 27124
        assert client.protocol == "https"
        
    def test_initialization_with_custom_values(self):
        """Test Obsidian client with custom configuration."""
        client = Obsidian(
            api_key="custom-key",
            protocol="http",
            host="localhost",
            port=8080
        )
        assert client.api_key == "custom-key"
        assert client.protocol == "http"
        assert client.host == "localhost"
        assert client.port == 8080
        
    def test_get_base_url(self):
        """Test base URL construction."""
        client = Obsidian(api_key="test-key")
        assert client.get_base_url() == "https://127.0.0.1:27124"
        
        client_http = Obsidian(api_key="test-key", protocol="http", port=8080)
        assert client_http.get_base_url() == "http://127.0.0.1:8080"
    
    def test_headers(self):
        """Test authorization headers."""
        client = Obsidian(api_key="test-key")
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer test-key"
    
    @responses.activate
    def test_list_files_in_vault(self):
        """Test listing files in vault."""
        client = Obsidian(api_key="test-key")
        expected_files = [
            {"path": "note1.md", "type": "file"},
            {"path": "folder1", "type": "directory"}
        ]
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/",
            json={"files": expected_files},
            status=200
        )
        
        files = client.list_files_in_vault()
        assert files == expected_files
        assert len(responses.calls) == 1
        
    @responses.activate
    def test_list_files_in_dir(self):
        """Test listing files in a specific directory."""
        client = Obsidian(api_key="test-key")
        expected_files = [
            {"path": "subfolder/note2.md", "type": "file"}
        ]
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/subfolder/",
            json={"files": expected_files},
            status=200
        )
        
        files = client.list_files_in_dir("subfolder")
        assert files == expected_files
        
    @responses.activate
    def test_get_file_contents(self):
        """Test getting file contents."""
        client = Obsidian(api_key="test-key")
        expected_content = "# Test Note\n\nThis is test content."
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/test.md",
            body=expected_content,
            status=200
        )
        
        content = client.get_file_contents("test.md")
        assert content == expected_content
        
    @responses.activate
    def test_batch_file_contents(self):
        """Test getting batch file contents."""
        client = Obsidian(api_key="test-key")
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/file1.md",
            body="Content of file 1",
            status=200
        )
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/file2.md",
            body="Content of file 2",
            status=200
        )
        
        result = client.get_batch_file_contents(["file1.md", "file2.md"])
        assert "# file1.md" in result
        assert "Content of file 1" in result
        assert "# file2.md" in result
        assert "Content of file 2" in result
        
    @responses.activate
    def test_batch_file_contents_with_error(self):
        """Test batch file contents with one file causing an error."""
        client = Obsidian(api_key="test-key")
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/file1.md",
            body="Content of file 1",
            status=200
        )
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/file2.md",
            status=404
        )
        
        result = client.get_batch_file_contents(["file1.md", "file2.md"])
        assert "Content of file 1" in result
        assert "Error reading file" in result
        
    @responses.activate
    def test_api_error_handling(self):
        """Test API error handling."""
        client = Obsidian(api_key="test-key")
        
        responses.add(
            responses.GET,
            "https://127.0.0.1:27124/vault/",
            json={"errorCode": 401, "message": "Unauthorized"},
            status=401
        )
        
        with pytest.raises(Exception) as exc_info:
            client.list_files_in_vault()
        assert "Error 401: Unauthorized" in str(exc_info.value)
        
    @responses.activate 
    def test_network_error_handling(self):
        """Test network error handling."""
        client = Obsidian(api_key="test-key")
        
        # Don't add any response to simulate network error
        with pytest.raises(Exception) as exc_info:
            client.list_files_in_vault()
        assert "Request failed" in str(exc_info.value)