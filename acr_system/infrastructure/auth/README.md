# GitHub App Authentication

This module implements JWT-based authentication for GitHub Apps according to [GitHub's documentation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app).

## Overview

GitHub App authentication flow:
1. **Generate JWT** from private key (.pem file) - valid for 10 minutes
2. **Exchange JWT for installation token** - valid for 1 hour
3. **Use installation token** for API requests
4. **Auto-refresh** token before expiry

## Setup

### 1. Create GitHub App

1. Go to GitHub Settings → Developer settings → GitHub Apps
2. Click "New GitHub App"
3. Configure:
   - **Webhook URL**: Your application webhook endpoint
   - **Permissions**: Choose required permissions (e.g., Pull requests: Read & write)
   - **Events**: Subscribe to events (e.g., Pull request)
4. Generate private key (.pem file) - **Download and save securely**
5. Note your **App ID**

### 2. Install GitHub App

1. Install the app to your organization/repositories
2. Note the **Installation ID** from the URL: `https://github.com/settings/installations/{installation_id}`

### 3. Configure Environment

```bash
# .env
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678  # Optional
```

## Usage

### Basic Usage

```python
from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.vcs.github_adapter import GitHubAdapter

# Initialize auth
auth = GitHubAppAuth(
    app_id="123456",
    private_key_path="./github-app-private-key.pem",
    installation_id="12345678",  # Optional
)

# Use with GitHub adapter
github = GitHubAdapter(auth=auth)

# Fetch PR
pr = await github.get_pull_request("owner/repo", 123)
```

### Shared Auth Instance

```python
# Create one auth instance and share across adapters
auth = GitHubAppAuth(
    app_id=os.getenv("GITHUB_APP_ID"),
    private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
    installation_id=os.getenv("GITHUB_APP_INSTALLATION_ID"),
)

# Share auth
github_vcs = GitHubAdapter(auth=auth)
github_checks = GitHubChecksAdapter(auth=auth)
```

### Auto-detect Installation ID

If you don't know the installation ID:

```python
auth = GitHubAppAuth(
    app_id="123456",
    private_key_path="./github-app-private-key.pem",
)

# Auto-detect installation ID for specific repo
installation_id = await auth.get_installation_id_for_repo("owner/repo")
print(f"Installation ID: {installation_id}")
```

### Manual Token Management

```python
# Get installation token directly
token = await auth.get_installation_token()

# Token is cached and auto-refreshed
# Force refresh by calling again after expiry
```

## Permissions

Configure GitHub App permissions based on your needs:

### Minimal Permissions for ACR System:
- **Pull requests**: Read & write (to read PRs and post review comments)
- **Contents**: Read (to read file contents)
- **Checks**: Read (to read CI/CD results)
- **Metadata**: Read (mandatory)

### Webhook Events:
- **Pull request** - opened, synchronize, reopened

## Security Best Practices

1. **Store private key securely**:
   - Never commit .pem file to version control
   - Use environment variables or secrets manager
   - Restrict file permissions: `chmod 600 github-app-private-key.pem`

2. **Rotate keys regularly**:
   - Generate new private key in GitHub App settings
   - Update deployment with new key
   - Revoke old key after transition

3. **Limit permissions**:
   - Only request necessary permissions
   - Use installation-level permissions when possible

4. **Monitor usage**:
   - Check GitHub App logs for suspicious activity
   - Set up rate limit monitoring

## Token Caching

The module automatically caches installation tokens:
- **Cache duration**: 55 minutes (refreshes 5 minutes before expiry)
- **Thread-safe**: Tokens are cached per GitHubAppAuth instance
- **Auto-refresh**: Transparently refreshes expired tokens

## Troubleshooting

### "PyJWT is required" error

```bash
pip install "PyJWT[crypto]>=2.8.0"
```

### "Private key not found" error

Check:
1. Path is correct: `GITHUB_APP_PRIVATE_KEY_PATH`
2. File exists and is readable
3. File permissions: `ls -la github-app-private-key.pem`

### "Failed to get installation token" error

Check:
1. App ID is correct
2. Installation ID is correct (or try auto-detect)
3. Private key matches the GitHub App
4. App is installed on the target repository
5. App has necessary permissions

### Rate Limits

GitHub API rate limits:
- **Authenticated requests**: 5,000 per hour per installation
- **JWT requests**: 5,000 per hour per app

Monitor with response headers:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## Testing

### Mock for Unit Tests

```python
from unittest.mock import AsyncMock, MagicMock

# Mock auth
mock_auth = MagicMock(spec=GitHubAppAuth)
mock_auth.get_auth_headers = AsyncMock(return_value={
    "Authorization": "Bearer fake-token",
    "Accept": "application/vnd.github+json",
})

# Use in tests
adapter = GitHubAdapter(auth=mock_auth)
```

### Integration Tests

Use real credentials in integration tests:

```python
@pytest.mark.integration
async def test_github_auth_integration():
    auth = GitHubAppAuth(
        app_id=os.getenv("GITHUB_APP_ID"),
        private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
    )
    
    token = await auth.get_installation_token("12345678")
    assert token.startswith("ghs_")
```

## References

- [GitHub Apps Documentation](https://docs.github.com/en/apps)
- [JWT Authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)
- [Installation Tokens](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app)
- [Permissions Reference](https://docs.github.com/en/rest/overview/permissions-required-for-github-apps)
