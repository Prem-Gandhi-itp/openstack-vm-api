"""
Flavors and Images Catalog Endpoints
GET /flavors
GET /images
"""

from fastapi import APIRouter, Depends
from typing import List

from app.schemas.vm import FlavorResponse, ImageResponse
from app.core.security import get_api_key
from app.services.factory import get_openstack_service

router = APIRouter()


@router.get(
    "/flavors",
    response_model=List[FlavorResponse],
    summary="List available VM flavors",
    description="Returns all available compute flavors (CPU/RAM/disk configurations).",
)
async def list_flavors(
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    return await service.list_flavors()


@router.get(
    "/images",
    response_model=List[ImageResponse],
    summary="List available images",
    description="Returns all bootable images available in the Glance image catalog.",
)
async def list_images(
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    return await service.list_images()
