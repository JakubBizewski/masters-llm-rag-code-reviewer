#!/usr/bin/env python3
"""Example script demonstrating GitHub App JWT authentication.

This script shows how to:
1. Initialize GitHubAppAuth with private key
2. Use it with GitHub adapters
3. Handle token refresh automatically
"""
import asyncio
import os
from pathlib import Path

from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter
from acr_system.infrastructure.vcs.github_adapter import GitHubAdapter


async def main():
    """Main example function."""
    # Load credentials from environment
    app_id = os.getenv("GITHUB_APP_ID")
    private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
    
    if not app_id or not private_key_path:
        print("Error: GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH must be set")
        print("\nExample:")
        print("  export GITHUB_APP_ID=123456")
        print("  export GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem")
        print("  export GITHUB_APP_INSTALLATION_ID=12345678  # Optional")
        return
    
    print("=" * 60)
    print("GitHub App JWT Authentication Example")
    print("=" * 60)
    
    # 1. Initialize auth
    print("\n1. Initializing GitHubAppAuth...")
    auth = GitHubAppAuth(
        app_id=app_id,
        private_key_path=private_key_path,
        installation_id=installation_id,
    )
    print(f"   ✓ App ID: {app_id}")
    print(f"   ✓ Private key loaded from: {private_key_path}")
    
    # 2. Auto-detect installation ID if not provided
    if not installation_id:
        print("\n2. Auto-detecting installation ID...")
        repo = input("   Enter repository (owner/repo): ")
        try:
            installation_id = await auth.get_installation_id_for_repo(repo)
            print(f"   ✓ Installation ID: {installation_id}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return
    else:
        print(f"\n2. Using installation ID: {installation_id}")
    
    # 3. Get installation token
    print("\n3. Fetching installation token...")
    try:
        token = await auth.get_installation_token()
        print(f"   ✓ Token obtained: {token[:20]}...")
        print(f"   ✓ Token expires at: {auth._token_expires_at}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    # 4. Use with GitHub VCS adapter
    print("\n4. Testing GitHub VCS Adapter...")
    github_vcs = GitHubAdapter(auth=auth)
    
    repo = input("   Enter repository to test (owner/repo): ")
    pr_number = input("   Enter PR number: ")
    
    try:
        pr = await github_vcs.get_pull_request(repo, int(pr_number))
        print(f"   ✓ PR fetched: #{pr.pr_number} - {pr.title}")
        print(f"     Author: {pr.author}")
        print(f"     Branch: {pr.source_branch} → {pr.target_branch}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # 5. Use with GitHub Checks adapter
    print("\n5. Testing GitHub Checks Adapter...")
    github_checks = GitHubChecksAdapter(auth=auth)
    
    try:
        ci_results = await github_checks.fetch_ci_results(repo, int(pr_number))
        print(f"   ✓ Found {len(ci_results)} CI results:")
        for result in ci_results:
            print(f"     - {result.tool_name}: {result.status}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # 6. Token caching demonstration
    print("\n6. Demonstrating token caching...")
    print("   Making second request (should use cached token)...")
    try:
        headers = await auth.get_auth_headers()
        print("   ✓ Auth headers obtained from cache")
        print(f"     Authorization: {headers['Authorization'][:30]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Cleanup
    await github_vcs.close()
    await github_checks.close()
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
