#!/usr/bin/env python3
"""
Standalone debug script for testing GitHub integration.
Set breakpoints in VSCode and run this file directly.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from junior.github_client import GitHubClient


async def debug_test_post_review_comment():
    """Debug version of the integration test."""

    # BREAKPOINT 1: Check environment
    print("=== Debug Test Starting ===")
    token = os.getenv("GITHUB_TOKEN")
    print(f"Token exists: {bool(token)}")
    print(f"Token length: {len(token) if token else 0}")

    # Test configuration
    repository = "mishachepi/junior"
    pr_number = 1
    body = f"Debug test comment - {os.urandom(4).hex()}"

    print(f"\nRepository: {repository}")
    print(f"PR Number: {pr_number}")
    print(f"Comment: {body}")

    # BREAKPOINT 2: Create client
    print("\n--- Creating GitHub Client ---")
    github_client = GitHubClient()
    print("Client created successfully")

    try:
        # BREAKPOINT 3: Fetch PR info
        print("\n--- Fetching PR Info ---")
        pr_info = await github_client.get_pull_request(repository, pr_number)
        print(f"PR Title: {pr_info.get('title')}")
        print(f"PR State: {pr_info.get('state')}")
        print(f"PR Author: {pr_info.get('user', {}).get('login')}")

        # BREAKPOINT 4: Post comment
        print("\n--- Posting Comment ---")
        response = await github_client.post_review_comment(
            repository=repository,
            pr_number=pr_number,
            body=body,
        )

        # BREAKPOINT 5: Check response
        print("\n--- Response Details ---")
        print(f"Comment ID: {response.get('id')}")
        print(f"Comment Body: {response.get('body')}")
        print(f"Created At: {response.get('created_at')}")

        # Verify
        assert response.get("body") == body
        print("\n✅ Test PASSED!")

    except Exception as e:
        print(f"\n❌ Test FAILED!")
        print(f"Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    print("Starting debug script...")
    print("You can set breakpoints at lines marked with 'BREAKPOINT' comments")
    print("-" * 50)

    result = asyncio.run(debug_test_post_review_comment())

    if result:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n😞 Test failed!")
        sys.exit(1)