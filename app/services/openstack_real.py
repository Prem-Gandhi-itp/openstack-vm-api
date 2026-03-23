"""
Real OpenStack Service
Full production implementation using the official openstacksdk.

Set MOCK_OPENSTACK=false and configure OS_* env vars to use this.
Install: pip install openstacksdk
Docs:    https://docs.openstack.org/openstacksdk/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import openstack
import openstack.exceptions
from openstack.compute.v2.server import Server

from app.core.exceptions import (
    InvalidVMStateError,
    OpenStackConnectionError,
    QuotaExceededError,
    SnapshotNotFoundError,
    VMNotFoundError,
    VMOperationError,
)
from app.schemas.vm import (
    AddressInfo,
    ConsoleResponse,
    FlavorResponse,
    ImageResponse,
    SnapshotResponse,
    VMMetrics,
    VMResponse,
    VMStatus,
)

logger = logging.getLogger(__name__)

# Valid VM states per operation (enforced client-side for early feedback)
_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "start":          ["SHUTOFF", "STOPPED", "SUSPENDED"],
    "stop":           ["ACTIVE"],
    "reboot":         ["ACTIVE"],
    "suspend":        ["ACTIVE"],
    "resume":         ["SUSPENDED"],
    "pause":          ["ACTIVE"],
    "unpause":        ["PAUSED"],
    "resize":         ["ACTIVE", "SHUTOFF"],
    "confirm_resize": ["VERIFY_RESIZE"],
    "snapshot":       ["ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED"],
    "console":        ["ACTIVE"],
    "delete":         ["ACTIVE", "SHUTOFF", "ERROR", "SUSPENDED", "PAUSED",
                       "VERIFY_RESIZE", "SHELVED", "SHELVED_OFFLOADED"],
    "shelve":         ["ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED"],
    "unshelve":       ["SHELVED", "SHELVED_OFFLOADED"],
    "rescue":         ["ACTIVE", "SHUTOFF"],
    "migrate":        ["ACTIVE", "SHUTOFF"],
    "live_migrate":   ["ACTIVE"],
}


class RealOpenStackService:
    """
    Production OpenStack service.

    Wraps the official openstacksdk, translating Nova/Glance/Cinder
    responses into our domain schemas. All mutations are logged at INFO
    level so operators have a clear audit trail.
    """

    def __init__(
        self,
        auth_url: str,
        username: str,
        password: str,
        project_name: str,
        user_domain_name: str = "Default",
        project_domain_name: str = "Default",
        region_name: str = "RegionOne",
    ) -> None:
        try:
            self.conn = openstack.connect(
                auth_url=auth_url,
                username=username,
                password=password,
                project_name=project_name,
                user_domain_name=user_domain_name,
                project_domain_name=project_domain_name,
                region_name=region_name,
            )
            # Verify credentials eagerly - fail fast at startup
            self.conn.authorize()
            logger.info(
                "Connected to OpenStack at %s (project=%s)", auth_url, project_name
            )
        except openstack.exceptions.HttpException as exc:
            raise OpenStackConnectionError(
                f"Auth failed against {auth_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise OpenStackConnectionError(str(exc)) from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _require_state(self, vm_id: str, current: str, operation: str) -> None:
        allowed = _VALID_TRANSITIONS.get(operation, [])
        if current not in allowed:
            raise InvalidVMStateError(vm_id, current, " or ".join(allowed))

    def _get_server_or_raise(self, vm_id: str) -> Server:
        server = self.conn.compute.get_server(vm_id)
        if server is None:
            raise VMNotFoundError(vm_id)
        return server

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _parse_addresses(raw: Dict) -> Dict[str, List[AddressInfo]]:
        result: Dict[str, List[AddressInfo]] = {}
        for net_name, addrs in (raw or {}).items():
            result[net_name] = [
                AddressInfo(
                    ip=a.get("addr", ""),
                    version=a.get("version", 4),
                    type=a.get("OS-EXT-IPS:type", "fixed"),
                    mac=a.get("OS-EXT-IPS-MAC:mac_addr"),
                )
                for a in addrs
            ]
        return result

    def _to_vm_response(self, server: Server) -> VMResponse:
        raw_status = (server.status or "ERROR").upper()
        try:
            status = VMStatus(raw_status)
        except ValueError:
            status = VMStatus.ERROR

        flavor_id = ""
        if server.flavor:
            flavor_id = (
                server.flavor.get("id")
                or server.flavor.get("original_name", "")
            )

        image_id = ""
        if server.image:
            image_id = server.image.get("id", "")

        sg_names = [sg.get("name", "") for sg in (server.security_groups or [])]

        def _attr(*names: str) -> Any:
            for n in names:
                v = getattr(server, n, None)
                if v is not None:
                    return v
            return None

        return VMResponse(
            id=server.id,
            name=server.name,
            status=status,
            flavor_id=flavor_id,
            image_id=image_id,
            host=_attr("host", "OS-EXT-SRV-ATTR:host"),
            availability_zone=_attr("availability_zone", "OS-EXT-AZ:availability_zone"),
            key_name=server.key_name,
            security_groups=sg_names,
            addresses=self._parse_addresses(server.addresses or {}),
            metadata=dict(server.metadata or {}),
            created_at=self._parse_dt(server.created_at) or datetime.now(timezone.utc),
            updated_at=self._parse_dt(server.updated_at) or datetime.now(timezone.utc),
            launched_at=self._parse_dt(
                _attr("launched_at", "OS-SRV-USG:launched_at")
            ),
            terminated_at=self._parse_dt(
                _attr("terminated_at", "OS-SRV-USG:terminated_at")
            ),
            progress=server.progress or 0,
            task_state=_attr("task_state", "OS-EXT-STS:task_state"),
            power_state=_attr("power_state", "OS-EXT-STS:power_state"),
        )

    # ── VM CRUD ───────────────────────────────────────────────────────────────

    async def list_vms(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if status:
            kwargs["status"] = status.upper()

        servers = list(self.conn.compute.servers(details=True, **kwargs))
        total = len(servers)
        start = (page - 1) * page_size
        paginated = servers[start : start + page_size]

        return {
            "vms": [self._to_vm_response(s) for s in paginated],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": (start + page_size) < total,
        }

    async def get_vm(self, vm_id: str) -> VMResponse:
        server = self._get_server_or_raise(vm_id)
        return self._to_vm_response(server)

    async def create_vm(self, data: Dict[str, Any]) -> VMResponse:
        networks = [
            {
                "uuid": n["network_id"],
                **({"fixed_ip": n["fixed_ip"]} if n.get("fixed_ip") else {}),
            }
            for n in data.get("networks", [])
        ]
        try:
            server = self.conn.compute.create_server(
                name=data["name"],
                flavor_id=data["flavor_id"],
                image_id=data["image_id"],
                networks=networks or [],
                key_name=data.get("key_name"),
                security_groups=[
                    {"name": sg} for sg in data.get("security_groups", ["default"])
                ],
                user_data=data.get("user_data"),
                metadata=data.get("metadata", {}),
                availability_zone=data.get("availability_zone"),
            )
        except openstack.exceptions.HttpException as exc:
            if exc.status_code == 403:
                raise QuotaExceededError("instances") from exc
            raise VMOperationError("create", str(exc)) from exc

        logger.info("Created VM %s (name=%s)", server.id, server.name)
        return self._to_vm_response(server)

    async def update_vm(self, vm_id: str, data: Dict[str, Any]) -> VMResponse:
        server = self._get_server_or_raise(vm_id)
        update_kwargs: Dict[str, Any] = {}

        if data.get("name"):
            update_kwargs["name"] = data["name"]
        if update_kwargs:
            server = self.conn.compute.update_server(vm_id, **update_kwargs)

        if data.get("metadata"):
            self.conn.compute.set_server_metadata(vm_id, **data["metadata"])
            server = self._get_server_or_raise(vm_id)

        logger.info("Updated VM %s", vm_id)
        return self._to_vm_response(server)

    async def delete_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "delete")
        self.conn.compute.delete_server(vm_id, force=False)
        logger.info("Deleted VM %s", vm_id)

    # ── Lifecycle Actions ─────────────────────────────────────────────────────

    async def start_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "start")
        self.conn.compute.start_server(vm_id)
        logger.info("Started VM %s", vm_id)

    async def stop_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "stop")
        self.conn.compute.stop_server(vm_id)
        logger.info("Stopped VM %s", vm_id)

    async def reboot_vm(self, vm_id: str, reboot_type: str = "SOFT") -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "reboot")
        self.conn.compute.reboot_server(vm_id, reboot_type)
        logger.info("Rebooted VM %s (type=%s)", vm_id, reboot_type)

    async def suspend_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "suspend")
        self.conn.compute.suspend_server(vm_id)
        logger.info("Suspended VM %s", vm_id)

    async def resume_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "resume")
        self.conn.compute.resume_server(vm_id)
        logger.info("Resumed VM %s", vm_id)

    async def pause_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "pause")
        self.conn.compute.pause_server(vm_id)
        logger.info("Paused VM %s", vm_id)

    async def unpause_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "unpause")
        self.conn.compute.unpause_server(vm_id)
        logger.info("Unpaused VM %s", vm_id)

    async def resize_vm(self, vm_id: str, flavor_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "resize")
        try:
            self.conn.compute.resize_server(vm_id, flavor_id)
        except openstack.exceptions.HttpException as exc:
            raise VMOperationError("resize", str(exc)) from exc
        logger.info("Resize scheduled: VM %s -> flavor %s", vm_id, flavor_id)

    async def confirm_resize(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "confirm_resize")
        self.conn.compute.confirm_server_resize(vm_id)
        logger.info("Resize confirmed for VM %s", vm_id)

    async def get_console(self, vm_id: str, console_type: str = "novnc") -> ConsoleResponse:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "console")
        try:
            result = self.conn.compute.create_console(
                vm_id, console_type={"type": console_type}
            )
            url = result.get("url", "") if isinstance(result, dict) else getattr(result, "url", "")
        except Exception:
            result = self.conn.compute.get_server_console_url(
                vm_id, console_type={"type": console_type}
            )
            url = result.get("url", "") if isinstance(result, dict) else ""
        return ConsoleResponse(type=console_type, url=url)

    # ── Snapshots ─────────────────────────────────────────────────────────────

    async def list_snapshots(self, vm_id: str) -> List[SnapshotResponse]:
        self._get_server_or_raise(vm_id)
        images = list(
            self.conn.image.images(
                owner=self.conn.current_project_id,
                properties={"instance_uuid": vm_id},
            )
        )
        return [self._to_snapshot_response(img, vm_id) for img in images]

    async def create_snapshot(
        self,
        vm_id: str,
        name: str,
        description: Optional[str],
        metadata: Dict[str, str],
    ) -> SnapshotResponse:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "snapshot")
        image_id = self.conn.compute.create_server_image(
            vm_id,
            name=name,
            metadata={"description": description or "", "source_vm": vm_id, **metadata},
        )
        image = self.conn.image.get_image(image_id)
        logger.info("Snapshot %s created for VM %s", image_id, vm_id)
        return self._to_snapshot_response(image, vm_id)

    async def delete_snapshot(self, vm_id: str, snapshot_id: str) -> None:
        self._get_server_or_raise(vm_id)
        image = self.conn.image.get_image(snapshot_id)
        if image is None:
            raise SnapshotNotFoundError(snapshot_id)
        self.conn.image.delete_image(snapshot_id)
        logger.info("Deleted snapshot %s (VM %s)", snapshot_id, vm_id)

    @staticmethod
    def _to_snapshot_response(image: Any, vm_id: str) -> SnapshotResponse:
        now = datetime.now(timezone.utc)
        props = getattr(image, "properties", {}) or {}
        return SnapshotResponse(
            id=image.id,
            name=image.name,
            vm_id=vm_id,
            status=getattr(image, "status", "unknown"),
            size=(getattr(image, "size", None) or 0) // (1024 ** 3) or None,
            description=props.get("description"),
            metadata={k: v for k, v in props.items() if k != "description"},
            created_at=RealOpenStackService._parse_dt(
                getattr(image, "created_at", None)
            ) or now,
            updated_at=RealOpenStackService._parse_dt(
                getattr(image, "updated_at", None)
            ) or now,
        )

    # ── Catalog ───────────────────────────────────────────────────────────────

    async def list_flavors(self) -> List[FlavorResponse]:
        return [
            FlavorResponse(
                id=f.id,
                name=f.name,
                vcpus=f.vcpus,
                ram_mb=f.ram,
                disk_gb=f.disk,
                ephemeral_gb=getattr(f, "ephemeral", 0) or 0,
                swap_mb=int(f.swap) if f.swap else 0,
                is_public=getattr(f, "is_public", True),
                rxtx_factor=float(getattr(f, "rxtx_factor", 1.0) or 1.0),
            )
            for f in self.conn.compute.flavors()
        ]

    async def list_images(self) -> List[ImageResponse]:
        now = datetime.now(timezone.utc)
        return [
            ImageResponse(
                id=img.id,
                name=img.name,
                status=img.status,
                size=getattr(img, "size", None),
                disk_format=getattr(img, "disk_format", None),
                container_format=getattr(img, "container_format", None),
                created_at=RealOpenStackService._parse_dt(
                    getattr(img, "created_at", None)
                ) or now,
                updated_at=RealOpenStackService._parse_dt(
                    getattr(img, "updated_at", None)
                ) or now,
                min_disk=getattr(img, "min_disk", 0) or 0,
                min_ram=getattr(img, "min_ram", 0) or 0,
                tags=list(getattr(img, "tags", []) or []),
            )
            for img in self.conn.image.images(status="active", visibility="public")
        ]

    # ── Metrics (Gnocchi / Ceilometer) ────────────────────────────────────────

    async def get_vm_metrics(self, vm_id: str) -> VMMetrics:
        self._get_server_or_raise(vm_id)

        def _safe_measure(metric_name: str) -> float:
            try:
                measures = self.conn.metric.get_measures(
                    metric=f"instance:{metric_name}",
                    resource_id=vm_id,
                    aggregation="mean",
                    limit=1,
                )
                return float(measures[-1][2]) if measures else 0.0
            except Exception:
                return 0.0

        return VMMetrics(
            vm_id=vm_id,
            cpu_util_percent=_safe_measure("cpu_util"),
            memory_used_mb=_safe_measure("memory.usage"),
            memory_total_mb=_safe_measure("memory"),
            disk_read_bytes=int(_safe_measure("disk.read.bytes")),
            disk_write_bytes=int(_safe_measure("disk.write.bytes")),
            network_in_bytes=int(_safe_measure("network.incoming.bytes")),
            network_out_bytes=int(_safe_measure("network.outgoing.bytes")),
            timestamp=datetime.now(timezone.utc),
        )

    # ── NEW: Lock / Unlock ────────────────────────────────────────────────────

    async def lock_vm(self, vm_id: str, locked_reason: Optional[str] = None) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.lock_server(vm_id, locked_reason=locked_reason)
        logger.info("Locked VM %s (reason=%s)", vm_id, locked_reason)

    async def unlock_vm(self, vm_id: str) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.unlock_server(vm_id)
        logger.info("Unlocked VM %s", vm_id)

    # ── NEW: Shelve / Unshelve ────────────────────────────────────────────────

    async def shelve_vm(self, vm_id: str) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "shelve")
        self.conn.compute.shelve_server(vm_id)
        logger.info("Shelved VM %s", vm_id)

    async def unshelve_vm(self, vm_id: str, host: Optional[str] = None) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "unshelve")
        self.conn.compute.unshelve_server(vm_id, host=host)
        logger.info("Unshelved VM %s", vm_id)

    # ── NEW: Rescue / Unrescue ────────────────────────────────────────────────

    async def rescue_vm(self, vm_id: str, admin_pass: Optional[str] = None, image_ref: Optional[str] = None) -> dict:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "rescue")
        result = self.conn.compute.rescue_server(vm_id, admin_pass=admin_pass, image_ref=image_ref)
        logger.info("Rescued VM %s", vm_id)
        return {"admin_pass": getattr(result, "admin_pass", None) or admin_pass or ""}

    async def unrescue_vm(self, vm_id: str) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.unrescue_server(vm_id)
        logger.info("Unrescued VM %s", vm_id)

    # ── NEW: Migrate / Live-migrate / Evacuate ────────────────────────────────

    async def migrate_vm(self, vm_id: str, host: Optional[str] = None) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "migrate")
        self.conn.compute.migrate_server(vm_id, host=host)
        logger.info("Cold-migrate scheduled for VM %s -> host=%s", vm_id, host)

    async def live_migrate_vm(self, vm_id: str, host: Optional[str] = None,
                               block_migration: Optional[bool] = None, force: bool = False) -> None:
        server = self._get_server_or_raise(vm_id)
        self._require_state(vm_id, server.status, "live_migrate")
        self.conn.compute.live_migrate_server(
            vm_id, host=host, block_migration=block_migration, force=force
        )
        logger.info("Live-migrate scheduled for VM %s -> host=%s", vm_id, host)

    async def evacuate_vm(self, vm_id: str, host: Optional[str] = None,
                          admin_pass: Optional[str] = None, force: bool = False) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.evacuate_server(vm_id, host=host, admin_pass=admin_pass, force=force)
        logger.info("Evacuated VM %s -> host=%s", vm_id, host)

    # ── NEW: Backup ───────────────────────────────────────────────────────────

    async def backup_vm(self, vm_id: str, name: str, backup_type: str, rotation: int) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.backup_server(vm_id, name=name, backup_type=backup_type, rotation=rotation)
        logger.info("Backup '%s' scheduled for VM %s", name, vm_id)

    # ── NEW: Metadata operations ──────────────────────────────────────────────

    async def get_vm_metadata(self, vm_id: str):
        self._get_server_or_raise(vm_id)
        server = self.conn.compute.get_server_metadata(vm_id)
        from app.schemas.vm import MetadataResponse
        return MetadataResponse(vm_id=vm_id, metadata=dict(server.metadata or {}))

    async def delete_vm_metadata(self, vm_id: str, keys: list) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.delete_server_metadata(vm_id, keys=keys)
        logger.info("Deleted metadata keys %s from VM %s", keys, vm_id)

    # ── NEW: Security group operations ────────────────────────────────────────

    async def add_security_group(self, vm_id: str, sg_name: str) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.add_security_group_to_server(vm_id, sg_name)
        logger.info("Added SG '%s' to VM %s", sg_name, vm_id)

    async def remove_security_group(self, vm_id: str, sg_name: str) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.remove_security_group_from_server(vm_id, sg_name)
        logger.info("Removed SG '%s' from VM %s", sg_name, vm_id)

    # ── NEW: Floating IP operations ───────────────────────────────────────────

    async def add_floating_ip(self, vm_id: str, address: str, fixed_address: Optional[str] = None) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.add_floating_ip_to_server(vm_id, address, fixed_address=fixed_address)
        logger.info("Added floating IP %s to VM %s", address, vm_id)

    async def remove_floating_ip(self, vm_id: str, address: str) -> None:
        self._get_server_or_raise(vm_id)
        self.conn.compute.remove_floating_ip_from_server(vm_id, address)
        logger.info("Removed floating IP %s from VM %s", address, vm_id)
