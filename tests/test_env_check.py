"""Test that verifies .env detection works correctly.
This test is somewhat meta - it tests the test infrastructure itself.
"""
import subprocess
import tempfile
from pathlib import Path
import sys

def test_env_file_detection():
    """Verify that tests fail when .env file is present."""
    # Create a temporary .env file
    env_file = Path(__file__).parent.parent / ".env"
    
    # Skip if .env already exists (shouldn't happen in CI)
    if env_file.exists():
        return  # Skip test if .env exists
    
    try:
        # Create .env file
        env_file.write_text("OBSIDIAN_API_KEY=test\n")
        
        # Try to run a simple test
        result = subprocess.run(
            [sys.executable, "-m", "pytest", __file__, "-k", "dummy_test"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent)
        )
        
        # Should fail with our custom error message
        assert result.returncode != 0
        assert "ERROR: .env file detected in project root" in result.stderr
        assert "Tests require a clean environment" in result.stderr
        
    finally:
        # Clean up
        if env_file.exists():
            env_file.unlink()

def test_dummy_test():
    """A dummy test that should pass when no .env exists."""
    assert True