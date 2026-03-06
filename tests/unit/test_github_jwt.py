"""Tests for GitHub App JWT authentication."""
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.shared.exceptions.infrastructure_exceptions import VCSAPIError


@pytest.fixture
def mock_private_key(tmp_path):
    """Create a mock private key file."""
    key_file = tmp_path / "test-key.pem"
    key_file.write_text("""-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8yvhJj/QKpnJVGQA1aEzkYLT7Ds
-----END RSA PRIVATE KEY-----""")
    return str(key_file)


@pytest.fixture
def github_app_auth(mock_private_key):
    """Create GitHubAppAuth instance."""
    return GitHubAppAuth(
        app_id="123456",
        private_key_path=mock_private_key,
        installation_id="12345678",
    )


class TestGitHubAppAuth:
    """Tests for GitHubAppAuth class."""
    
    def test_init_with_valid_key(self, mock_private_key):
        """Test initialization with valid private key."""
        auth = GitHubAppAuth(
            app_id="123456",
            private_key_path=mock_private_key,
            installation_id="12345678",
        )
        
        assert auth.app_id == "123456"
        assert auth.installation_id == "12345678"
        assert auth.private_key is not None
        assert auth._installation_token is None
    
    def test_init_without_jwt_raises_error(self, mock_private_key):
        """Test that missing PyJWT raises ImportError."""
        with patch("acr_system.infrastructure.auth.github_jwt.JWT_AVAILABLE", False):
            with pytest.raises(ImportError, match="PyJWT is required"):
                GitHubAppAuth(
                    app_id="123456",
                    private_key_path=mock_private_key,
                )
    
    def test_init_invalid_key_path_raises_error(self):
        """Test that invalid key path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            GitHubAppAuth(
                app_id="123456",
                private_key_path="/nonexistent/key.pem",
            )
    
    @patch("acr_system.infrastructure.auth.github_jwt.jwt")
    def test_generate_jwt(self, mock_jwt, github_app_auth):
        """Test JWT generation."""
        mock_jwt.encode.return_value = "fake-jwt-token"
        
        token = github_app_auth.generate_jwt()
        
        assert token == "fake-jwt-token"
        mock_jwt.encode.assert_called_once()
        
        # Check payload
        call_args = mock_jwt.encode.call_args
        payload = call_args[0][0]
        
        assert payload["iss"] == "123456"
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] - payload["iat"] == 600  # 10 minutes
    
    @pytest.mark.asyncio
    async def test_get_installation_token_success(self, github_app_auth):
        """Test getting installation token successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "ghs_test_token",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat() + "Z",
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(github_app_auth, "generate_jwt", return_value="fake-jwt"):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client
                
                token = await github_app_auth.get_installation_token()
                
                assert token == "ghs_test_token"
                assert github_app_auth._installation_token == "ghs_test_token"
                assert github_app_auth._token_expires_at is not None
    
    @pytest.mark.asyncio
    async def test_get_installation_token_uses_cache(self, github_app_auth):
        """Test that cached token is reused."""
        # Set cached token
        github_app_auth._installation_token = "cached-token"
        github_app_auth._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        # Should return cached token without API call
        token = await github_app_auth.get_installation_token()
        
        assert token == "cached-token"
    
    @pytest.mark.asyncio
    async def test_get_installation_token_refreshes_expired(self, github_app_auth):
        """Test that expired token is refreshed."""
        # Set expired token
        github_app_auth._installation_token = "expired-token"
        github_app_auth._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "ghs_new_token",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(github_app_auth, "generate_jwt", return_value="fake-jwt"):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client
                
                token = await github_app_auth.get_installation_token()
                
                assert token == "ghs_new_token"
    
    @pytest.mark.asyncio
    async def test_get_installation_token_no_installation_id_raises_error(
        self, mock_private_key
    ):
        """Test that missing installation ID raises error."""
        auth = GitHubAppAuth(
            app_id="123456",
            private_key_path=mock_private_key,
        )
        
        with pytest.raises(VCSAPIError, match="Installation ID not provided"):
            await auth.get_installation_token()
    
    @pytest.mark.asyncio
    async def test_get_installation_token_api_error_raises(self, github_app_auth):
        """Test that API errors are properly raised."""
        import httpx
        
        with patch.object(github_app_auth, "generate_jwt", return_value="fake-jwt"):
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_post.side_effect = httpx.HTTPError("API Error")
                
                with pytest.raises(VCSAPIError, match="Failed to get installation token"):
                    await github_app_auth.get_installation_token()
    
    @pytest.mark.asyncio
    async def test_get_auth_headers(self, github_app_auth):
        """Test getting auth headers."""
        github_app_auth._installation_token = "test-token"
        github_app_auth._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        headers = await github_app_auth.get_auth_headers()
        
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    
    @pytest.mark.asyncio
    async def test_get_installation_id_for_repo_success(self, github_app_auth):
        """Test auto-detecting installation ID for repo."""
        # Mock installations list
        mock_installations_response = MagicMock()
        mock_installations_response.json.return_value = [
            {"id": 11111111},
            {"id": 12345678},
        ]
        mock_installations_response.raise_for_status = MagicMock()
        
        # Mock repositories list
        mock_repos_response = MagicMock()
        mock_repos_response.json.return_value = {
            "repositories": [
                {"full_name": "owner/repo"},
                {"full_name": "owner/other-repo"},
            ]
        }
        mock_repos_response.raise_for_status = MagicMock()
        
        # Mock token response
        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "token": "ghs_test_token",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat() + "Z",
        }
        mock_token_response.raise_for_status = MagicMock()
        
        with patch.object(github_app_auth, "generate_jwt", return_value="fake-jwt"):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                
                # First call returns installations, subsequent calls return repos/token
                mock_client.get = AsyncMock(
                    side_effect=[mock_installations_response, mock_repos_response]
                )
                mock_client.post = AsyncMock(return_value=mock_token_response)
                mock_client_class.return_value = mock_client
                
                installation_id = await github_app_auth.get_installation_id_for_repo(
                    "owner/repo"
                )
                
                assert installation_id == "11111111"
                assert github_app_auth.installation_id == "11111111"
    
    @pytest.mark.asyncio
    async def test_get_installation_id_for_repo_not_found(self, github_app_auth):
        """Test that missing installation raises error."""
        mock_installations_response = MagicMock()
        mock_installations_response.json.return_value = []
        mock_installations_response.raise_for_status = MagicMock()
        
        with patch.object(github_app_auth, "generate_jwt", return_value="fake-jwt"):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.get = AsyncMock(return_value=mock_installations_response)
                mock_client_class.return_value = mock_client
                
                with pytest.raises(
                    VCSAPIError, match="No installation found with access to"
                ):
                    await github_app_auth.get_installation_id_for_repo("owner/repo")
