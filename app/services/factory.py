"""
Service factory: dependency injection for the OpenStack service.
Switches between mock (for local dev/CI) and real SDK (for production).
"""

import logging
from functools import lru_cache
from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_real_service():
    """Cache the real service as a singleton (SDK connection is expensive)."""
    from app.services.openstack_real import RealOpenStackService
    return RealOpenStackService(
        auth_url=settings.OS_AUTH_URL,
        username=settings.OS_USERNAME,
        password=settings.OS_PASSWORD,
        project_name=settings.OS_PROJECT_NAME,
        user_domain_name=settings.OS_USER_DOMAIN_NAME,
        project_domain_name=settings.OS_PROJECT_DOMAIN_NAME,
        region_name=settings.OS_REGION_NAME,
    )


def get_openstack_service():
    """
    FastAPI dependency. Returns mock or real OpenStack service.

    Toggle via MOCK_OPENSTACK env var:
      MOCK_OPENSTACK=true  → fast, in-memory, no cluster needed (default)
      MOCK_OPENSTACK=false → real openstacksdk against OS_AUTH_URL
    """
    if settings.MOCK_OPENSTACK:
        logger.debug("Using MockOpenStackService")
        from app.services.openstack_mock import openstack_service
        return openstack_service

    logger.debug("Using RealOpenStackService")
    return _get_real_service()
