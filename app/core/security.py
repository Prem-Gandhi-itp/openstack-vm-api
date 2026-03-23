"""
Security utilities: API Key authentication dependency
"""

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency that validates the API key from the request header.
    Raises HTTP 401 if missing, HTTP 403 if invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Provide it via the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if api_key not in settings.VALID_API_KEYS:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired API key.",
        )
    return api_key
