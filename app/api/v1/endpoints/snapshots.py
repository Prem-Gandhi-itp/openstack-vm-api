"""
VM Snapshot Endpoints
GET  /vms/{id}/snapshots
POST /vms/{id}/snapshots
DELETE /vms/{id}/snapshots/{snapshot_id}
"""

from fastapi import APIRouter, Depends, HTTPException, status
import logging

from app.schemas.vm import SnapshotCreateRequest, SnapshotResponse, SnapshotListResponse, ErrorResponse
from app.core.security import get_api_key
from app.core.exceptions import VMNotFoundError, SnapshotNotFoundError
from app.services.factory import get_openstack_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/{vm_id}/snapshots",
    response_model=SnapshotListResponse,
    summary="List snapshots for a VM",
    responses={404: {"model": ErrorResponse}},
)
async def list_snapshots(
    vm_id: str,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        snapshots = await service.list_snapshots(vm_id)
        return SnapshotListResponse(snapshots=snapshots, total=len(snapshots))
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{vm_id}/snapshots",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a snapshot of a VM",
    responses={404: {"model": ErrorResponse}},
)
async def create_snapshot(
    vm_id: str,
    body: SnapshotCreateRequest,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        return await service.create_snapshot(
            vm_id, body.name, body.description, body.metadata
        )
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{vm_id}/snapshots/{snapshot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a snapshot",
    responses={404: {"model": ErrorResponse}},
)
async def delete_snapshot(
    vm_id: str,
    snapshot_id: str,
    _api_key: str = Depends(get_api_key),
    service=Depends(get_openstack_service),
):
    try:
        await service.delete_snapshot(vm_id, snapshot_id)
    except (VMNotFoundError, SnapshotNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
