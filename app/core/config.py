"""
Application configuration using Pydantic Settings
Supports environment variables and .env files
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import os


class Settings(BaseSettings):
    # API Info
    PROJECT_NAME: str = "OpenStack VM Lifecycle API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    API_KEY_HEADER: str = "X-API-Key"
    # In production, load from DB or secrets manager
    VALID_API_KEYS: List[str] = ["dev-api-key-12345", "test-api-key-67890"]

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # OpenStack Connection
    OS_AUTH_URL: str = "http://localhost:5000/v3"
    OS_USERNAME: str = "admin"
    OS_PASSWORD: str = "admin"
    OS_PROJECT_NAME: str = "admin"
    OS_USER_DOMAIN_NAME: str = "Default"
    OS_PROJECT_DOMAIN_NAME: str = "Default"
    OS_REGION_NAME: str = "RegionOne"

    # Mock mode: use simulated OpenStack responses (no real OS needed)
    MOCK_OPENSTACK: bool = True

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Redis (for rate limiting & caching in production)
    REDIS_URL: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
