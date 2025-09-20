#!/usr/bin/env python3
"""Quick test script to validate Junior setup."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test all critical imports."""
    print("🧪 Testing imports...")
    
    try:
        from junior.app import app
        print("✅ FastAPI app import")
        
        from junior.agent import LogicalReviewAgent, ReviewFinding
        print("✅ Review agent import")
        
        from junior.services import GitHubClient
        print("✅ GitHub client import")
        
        from junior.services import WebhookProcessor, PullRequestWebhookPayload
        print("✅ Webhook handler import")
        
        from junior.agent import RepositoryAnalyzer
        print("✅ Repository analyzer import")
        
        from junior.config import settings
        print("✅ Configuration import")
        
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_models():
    """Test data models."""
    print("\n🧪 Testing data models...")
    
    try:
        from junior.agent import ReviewFinding
        
        finding = ReviewFinding(
            category="logic",
            severity="high", 
            message="Test finding",
            file_path="test.py",
            line_number=42
        )
        
        print(f"✅ ReviewFinding: {finding.message}")
        return True
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False

def test_webhook():
    """Test webhook processing."""
    print("\n🧪 Testing webhook processing...")
    
    try:
        from junior.services import WebhookProcessor, PullRequestWebhookPayload
        
        # Sample GitHub webhook payload
        sample_payload = {
            'action': 'opened',
            'number': 123,
            'pull_request': {
                'title': 'Test PR',
                'body': 'This fixes #456',
                'state': 'open',
                'draft': False,
                'user': {'login': 'testuser', 'id': 123},
                'base': {'ref': 'main', 'sha': 'abc123'},
                'head': {'ref': 'feature', 'sha': 'def456'},
                'html_url': 'https://github.com/test/repo/pull/123',
                'issue_url': 'https://github.com/test/repo/issues/123',
                'diff_url': 'https://github.com/test/repo/pull/123.diff',
                'patch_url': 'https://github.com/test/repo/pull/123.patch',
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-01T00:00:00Z',
                'additions': 10,
                'deletions': 5,
                'changed_files': 3
            },
            'repository': {
                'full_name': 'test/repo',
                'clone_url': 'https://github.com/test/repo.git',
                'ssh_url': 'git@github.com:test/repo.git',
                'default_branch': 'main',
                'language': 'Python',
                'private': False,
                'description': 'Test repository'
            },
            'sender': {'login': 'testuser'}
        }
        
        processor = WebhookProcessor()
        webhook_payload = PullRequestWebhookPayload(**sample_payload)
        should_process = processor.should_process_event(webhook_payload)
        review_data = processor.extract_review_data(webhook_payload)
        
        print(f"✅ Webhook processing: {review_data['repository']}")
        print(f"✅ Should process: {should_process}")
        print(f"✅ PR number: {review_data['pr_number']}")
        
        return True
    except Exception as e:
        print(f"❌ Webhook test failed: {e}")
        return False

def test_config():
    """Test configuration."""
    print("\n🧪 Testing configuration...")
    
    try:
        from junior.config import settings
        
        print(f"✅ AI Model: {settings.default_model}")
        print(f"✅ Temperature: {settings.temperature}")
        print(f"✅ Max Tokens: {settings.max_tokens}")
        print(f"✅ API Port: {settings.api_port}")
        print(f"✅ Log Level: {settings.log_level}")
        
        return True
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Junior AI Code Review Agent - Quick Test\n")
    
    tests = [
        test_imports,
        test_models, 
        test_webhook,
        test_config
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Junior is ready to review PRs.")
        print("\nNext steps:")
        print("1. Set environment variables (GITHUB_TOKEN, OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        print("2. Run: uv run junior webhook-server --port 8000")
        print("3. Configure GitHub webhook to point to your server")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())