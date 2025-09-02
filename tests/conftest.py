"""Shared fixtures for tests."""
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Check for .env file and fail fast if it exists
def check_no_env_file():
    """Ensure no .env file exists during testing to prevent configuration conflicts."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        pytest.exit(
            "\n"
            "ERROR: .env file detected in project root.\n"
            "Tests require a clean environment without .env file to ensure proper isolation.\n"
            "Please remove or rename the .env file before running tests.\n"
            f"File location: {env_file}\n",
            returncode=1
        )

# Run the check when tests are collected
check_no_env_file()

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Automatically set required environment variables for all tests."""
    # Clear any existing env vars first
    for key in ["OBSIDIAN_API_KEY", "OBSIDIAN_HOST", "OBSIDIAN_PORT", "OBSIDIAN_PROTOCOL"]:
        monkeypatch.delenv(key, raising=False)
    
    # Set test values
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-api-key")
    monkeypatch.setenv("OBSIDIAN_HOST", "127.0.0.1")
    monkeypatch.setenv("OBSIDIAN_PORT", "27124")
    monkeypatch.setenv("OBSIDIAN_PROTOCOL", "https")

@pytest.fixture
def mock_obsidian_api():
    """Fixture for mocking Obsidian API responses."""
    import responses
    with responses.RequestsMock() as rsps:
        yield rsps

@pytest.fixture
def sample_vault_files():
    """Sample vault file structure for testing."""
    return {
        "files": [
            {"path": "notes/daily/2024-01-01.md", "type": "file"},
            {"path": "notes/daily/2024-01-02.md", "type": "file"},
            {"path": "notes/meetings", "type": "directory"},
            {"path": "notes/meetings/team-standup.md", "type": "file"},
            {"path": "projects/project-a.md", "type": "file"},
        ]
    }

@pytest.fixture
def sample_file_content():
    """Sample file content for testing."""
    return """# Test Note

## Section 1
This is a test note with some content.

## Section 2
- Item 1
- Item 2
- Item 3

## Tags
#test #sample #markdown
"""

@pytest.fixture
def sample_search_results():
    """Sample search results for testing."""
    return [
        {
            "filename": "notes/daily/2024-01-01.md",
            "matches": [
                {"match": {"text": "meeting with team about project"}, "line": 5}
            ]
        },
        {
            "filename": "projects/project-a.md", 
            "matches": [
                {"match": {"text": "project kickoff scheduled"}, "line": 10}
            ]
        }
    ]