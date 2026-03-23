"""
Mock OpenStack Service
Full in-memory simulation of Nova + Glance + Cinder APIs.
Covers every SDK operation including the newly added ones.
Switch to real SDK: set MOCK_OPENSTACK=False
"""

import uuid
import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from app.schemas.vm import (
    VMResponse, VMStatus, SnapshotResponse, FlavorResponse,
    ImageResponse, VMMetrics, AddressInfo, ConsoleResponse,
    MetadataResponse,
)
from app.core.exceptions import (
    VMNotFoundError, InvalidVMStateError, SnapshotNotFoundError,
    QuotaExceededError, VMLockedError,
)

logger = logging.getLogger(__name__)

# ── In-Memory Store ───────────────────────────────────────────────────────────

_vms: Dict[str, dict] = {}
_snapshots: Dict[str, dict] = {}


def _seed():
    now = datetime.now(timezone.utc)
    for i, (name, status, flavor) in enumerate([
        ("web-server-01", "ACTIVE",  "m1.small"),
        ("db-primary-01", "ACTIVE",  "m1.large"),
        ("worker-node-01","SHUTOFF", "m1.medium"),
        ("bastion-host",  "ACTIVE",  "m1.tiny"),
    ]):
        vid = str(uuid.uuid4())
        _vms[vid] = {
            "id": vid, "name": name, "status": status,
            "flavor_id": flavor, "image_id": "img-ubuntu-22-04",
            "host": f"compute-node-{i+1:02d}", "availability_zone": "nova",
            "key_name": "default-keypair",
            "security_groups": ["default"],
            "addresses": {
                "private": [{"ip": f"10.0.0.{10+i}", "version": 4,
                             "type": "fixed", "mac": f"fa:16:3e:00:00:{i+1:02x}"}],
                "public":  [{"ip": f"203.0.113.{10+i}", "version": 4,
                             "type": "floating", "mac": None}] if status == "ACTIVE" else [],
            },
            "metadata": {"env": "demo", "created_by": "seed"},
            "created_at":  now - timedelta(days=random.randint(1, 30)),
            "updated_at":  now - timedelta(hours=random.randint(0, 12)),
            "launched_at": now - timedelta(days=random.randint(1, 30)) if status == "ACTIVE" else None,
            "terminated_at": None,
            "progress": 100, "task_state": None,
            "power_state": 1 if status == "ACTIVE" else 4,
            # new fields
            "locked": False, "locked_reason": None,
            "shelved": False, "rescued": False,
            "backups": [],
        }

_seed()

_flavors = [
    {"id": "m1.tiny",   "name": "m1.tiny",   "vcpus": 1, "ram_mb": 512,   "disk_gb": 1,   "ephemeral_gb": 0, "swap_mb": 0, "is_public": True, "rxtx_factor": 1.0},
    {"id": "m1.small",  "name": "m1.small",  "vcpus": 1, "ram_mb": 2048,  "disk_gb": 20,  "ephemeral_gb": 0, "swap_mb": 0, "is_public": True, "rxtx_factor": 1.0},
    {"id": "m1.medium", "name": "m1.medium", "vcpus": 2, "ram_mb": 4096,  "disk_gb": 40,  "ephemeral_gb": 0, "swap_mb": 0, "is_public": True, "rxtx_factor": 1.0},
    {"id": "m1.large",  "name": "m1.large",  "vcpus": 4, "ram_mb": 8192,  "disk_gb": 80,  "ephemeral_gb": 0, "swap_mb": 0, "is_public": True, "rxtx_factor": 1.0},
    {"id": "m1.xlarge", "name": "m1.xlarge", "vcpus": 8, "ram_mb": 16384, "disk_gb": 160, "ephemeral_gb": 0, "swap_mb": 0, "is_public": True, "rxtx_factor": 1.0},
]

_images = [
    {"id": "img-ubuntu-22-04", "name": "Ubuntu 22.04 LTS",   "status": "active", "size": 2361393152, "disk_format": "qcow2", "container_format": "bare", "created_at": datetime(2024,1,1,tzinfo=timezone.utc), "updated_at": datetime(2024,6,1,tzinfo=timezone.utc), "min_disk": 10, "min_ram": 512,  "tags": ["ubuntu","lts"]},
    {"id": "img-centos-9",     "name": "CentOS Stream 9",    "status": "active", "size": 1073741824, "disk_format": "qcow2", "container_format": "bare", "created_at": datetime(2024,2,1,tzinfo=timezone.utc), "updated_at": datetime(2024,6,1,tzinfo=timezone.utc), "min_disk": 10, "min_ram": 1024, "tags": ["centos","rhel"]},
    {"id": "img-debian-12",    "name": "Debian 12 Bookworm", "status": "active", "size": 900000000,  "disk_format": "qcow2", "container_format": "bare", "created_at": datetime(2024,3,1,tzinfo=timezone.utc), "updated_at": datetime(2024,6,1,tzinfo=timezone.utc), "min_disk": 10, "min_ram": 512,  "tags": ["debian"]},
]


# ── CRUD ──────────────────────────────────────────────────────────────────────

class MockOpenStackService:
    """Full in-memory simulation of OpenStack Nova + Glance APIs."""

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get(self, vm_id: str) -> dict:
        if vm_id not in _vms:
            raise VMNotFoundError(vm_id)
        return _vms[vm_id]

    def _require_status(self, vm: dict, *allowed: str):
        if vm["status"] not in allowed:
            raise InvalidVMStateError(vm["id"], vm["status"], " or ".join(allowed))

    def _require_unlocked(self, vm: dict):
        if vm.get("locked"):
            raise VMLockedError(vm["id"])

    def _touch(self, vm: dict):
        vm["updated_at"] = datetime.now(timezone.utc)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def list_vms(self, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        items = list(_vms.values())
        if status:
            items = [v for v in items if v["status"] == status.upper()]
        total = len(items)
        start = (page - 1) * page_size
        return {
            "vms": [VMResponse(**v) for v in items[start:start + page_size]],
            "total": total, "page": page, "page_size": page_size,
            "has_next": (start + page_size) < total,
        }

    async def get_vm(self, vm_id: str) -> VMResponse:
        return VMResponse(**self._get(vm_id))

    async def create_vm(self, data: dict) -> VMResponse:
        if len(_vms) >= 50:
            raise QuotaExceededError("instances")
        now = datetime.now(timezone.utc)
        vm_id = str(uuid.uuid4())
        data.pop("count", 1)
        vm = {
            **data, "id": vm_id, "status": "ACTIVE",
            "host": f"compute-node-{random.randint(1,4):02d}",
            "availability_zone": data.get("availability_zone", "nova"),
            "addresses": {"private": [{"ip": f"10.0.{random.randint(1,254)}.{random.randint(2,254)}", "version": 4, "type": "fixed", "mac": f"fa:16:3e:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"}]},
            "created_at": now, "updated_at": now, "launched_at": now,
            "terminated_at": None, "progress": 100, "task_state": None, "power_state": 1,
            "locked": False, "locked_reason": None, "shelved": False, "rescued": False, "backups": [],
        }
        _vms[vm_id] = vm
        logger.info("Created VM %s (%s)", vm_id, data.get("name"))
        return VMResponse(**vm)

    async def update_vm(self, vm_id: str, data: dict) -> VMResponse:
        vm = self._get(vm_id)
        if data.get("name"):
            vm["name"] = data["name"]
        if data.get("metadata") is not None:
            vm["metadata"].update(data["metadata"])
        self._touch(vm)
        return VMResponse(**vm)

    async def delete_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        vm["status"] = "DELETED"
        vm["terminated_at"] = datetime.now(timezone.utc)
        del _vms[vm_id]
        logger.info("Deleted VM %s", vm_id)

    # ── Basic lifecycle ───────────────────────────────────────────────────────

    async def start_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "SHUTOFF", "STOPPED", "SUSPENDED")
        vm["status"] = "ACTIVE"
        vm["power_state"] = 1
        vm["launched_at"] = datetime.now(timezone.utc)
        self._touch(vm)
        logger.info("Started VM %s", vm_id)

    async def stop_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE")
        vm["status"] = "SHUTOFF"
        vm["power_state"] = 4
        self._touch(vm)
        logger.info("Stopped VM %s", vm_id)

    async def reboot_vm(self, vm_id: str, reboot_type: str = "SOFT") -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE")
        vm["status"] = "ACTIVE"   # instant for mock
        self._touch(vm)
        logger.info("Rebooted VM %s (%s)", vm_id, reboot_type)

    async def suspend_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE")
        vm["status"] = "SUSPENDED"
        vm["power_state"] = 3
        self._touch(vm)

    async def resume_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "SUSPENDED")
        vm["status"] = "ACTIVE"
        vm["power_state"] = 1
        self._touch(vm)

    async def pause_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE")
        vm["status"] = "PAUSED"
        self._touch(vm)

    async def unpause_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "PAUSED")
        vm["status"] = "ACTIVE"
        self._touch(vm)

    async def resize_vm(self, vm_id: str, flavor_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE", "SHUTOFF")
        vm["status"] = "VERIFY_RESIZE"
        vm["flavor_id"] = flavor_id
        self._touch(vm)

    async def confirm_resize(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "VERIFY_RESIZE")
        vm["status"] = "ACTIVE"
        self._touch(vm)

    async def get_console(self, vm_id: str, console_type: str = "novnc") -> ConsoleResponse:
        vm = self._get(vm_id)
        self._require_status(vm, "ACTIVE")
        token = uuid.uuid4().hex
        return ConsoleResponse(
            type=console_type,
            url=f"http://console.openstack.example.com:6080/vnc_auto.html?token={token}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    # ── NEW: Lock / Unlock ────────────────────────────────────────────────────

    async def lock_vm(self, vm_id: str, locked_reason: Optional[str] = None) -> None:
        vm = self._get(vm_id)
        vm["locked"] = True
        vm["locked_reason"] = locked_reason
        self._touch(vm)
        logger.info("Locked VM %s (reason=%s)", vm_id, locked_reason)

    async def unlock_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        vm["locked"] = False
        vm["locked_reason"] = None
        self._touch(vm)
        logger.info("Unlocked VM %s", vm_id)

    # ── NEW: Shelve / Unshelve ────────────────────────────────────────────────

    async def shelve_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED")
        vm["status"] = "SHELVED"
        vm["shelved"] = True
        vm["power_state"] = 4
        self._touch(vm)
        logger.info("Shelved VM %s", vm_id)

    async def unshelve_vm(self, vm_id: str, host: Optional[str] = None) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "SHELVED", "SHELVED_OFFLOADED")
        vm["status"] = "ACTIVE"
        vm["shelved"] = False
        vm["power_state"] = 1
        if host:
            vm["host"] = host
        self._touch(vm)
        logger.info("Unshelved VM %s", vm_id)

    # ── NEW: Rescue / Unrescue ────────────────────────────────────────────────

    async def rescue_vm(self, vm_id: str, admin_pass: Optional[str] = None, image_ref: Optional[str] = None) -> dict:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE", "SHUTOFF")
        vm["status"] = "RESCUE"
        vm["rescued"] = True
        self._touch(vm)
        logger.info("Rescued VM %s", vm_id)
        return {"admin_pass": admin_pass or uuid.uuid4().hex[:12]}

    async def unrescue_vm(self, vm_id: str) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "RESCUE")
        vm["status"] = "ACTIVE"
        vm["rescued"] = False
        self._touch(vm)
        logger.info("Unrescued VM %s", vm_id)

    # ── NEW: Migrate / Live-migrate / Evacuate ────────────────────────────────

    async def migrate_vm(self, vm_id: str, host: Optional[str] = None) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE", "SHUTOFF")
        old_host = vm["host"]
        vm["host"] = host or f"compute-node-{random.randint(1,4):02d}"
        vm["status"] = "VERIFY_RESIZE"   # Nova cold migrate flow
        self._touch(vm)
        logger.info("Cold-migrated VM %s from %s to %s", vm_id, old_host, vm["host"])

    async def live_migrate_vm(self, vm_id: str, host: Optional[str] = None,
                              block_migration: Optional[bool] = None, force: bool = False) -> None:
        vm = self._get(vm_id)
        self._require_unlocked(vm)
        self._require_status(vm, "ACTIVE")
        old_host = vm["host"]
        vm["host"] = host or f"compute-node-{random.randint(1,4):02d}"
        vm["task_state"] = "migrating"
        vm["task_state"] = None          # instant in mock
        self._touch(vm)
        logger.info("Live-migrated VM %s from %s to %s", vm_id, old_host, vm["host"])

    async def evacuate_vm(self, vm_id: str, host: Optional[str] = None,
                          admin_pass: Optional[str] = None, force: bool = False) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "ACTIVE", "SHUTOFF", "STOPPED", "ERROR")
        old_host = vm["host"]
        vm["host"] = host or f"compute-node-{random.randint(1,4):02d}"
        vm["status"] = "ACTIVE"
        self._touch(vm)
        logger.info("Evacuated VM %s from %s to %s", vm_id, old_host, vm["host"])

    # ── NEW: Backup ───────────────────────────────────────────────────────────

    async def backup_vm(self, vm_id: str, name: str, backup_type: str, rotation: int) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "ACTIVE", "SHUTOFF")
        backups = vm.setdefault("backups", [])
        backups.append({"name": name, "type": backup_type, "created_at": datetime.now(timezone.utc).isoformat()})
        # enforce rotation — remove oldest
        while len(backups) > rotation:
            backups.pop(0)
        self._touch(vm)
        logger.info("Backup '%s' created for VM %s (rotation=%d)", name, vm_id, rotation)

    # ── NEW: Metadata operations ──────────────────────────────────────────────

    async def get_vm_metadata(self, vm_id: str) -> MetadataResponse:
        vm = self._get(vm_id)
        return MetadataResponse(vm_id=vm_id, metadata=dict(vm.get("metadata", {})))

    async def delete_vm_metadata(self, vm_id: str, keys: List[str]) -> None:
        vm = self._get(vm_id)
        for key in keys:
            vm["metadata"].pop(key, None)
        self._touch(vm)
        logger.info("Deleted metadata keys %s from VM %s", keys, vm_id)

    # ── NEW: Security group operations ────────────────────────────────────────

    async def add_security_group(self, vm_id: str, sg_name: str) -> None:
        vm = self._get(vm_id)
        if sg_name not in vm["security_groups"]:
            vm["security_groups"].append(sg_name)
        self._touch(vm)
        logger.info("Added SG '%s' to VM %s", sg_name, vm_id)

    async def remove_security_group(self, vm_id: str, sg_name: str) -> None:
        vm = self._get(vm_id)
        if sg_name in vm["security_groups"]:
            vm["security_groups"].remove(sg_name)
        self._touch(vm)
        logger.info("Removed SG '%s' from VM %s", sg_name, vm_id)

    # ── NEW: Floating IP operations ───────────────────────────────────────────

    async def add_floating_ip(self, vm_id: str, address: str, fixed_address: Optional[str] = None) -> None:
        vm = self._get(vm_id)
        self._require_status(vm, "ACTIVE")
        public = vm["addresses"].setdefault("public", [])
        if not any(a["ip"] == address for a in public):
            public.append({"ip": address, "version": 4, "type": "floating", "mac": None})
        self._touch(vm)
        logger.info("Added floating IP %s to VM %s", address, vm_id)

    async def remove_floating_ip(self, vm_id: str, address: str) -> None:
        vm = self._get(vm_id)
        public = vm["addresses"].get("public", [])
        vm["addresses"]["public"] = [a for a in public if a["ip"] != address]
        self._touch(vm)
        logger.info("Removed floating IP %s from VM %s", address, vm_id)

    # ── Snapshots ─────────────────────────────────────────────────────────────

    async def list_snapshots(self, vm_id: str) -> List[SnapshotResponse]:
        self._get(vm_id)
        return [SnapshotResponse(**s) for s in _snapshots.values() if s["vm_id"] == vm_id]

    async def create_snapshot(self, vm_id: str, name: str, description: Optional[str], metadata: dict) -> SnapshotResponse:
        self._get(vm_id)
        now = datetime.now(timezone.utc)
        snap_id = str(uuid.uuid4())
        snap = {"id": snap_id, "name": name, "vm_id": vm_id, "status": "active",
                "size": random.randint(10, 80), "description": description,
                "metadata": metadata, "created_at": now, "updated_at": now}
        _snapshots[snap_id] = snap
        logger.info("Snapshot %s created for VM %s", snap_id, vm_id)
        return SnapshotResponse(**snap)

    async def delete_snapshot(self, vm_id: str, snapshot_id: str) -> None:
        self._get(vm_id)
        if snapshot_id not in _snapshots:
            raise SnapshotNotFoundError(snapshot_id)
        del _snapshots[snapshot_id]

    # ── Flavors & Images ──────────────────────────────────────────────────────

    async def list_flavors(self) -> List[FlavorResponse]:
        return [FlavorResponse(**f) for f in _flavors]

    async def list_images(self) -> List[ImageResponse]:
        return [ImageResponse(**i) for i in _images]

    # ── Metrics ───────────────────────────────────────────────────────────────

    async def get_vm_metrics(self, vm_id: str) -> VMMetrics:
        self._get(vm_id)
        return VMMetrics(
            vm_id=vm_id,
            cpu_util_percent=round(random.uniform(0.5, 95.0), 2),
            memory_used_mb=round(random.uniform(256, 7800), 2),
            memory_total_mb=8192,
            disk_read_bytes=random.randint(0, 10_000_000),
            disk_write_bytes=random.randint(0, 5_000_000),
            network_in_bytes=random.randint(0, 50_000_000),
            network_out_bytes=random.randint(0, 20_000_000),
            timestamp=datetime.now(timezone.utc),
        )


# Singleton
openstack_service = MockOpenStackService()
