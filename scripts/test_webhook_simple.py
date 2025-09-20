#!/usr/bin/env python3
"""Simple webhook test with realistic PR data."""

import asyncio
import json
import sys
import httpx
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Simple GitHub PR webhook payload for testing
WEBHOOK_PAYLOAD = {
    "action": "opened",
    "number": 456,
    "pull_request": {
        "id": 456,
        "number": 456,
        "title": "Fix authentication bug",
        "body": "This PR fixes a critical authentication bypass issue found in #123",
        "state": "open",
        "draft": False,
        "user": {"login": "security-dev", "id": 67890},
        "base": {"ref": "main", "sha": "main123"},
        "head": {"ref": "security/fix-auth", "sha": "fix456"},
        "html_url": "https://github.com/myorg/myapp/pull/456",
        "issue_url": "https://api.github.com/repos/myorg/myapp/issues/456",
        "diff_url": "https://api.github.com/repos/myorg/myapp/pulls/456.diff",
        "patch_url": "https://api.github.com/repos/myorg/myapp/pulls/456.patch",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
        "additions": 25,
        "deletions": 8,
        "changed_files": 2
    },
    "repository": {
        "id": 789,
        "name": "myapp",
        "full_name": "myorg/myapp",
        "private": True,
        "clone_url": "https://github.com/myorg/myapp.git",
        "ssh_url": "git@github.com:myorg/myapp.git",
        "default_branch": "main",
        "language": "Python",
        "description": "Production web application"
    },
    "sender": {"login": "security-dev", "id": 67890}
}


async def test_webhook_endpoint(port=8000):
    """Test the webhook endpoint with a realistic payload."""
    print("🧪 Testing webhook endpoint with realistic PR data...")
    
    webhook_url = f"http://127.0.0.1:{port}/webhook/github"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json=WEBHOOK_PAYLOAD,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "User-Agent": "GitHub-Hookshot/test",
                    # Note: No X-Hub-Signature-256 header for testing without secret
                }
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Webhook accepted successfully!")
                print(f"   Repository: {result.get('repository', 'N/A')}")
                print(f"   PR Number: {result.get('pr_number', 'N/A')}")
                print(f"   Action: {result.get('action', 'N/A')}")
                return True
            else:
                print(f"❌ Unexpected status: {response.status_code}")
                return False
                
    except httpx.ConnectError:
        print("❌ Connection failed - is the webhook server running?")
        print(f"   Start it with: uv run junior webhook-server --port {port}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_health_endpoints(port=8000):
    """Test health and readiness endpoints."""
    print("\n🏥 Testing health endpoints...")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test health endpoint
            health_response = await client.get(f"http://127.0.0.1:{port}/health")
            print(f"Health: {health_response.status_code} - {health_response.text}")
            
            # Test readiness endpoint
            ready_response = await client.get(f"http://127.0.0.1:{port}/ready")
            print(f"Ready: {ready_response.status_code} - {ready_response.text}")
            
            return health_response.status_code == 200
            
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def test_data_models():
    """Test that webhook data can be parsed."""
    print("\n📋 Testing data model parsing...")
    
    try:
        from junior.webhook import PullRequestWebhookPayload, WebhookProcessor
        
        # Test payload parsing
        webhook_payload = PullRequestWebhookPayload(**WEBHOOK_PAYLOAD)
        print(f"✅ Payload parsed: PR #{webhook_payload.number} by {webhook_payload.pull_request['user']['login']}")
        
        # Test data extraction
        processor = WebhookProcessor()
        review_data = processor.extract_review_data(webhook_payload)
        print(f"✅ Data extracted: {review_data['repository']} - {len(review_data['linked_issues'])} linked issues")
        
        return True
        
    except Exception as e:
        print(f"❌ Data model test failed: {e}")
        return False


async def main():
    """Run simple webhook tests."""
    print("🚀 Junior Webhook Simple Test\n")
    
    # Get port from command line argument
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}, using default 8000")
    
    print(f"Testing against server on port {port}\n")
    
    # Test 1: Data models (no server needed)
    models_ok = test_data_models()
    
    # Test 2: Health endpoints (requires running server)
    health_ok = await test_health_endpoints(port)
    
    # Test 3: Webhook endpoint (requires running server) 
    webhook_ok = await test_webhook_endpoint(port)
    
    # Summary
    tests = {"Data Models": models_ok, "Health Endpoints": health_ok, "Webhook": webhook_ok}
    passed = sum(tests.values())
    total = len(tests)
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    for test_name, result in tests.items():
        status = "✅" if result else "❌"
        print(f"  {status} {test_name}")
    
    if passed == total:
        print("\n🎉 All tests passed! Webhook server is working correctly.")
    elif models_ok and not health_ok:
        print("\n⚠️  Server not running. Start with: uv run junior webhook-server")
    else:
        print("\n❌ Some tests failed. Check the errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)