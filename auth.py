"""
Authentication module for PM Chatbot API
Provides token-based authentication with configurable backends
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import hashlib
import hmac

logger = logging.getLogger(__name__)

security = HTTPBearer()

class AuthConfig:
    """Authentication configuration"""
    
    def __init__(self):
        # Simple token validation (default)
        self.auth_method = os.getenv("AUTH_METHOD", "simple")
        self.secret_key = os.getenv("API_SECRET_KEY", "pmbot-default-secret-change-in-production")
        self.token_prefix = os.getenv("TOKEN_PREFIX", "pmbot-")
        
        # API Key validation
        self.valid_api_keys = self._load_api_keys()
        
        # JWT settings (for future enhancement)
        self.jwt_algorithm = "HS256"
        self.jwt_expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
        
    def _load_api_keys(self) -> Dict[str, Dict[str, Any]]:
        """Load valid API keys from environment or file"""
        api_keys = {}
        
        # Load from environment variables
        # Format: API_KEY_USER1=pmbot-key1, API_KEY_USER2=pmbot-key2
        for key, value in os.environ.items():
            if key.startswith("API_KEY_"):
                username = key.replace("API_KEY_", "").lower()
                api_keys[value] = {
                    "username": username,
                    "permissions": ["read", "write"],  # Default permissions
                    "created": datetime.now()
                }
        
        # Add default development key
        if not api_keys and os.getenv("ENVIRONMENT", "development") == "development":
            api_keys["pmbot-dev-token"] = {
                "username": "developer",
                "permissions": ["read", "write"],
                "created": datetime.now()
            }
            logger.warning("Using default development token - not for production!")
        
        return api_keys

class TokenValidator:
    """Token validation logic"""
    
    def __init__(self, config: AuthConfig):
        self.config = config
    
    def validate_simple_token(self, token: str) -> Dict[str, Any]:
        """Validate simple prefix-based tokens"""
        if not token.startswith(self.config.token_prefix):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if token is in valid API keys
        if token in self.config.valid_api_keys:
            return self.config.valid_api_keys[token]
        
        # For development, allow any token with correct prefix
        if os.getenv("ENVIRONMENT", "development") == "development":
            return {
                "username": "dev-user",
                "permissions": ["read", "write"],
                "created": datetime.now()
            }
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    def validate_api_key(self, token: str) -> Dict[str, Any]:
        """Validate API key tokens"""
        if token not in self.config.valid_api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return self.config.valid_api_keys[token]
    
    def validate_signed_token(self, token: str) -> Dict[str, Any]:
        """Validate cryptographically signed tokens"""
        try:
            # Split token into payload and signature
            if "." not in token:
                raise ValueError("Invalid token format")
            
            payload_b64, signature = token.rsplit(".", 1)
            
            # Verify signature
            expected_signature = hmac.new(
                self.config.secret_key.encode(),
                payload_b64.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("Invalid signature")
            
            # Decode payload (simple base64 for now)
            import base64
            import json
            payload = json.loads(base64.b64decode(payload_b64 + "=="))
            
            # Check expiry
            if "exp" in payload:
                exp_time = datetime.fromtimestamp(payload["exp"])
                if datetime.now() > exp_time:
                    raise ValueError("Token expired")
            
            return {
                "username": payload.get("sub", "unknown"),
                "permissions": payload.get("permissions", ["read"]),
                "created": datetime.fromtimestamp(payload.get("iat", 0))
            }
            
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

# Global auth instances
auth_config = AuthConfig()
token_validator = TokenValidator(auth_config)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Verify authentication token and return user context
    
    Supports multiple authentication methods:
    - simple: prefix-based tokens (pmbot-*)
    - api_key: pre-configured API keys
    - signed: cryptographically signed tokens
    """
    token = credentials.credentials
    
    try:
        if auth_config.auth_method == "simple":
            user_context = token_validator.validate_simple_token(token)
        elif auth_config.auth_method == "api_key":
            user_context = token_validator.validate_api_key(token)
        elif auth_config.auth_method == "signed":
            user_context = token_validator.validate_signed_token(token)
        else:
            # Fallback to simple validation
            user_context = token_validator.validate_simple_token(token)
        
        # Add token to context for logging
        user_context["token"] = token[:10] + "..." if len(token) > 10 else token
        
        logger.info(f"Authenticated user: {user_context['username']}")
        return user_context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def verify_token_with_permissions(required_permissions: list = None):
    """
    Dependency factory for permission-based authorization
    
    Usage:
    @app.post("/admin/endpoint")
    async def admin_function(user = Depends(verify_token_with_permissions(["admin"]))):
        pass
    """
    async def _verify(user_context: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
        if required_permissions:
            user_permissions = user_context.get("permissions", [])
            
            # Check if user has required permissions
            if not any(perm in user_permissions for perm in required_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {required_permissions}"
                )
        
        return user_context
    
    return _verify

def generate_signed_token(username: str, permissions: list = None, expiry_hours: int = None) -> str:
    """
    Generate a cryptographically signed token
    
    Useful for creating API keys programmatically
    """
    import base64
    import json
    
    if permissions is None:
        permissions = ["read"]
    
    if expiry_hours is None:
        expiry_hours = auth_config.jwt_expiry_hours
    
    # Create payload
    now = datetime.now()
    payload = {
        "sub": username,
        "permissions": permissions,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expiry_hours)).timestamp())
    }
    
    # Encode payload
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.b64encode(payload_json.encode()).decode().rstrip("=")
    
    # Sign payload
    signature = hmac.new(
        auth_config.secret_key.encode(),
        payload_b64.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return f"{payload_b64}.{signature}"

def get_auth_info() -> Dict[str, Any]:
    """Get current authentication configuration info"""
    return {
        "auth_method": auth_config.auth_method,
        "token_prefix": auth_config.token_prefix,
        "valid_keys_count": len(auth_config.valid_api_keys),
        "environment": os.getenv("ENVIRONMENT", "development")
    }