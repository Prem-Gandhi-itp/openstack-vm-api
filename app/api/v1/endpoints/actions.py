"""
VM Lifecycle Action Endpoints — full SDK coverage.

Existing:
  POST /vms/{id}/start          POST /vms/{id}/stop
  POST /vms/{id}/reboot         POST /vms/{id}/suspend
  POST /vms/{id}/resume         POST /vms/{id}/pause
  POST /vms/{id}/unpause        POST /vms/{id}/resize
  POST /vms/{id}/resize/confirm GET  /vms/{id}/console
  GET  /vms/{id}/metrics

New (SDK-complete):
  POST /vms/{id}/lock           POST /vms/{id}/unlock
  POST /vms/{id}/shelve         POST /vms/{id}/unshelve
  POST /vms/{id}/rescue         POST /vms/{id}/unrescue
  POST /vms/{id}/migrate        POST /vms/{id}/live-migrate
  POST /vms/{id}/evacuate       POST /vms/{id}/backup
  GET  /vms/{id}/metadata       DELETE /vms/{id}/metadata
  POST /vms/{id}/security-groups/add
  POST /vms/{id}/security-groups/remove
  POST /vms/{id}/floating-ips/add
  POST /vms/{id}/floating-ips/remove
"""

from fastapi import APIRouter, Depends, HTTPException
import logging
import uuid

from app.schemas.vm import (
    ActionResponse, RebootRequest, ResizeRequest,
    ConsoleResponse, VMMetrics, ErrorResponse,
    LockRequest, RescueRequest, MigrateRequest, LiveMigrateRequest,
    EvacuateRequest, BackupRequest, SecurityGroupRequest,
    FloatingIPRequest, MetadataResponse, MetadataDeleteRequest,
)
from app.core.security import get_api_key
from app.core.exceptions import VMNotFoundError, InvalidVMStateError, VMLockedError
from app.services.factory import get_openstack_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(vm_id: str, action: str, message: str) -> ActionResponse:
    return ActionResponse(success=True, message=message, vm_id=vm_id,
                          action=action, request_id=str(uuid.uuid4()))


def _handle(e: Exception, vm_id: str):
    if isinstance(e, VMNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, InvalidVMStateError):
        raise HTTPException(status_code=409, detail=str(e))
    if isinstance(e, VMLockedError):
        raise HTTPException(status_code=409, detail=str(e))
    logger.error("Unexpected error on VM %s: %s", vm_id, e)
    raise HTTPException(status_code=500, detail=str(e))


# ── Existing lifecycle actions ─────────────────────────────────────────────────

@router.post("/{vm_id}/start", response_model=ActionResponse,
             summary="Start a stopped VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def start_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.start_vm(vm_id)
        return _ok(vm_id, "start", "VM start initiated.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/stop", response_model=ActionResponse,
             summary="Stop a running VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def stop_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.stop_vm(vm_id)
        return _ok(vm_id, "stop", "VM stop initiated.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/reboot", response_model=ActionResponse,
             summary="Reboot a VM (SOFT or HARD)",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def reboot_vm(vm_id: str, body: RebootRequest = RebootRequest(),
                    _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.reboot_vm(vm_id, reboot_type=body.type.value)
        return _ok(vm_id, "reboot", f"VM {body.type.value} reboot initiated.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/suspend", response_model=ActionResponse, summary="Suspend a VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def suspend_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.suspend_vm(vm_id)
        return _ok(vm_id, "suspend", "VM suspended.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/resume", response_model=ActionResponse, summary="Resume a suspended VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def resume_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.resume_vm(vm_id)
        return _ok(vm_id, "resume", "VM resumed.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/pause", response_model=ActionResponse, summary="Pause a VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def pause_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.pause_vm(vm_id)
        return _ok(vm_id, "pause", "VM paused.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/unpause", response_model=ActionResponse, summary="Unpause a paused VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def unpause_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.unpause_vm(vm_id)
        return _ok(vm_id, "unpause", "VM unpaused.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/resize", response_model=ActionResponse,
             summary="Resize VM to a different flavor",
             description="Schedules a resize. VM enters VERIFY_RESIZE. Call /resize/confirm to finalize.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def resize_vm(vm_id: str, body: ResizeRequest, _=Depends(get_api_key),
                    service=Depends(get_openstack_service)):
    try:
        await service.resize_vm(vm_id, body.flavor_id)
        return _ok(vm_id, "resize", f"Resize to {body.flavor_id} scheduled. Call /resize/confirm.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/resize/confirm", response_model=ActionResponse,
             summary="Confirm a pending resize",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def confirm_resize(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.confirm_resize(vm_id)
        return _ok(vm_id, "resize_confirm", "Resize confirmed. VM is ACTIVE.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


@router.get("/{vm_id}/console", response_model=ConsoleResponse,
            summary="Get VNC/SPICE console URL",
            responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def get_console(vm_id: str, console_type: str = "novnc",
                      _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        return await service.get_console(vm_id, console_type=console_type)
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


@router.get("/{vm_id}/metrics", response_model=VMMetrics,
            summary="Get VM resource utilization metrics",
            responses={404: {"model": ErrorResponse}})
async def get_metrics(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        return await service.get_vm_metrics(vm_id)
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── NEW: Lock / Unlock ─────────────────────────────────────────────────────────

@router.post("/{vm_id}/lock", response_model=ActionResponse,
             summary="Lock a VM — prevents modifications until unlocked",
             description="Locked VMs reject stop/start/resize/delete. Provide an optional reason.",
             responses={404: {"model": ErrorResponse}})
async def lock_vm(vm_id: str, body: LockRequest = LockRequest(),
                  _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.lock_vm(vm_id, locked_reason=body.locked_reason)
        reason_msg = f" Reason: {body.locked_reason}" if body.locked_reason else ""
        return _ok(vm_id, "lock", f"VM locked.{reason_msg}")
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{vm_id}/unlock", response_model=ActionResponse,
             summary="Unlock a previously locked VM",
             responses={404: {"model": ErrorResponse}})
async def unlock_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.unlock_vm(vm_id)
        return _ok(vm_id, "unlock", "VM unlocked.")
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── NEW: Shelve / Unshelve ─────────────────────────────────────────────────────

@router.post("/{vm_id}/shelve", response_model=ActionResponse,
             summary="Shelve a VM — frees compute resources while preserving data",
             description="VM state and data are saved to storage. Compute resources are freed. Status → SHELVED.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def shelve_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.shelve_vm(vm_id)
        return _ok(vm_id, "shelve", "VM shelved. Compute resources freed.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/unshelve", response_model=ActionResponse,
             summary="Unshelve a shelved VM — restores it to ACTIVE",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def unshelve_vm(vm_id: str, body: MigrateRequest = MigrateRequest(),
                      _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.unshelve_vm(vm_id, host=body.host)
        return _ok(vm_id, "unshelve", "VM unshelved and ACTIVE.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


# ── NEW: Rescue / Unrescue ─────────────────────────────────────────────────────

@router.post("/{vm_id}/rescue", response_model=ActionResponse,
             summary="Put VM into rescue mode",
             description="Boots into a rescue image so you can recover a broken OS. Status → RESCUE.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def rescue_vm(vm_id: str, body: RescueRequest = RescueRequest(),
                    _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        result = await service.rescue_vm(vm_id, admin_pass=body.admin_pass, image_ref=body.image_ref)
        return _ok(vm_id, "rescue", f"VM in rescue mode. Admin pass: {result.get('admin_pass','(unchanged)')}")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/unrescue", response_model=ActionResponse,
             summary="Exit rescue mode — restores VM to ACTIVE",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def unrescue_vm(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.unrescue_vm(vm_id)
        return _ok(vm_id, "unrescue", "VM exited rescue mode and is ACTIVE.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


# ── NEW: Migrate / Live-migrate / Evacuate ─────────────────────────────────────

@router.post("/{vm_id}/migrate", response_model=ActionResponse,
             summary="Cold-migrate VM to another compute host",
             description="VM is shut off, moved, then enters VERIFY_RESIZE. Call /resize/confirm to finalize.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def migrate_vm(vm_id: str, body: MigrateRequest = MigrateRequest(),
                     _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.migrate_vm(vm_id, host=body.host)
        host_msg = f" to host '{body.host}'" if body.host else " (scheduler will choose host)"
        return _ok(vm_id, "migrate", f"Cold migration scheduled{host_msg}. Confirm with /resize/confirm.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/live-migrate", response_model=ActionResponse,
             summary="Live-migrate VM with zero downtime",
             description="VM keeps running while being moved to another host. ACTIVE throughout.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def live_migrate_vm(vm_id: str, body: LiveMigrateRequest = LiveMigrateRequest(),
                          _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.live_migrate_vm(vm_id, host=body.host,
                                      block_migration=body.block_migration, force=body.force)
        host_msg = f" to host '{body.host}'" if body.host else " (scheduler will choose host)"
        return _ok(vm_id, "live_migrate", f"Live migration initiated{host_msg}.")
    except (VMNotFoundError, InvalidVMStateError, VMLockedError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/evacuate", response_model=ActionResponse,
             summary="Evacuate VM off a failed host",
             description="Used in host failure scenarios. Moves VM to a healthy host. Requires admin.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def evacuate_vm(vm_id: str, body: EvacuateRequest = EvacuateRequest(),
                      _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.evacuate_vm(vm_id, host=body.host, admin_pass=body.admin_pass, force=body.force)
        host_msg = f" to '{body.host}'" if body.host else ""
        return _ok(vm_id, "evacuate", f"VM evacuated{host_msg}.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


# ── NEW: Backup ────────────────────────────────────────────────────────────────

@router.post("/{vm_id}/backup", response_model=ActionResponse,
             summary="Create a scheduled backup with rotation",
             description="Creates a Glance image backup. Oldest backup deleted when rotation limit exceeded.",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def backup_vm(vm_id: str, body: BackupRequest, _=Depends(get_api_key),
                    service=Depends(get_openstack_service)):
    try:
        await service.backup_vm(vm_id, name=body.name, backup_type=body.backup_type,
                                rotation=body.rotation)
        return _ok(vm_id, "backup",
                   f"Backup '{body.name}' ({body.backup_type}) scheduled. Rotation={body.rotation}.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


# ── NEW: Metadata ──────────────────────────────────────────────────────────────

@router.get("/{vm_id}/metadata", response_model=MetadataResponse,
            summary="Get VM metadata key-value pairs",
            responses={404: {"model": ErrorResponse}})
async def get_metadata(vm_id: str, _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        return await service.get_vm_metadata(vm_id)
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{vm_id}/metadata", status_code=204,
               summary="Delete specific metadata keys from a VM",
               responses={404: {"model": ErrorResponse}})
async def delete_metadata(vm_id: str, body: MetadataDeleteRequest,
                          _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.delete_vm_metadata(vm_id, keys=body.keys)
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── NEW: Security Groups ───────────────────────────────────────────────────────

@router.post("/{vm_id}/security-groups/add", response_model=ActionResponse,
             summary="Add a security group to a running VM",
             responses={404: {"model": ErrorResponse}})
async def add_security_group(vm_id: str, body: SecurityGroupRequest,
                              _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.add_security_group(vm_id, sg_name=body.name)
        return _ok(vm_id, "security_group_add", f"Security group '{body.name}' added.")
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{vm_id}/security-groups/remove", response_model=ActionResponse,
             summary="Remove a security group from a VM",
             responses={404: {"model": ErrorResponse}})
async def remove_security_group(vm_id: str, body: SecurityGroupRequest,
                                 _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.remove_security_group(vm_id, sg_name=body.name)
        return _ok(vm_id, "security_group_remove", f"Security group '{body.name}' removed.")
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── NEW: Floating IPs ──────────────────────────────────────────────────────────

@router.post("/{vm_id}/floating-ips/add", response_model=ActionResponse,
             summary="Attach a floating IP to a VM",
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def add_floating_ip(vm_id: str, body: FloatingIPRequest,
                           _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.add_floating_ip(vm_id, address=body.address, fixed_address=body.fixed_address)
        return _ok(vm_id, "floating_ip_add", f"Floating IP {body.address} attached.")
    except (VMNotFoundError, InvalidVMStateError) as e:
        _handle(e, vm_id)


@router.post("/{vm_id}/floating-ips/remove", response_model=ActionResponse,
             summary="Detach a floating IP from a VM",
             responses={404: {"model": ErrorResponse}})
async def remove_floating_ip(vm_id: str, body: FloatingIPRequest,
                              _=Depends(get_api_key), service=Depends(get_openstack_service)):
    try:
        await service.remove_floating_ip(vm_id, address=body.address)
        return _ok(vm_id, "floating_ip_remove", f"Floating IP {body.address} detached.")
    except VMNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
