#!/usr/bin/env python3
"""
Test the encoding logic for patch_content
"""
import urllib.parse

def test_target_encoding():
    """Test the new encoding logic"""
    
    test_cases = [
        ("## Simple Heading", "## Simple Heading"),  # ASCII - no encoding
        ("## 🔍 Unicode Test", "##%20%F0%9F%94%8D%20Unicode%20Test"),  # Unicode - encoded
        ("status", "status"),  # Simple field - no encoding
        ("simple-block", "simple-block"),  # Block ID - no encoding
    ]
    
    print("Testing target encoding logic:")
    print("=" * 50)
    
    for original, expected in test_cases:
        # Apply our encoding logic
        try:
            original.encode('ascii')
            # Target is pure ASCII, use as-is
            final_target = original
        except UnicodeEncodeError:
            # Target contains non-ASCII characters, URL encode it
            final_target = urllib.parse.quote(original, safe='')
        
        print(f"Original: {original}")
        print(f"Expected: {expected}")
        print(f"Got:      {final_target}")
        print(f"Match:    {final_target == expected}")
        print("-" * 30)

if __name__ == "__main__":
    test_target_encoding()
