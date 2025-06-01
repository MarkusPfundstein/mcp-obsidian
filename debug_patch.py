#!/usr/bin/env python3
"""
Debug script to test patch_content functionality directly
"""
import os
import sys
import requests
import urllib.parse
from src.mcp_obsidian.obsidian import Obsidian

def test_patch_content():
    api_key = os.getenv("OBSIDIAN_API_KEY", "")
    if not api_key:
        print("OBSIDIAN_API_KEY environment variable required")
        return
    
    # Create test content first
    test_file = "patch_test.md"
    test_content = """---
status: testing
priority: high
---

# Patch Test File

## Simple Heading

This is a test paragraph for patch functionality.

Some more content here. ^simple-block

## 🔍 Unicode Test Section

This section has emoji in the heading.

More content with a block reference. ^emoji-block
"""
    
    api = Obsidian(api_key=api_key)
    
    # First create the test file
    print("Creating test file...")
    try:
        api.append_content(test_file, test_content)
        print(f"✅ Created {test_file}")
    except Exception as e:
        print(f"❌ Failed to create test file: {e}")
        return
    
    # Test different patch scenarios
    test_cases = [
        {
            "name": "Test 1: Simple heading patch",
            "operation": "append",
            "target_type": "heading", 
            "target": "## Simple Heading",
            "content": "\n\nThis content was added via patch!"
        },
        {
            "name": "Test 2: Unicode heading patch",
            "operation": "append",
            "target_type": "heading",
            "target": "## 🔍 Unicode Test Section", 
            "content": "\n\nThis was added to the emoji heading!"
        },
        {
            "name": "Test 3: Frontmatter patch",
            "operation": "replace",
            "target_type": "frontmatter",
            "target": "status",
            "content": "debugging"
        },
        {
            "name": "Test 4: Block reference patch",
            "operation": "append",
            "target_type": "block",
            "target": "simple-block",
            "content": "\n\nContent added after simple block!"
        },
        {
            "name": "Test 5: Unicode block reference patch",
            "operation": "append", 
            "target_type": "block",
            "target": "emoji-block",
            "content": "\n\nContent added after emoji block!"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{test_case['name']}")
        try:
            api.patch_content(
                test_file,
                test_case["operation"],
                test_case["target_type"], 
                test_case["target"],
                test_case["content"]
            )
            print(f"✅ Success: {test_case['name']}")
        except Exception as e:
            print(f"❌ Failed: {test_case['name']} - {e}")
    
    # Show final content
    print(f"\n📄 Final content of {test_file}:")
    try:
        final_content = api.get_file_contents(test_file)
        print(final_content)
    except Exception as e:
        print(f"❌ Failed to read final content: {e}")

if __name__ == "__main__":
    test_patch_content()
