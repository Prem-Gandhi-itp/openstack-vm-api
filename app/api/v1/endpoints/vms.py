"""
VM CRUD Endpoints
GET /vms, POST /vms, GET /vms/{id}, PUT /vms/{id}, DELETE /vms/{id}
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional
import logging

from app.schemas.vm import (
    VMCreateRequest, VMUpdateRequest, VMResponse, VMListResponse, ErrorResponse
)
from app.core.security import get_api_key
from app.core.exceptions import VMNotFoundError, QuotaExceededError
from app.services.factory import get_openstack_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/",
    response_model=VMListResponse,
    summary="List all VMs",
    description="Returns a paginated list of all virtual machines, with optional status filter.",
    responses={403: {"model": ErrorResponse}},
)
async def list_vms(
    status: Optional[str] = Query(None, description="Filter by VM status (ACTIVE, SHUTOFF, ERROR, etc.)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    result = await service.list_vms(status=status, page=page, page_size=page_size)
    return result


@router.post(
    "/",
    response_model=VMResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a VM",
    description="Provisions a new virtual machine from the provided image and flavor.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "Quota exceeded"},
    },
)
async def create_vm(
    body: VMCreateRequest,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        return await service.create_vm(body.model_dump())
    except QuotaExceededError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Get VM details",
    responses={
        404: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def get_vm(
    vm_id: str,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        return await service.get_vm(vm_id)
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/{vm_id}",
    response_model=VMResponse,
    summary="Update VM metadata/name",
    responses={
        404: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def update_vm(
    vm_id: str,
    body: VMUpdateRequest,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        return await service.update_vm(vm_id, body.model_dump(exclude_none=True))
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{vm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a VM",
    description="Permanently terminates and removes the VM. This action is irreversible.",
    responses={
        404: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
async def delete_vm(
    vm_id: str,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        await service.delete_vm(vm_id)
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
