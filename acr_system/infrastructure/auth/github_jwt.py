"""GitHub App JWT authentication."""
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    jwt = None  # type: ignore

import httpx

from acr_system.shared.exceptions.infrastructure_exceptions import VCSAPIError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class GitHubAppAuth:
    """GitHub App authentication using JWT and installation tokens.
    
    Implements authentication flow:
    1. Generate JWT from private key (.pem file)
    2. Use JWT to get installation access token
    3. Use installation token for API requests
    
    References:
    - https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
    - https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app
    """
    
    API_BASE = "https://api.github.com"
    JWT_EXPIRY_SECONDS = 600  # 10 minutes (max allowed by GitHub)
    TOKEN_REFRESH_BUFFER = 300  # Refresh 5 minutes before expiry
    
    def __init__(
        self,
        app_id: str,
        private_key_path: str,
        installation_id: Optional[str] = None,
    ):
        """Initialize GitHub App authentication.
        
        Args:
            app_id: GitHub App ID
            private_key_path: Path to .pem private key file
            installation_id: Installation ID (optional, can be set later)
            
        Raises:
            ImportError: If PyJWT is not installed
            FileNotFoundError: If private key file not found
        """
        if not JWT_AVAILABLE:
            raise ImportError(
                "PyJWT is required for GitHub App authentication. "
                "Install it with: pip install PyJWT[crypto]"
            )
        
        self.app_id = app_id
        self.installation_id = installation_id
        
        # Load private key
        key_path = Path(private_key_path)
        if not key_path.exists():
            raise FileNotFoundError(f"Private key not found: {private_key_path}")
        
        self.private_key = key_path.read_text()
        
        # Token cache
        self._installation_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
        logger.info(f"Initialized GitHub App auth for app_id={app_id}")
    
    def generate_jwt(self) -> str:
        """Generate JWT token for GitHub App.
        
        Returns:
            JWT token string
        """
        now = int(time.time())
        
        payload = {
            "iat": now,  # Issued at time
            "exp": now + self.JWT_EXPIRY_SECONDS,  # Expiration time
            "iss": self.app_id,  # Issuer (GitHub App ID)
        }
        
        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
        )
        
        logger.debug("Generated JWT token")
        return token
    
    async def get_installation_token(
        self,
        installation_id: Optional[str] = None,
    ) -> str:
        """Get installation access token (with caching).
        
        Args:
            installation_id: Installation ID (uses self.installation_id if not provided)
            
        Returns:
            Installation access token
            
        Raises:
            VCSAPIError: If token fetch fails
        """
        inst_id = installation_id or self.installation_id
        if not inst_id:
            raise VCSAPIError("Installation ID not provided")
        
        # Check if cached token is still valid
        if self._installation_token and self._token_expires_at:
            if datetime.now(timezone.utc) < self._token_expires_at - timedelta(seconds=self.TOKEN_REFRESH_BUFFER):
                logger.debug("Using cached installation token")
                return self._installation_token
        
        # Generate new token
        logger.info(f"Fetching new installation token for installation_id={inst_id}")
        jwt_token = self.generate_jwt()
        
        async with httpx.AsyncClient() as client:
            url = f"{self.API_BASE}/app/installations/{inst_id}/access_tokens"
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            
            try:
                response = await client.post(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                token = data["token"]
                expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
                
                # Cache token
                self._installation_token = token
                self._token_expires_at = expires_at
                
                logger.info(f"Installation token obtained, expires at {expires_at}")
                return token
                
            except httpx.HTTPError as e:
                raise VCSAPIError(f"Failed to get installation token: {e}") from e
    
    async def get_auth_headers(
        self,
        repo: Optional[str] = None,
        installation_id: Optional[str] = None,
    ) -> dict:
        """Get authentication headers for API requests.
        
        If installation_id is not set, will auto-detect it using the repo.
        
        Args:
            repo: Repository in format "owner/repo" (for auto-detection)
            installation_id: Installation ID (uses self.installation_id if not provided)
            
        Returns:
            Dict with Authorization header
            
        Raises:
            VCSAPIError: If installation_id cannot be determined
        """
        # Auto-detect installation_id if not set
        if not installation_id and not self.installation_id:
            if repo:
                logger.info(f"Auto-detecting installation_id for repo {repo}")
                installation_id = await self.get_installation_id_for_repo(repo)
            else:
                raise VCSAPIError(
                    "Installation ID not provided and no repo specified for auto-detection. "
                    "Set GITHUB_APP_INSTALLATION_ID or ensure repo is passed to API calls."
                )
        
        token = await self.get_installation_token(installation_id)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    async def get_installation_id_for_repo(self, repo: str) -> str:
        """Get installation ID for a specific repository.
        
        Useful when you don't know the installation ID upfront.
        
        Args:
            repo: Repository in format "owner/repo"
            
        Returns:
            Installation ID
            
        Raises:
            VCSAPIError: If installation not found or fetch fails
        """
        jwt_token = self.generate_jwt()
        
        async with httpx.AsyncClient() as client:
            # Get all installations for this app
            url = f"{self.API_BASE}/app/installations"
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                installations = response.json()
                
                # For each installation, check if it has access to the repo
                owner, repo_name = repo.split("/")
                
                for installation in installations:
                    inst_id = str(installation["id"])
                    
                    # Get repos for this installation
                    repos_url = f"{self.API_BASE}/installation/repositories"
                    inst_token = await self.get_installation_token(inst_id)
                    inst_headers = {
                        "Authorization": f"Bearer {inst_token}",
                        "Accept": "application/vnd.github+json",
                    }
                    
                    repos_response = await client.get(repos_url, headers=inst_headers)
                    repos_response.raise_for_status()
                    
                    repos_data = repos_response.json()
                    for repository in repos_data.get("repositories", []):
                        if repository["full_name"] == repo:
                            logger.info(f"Found installation_id={inst_id} for repo {repo}")
                            self.installation_id = inst_id
                            return inst_id
                
                raise VCSAPIError(f"No installation found with access to {repo}")
                
            except httpx.HTTPError as e:
                raise VCSAPIError(f"Failed to get installation ID: {e}") from e
