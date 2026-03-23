"""
Pydantic v2 schemas for request validation and response serialization.
These are the API contract — not the internal domain models.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime


# ── Enums ─────────────────────────────────────────────────────────────────────

class VMStatus(str, Enum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    SUSPENDED = "SUSPENDED"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    BUILD = "BUILD"
    DELETED = "DELETED"
    SHUTOFF = "SHUTOFF"
    REBOOT = "REBOOT"
    HARD_REBOOT = "HARD_REBOOT"
    MIGRATING = "MIGRATING"
    RESIZE = "RESIZE"
    VERIFY_RESIZE = "VERIFY_RESIZE"
    SHELVED = "SHELVED"
    SHELVED_OFFLOADED = "SHELVED_OFFLOADED"
    RESCUE = "RESCUE"


class RebootType(str, Enum):
    SOFT = "SOFT"
    HARD = "HARD"


class DiskFormat(str, Enum):
    QCOW2 = "qcow2"
    RAW = "raw"
    VMDK = "vmdk"
    VHD = "vhd"


# ── VM Schemas ────────────────────────────────────────────────────────────────

class NetworkInterface(BaseModel):
    network_id: str
    fixed_ip: Optional[str] = None
    port_id: Optional[str] = None


class VMCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="VM display name")
    flavor_id: str = Field(..., description="OpenStack flavor ID (e.g., m1.small)")
    image_id: str = Field(..., description="Glance image ID to boot from")
    networks: List[NetworkInterface] = Field(
        default_factory=list, description="Network interfaces to attach"
    )
    key_name: Optional[str] = Field(None, description="SSH keypair name")
    security_groups: List[str] = Field(
        default_factory=lambda: ["default"],
        description="Security group names",
    )
    user_data: Optional[str] = Field(
        None, description="Base64-encoded cloud-init user data"
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Arbitrary key-value metadata"
    )
    availability_zone: Optional[str] = Field(
        None, description="Target availability zone"
    )
    count: int = Field(1, ge=1, le=10, description="Number of identical VMs to create")

    @field_validator("name")
    @classmethod
    def name_must_be_valid(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Name must be alphanumeric with hyphens/underscores only")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "name": "web-server-01",
            "flavor_id": "m1.small",
            "image_id": "ami-ubuntu-22-04",
            "networks": [{"network_id": "net-private"}],
            "key_name": "my-keypair",
            "security_groups": ["default", "web-sg"],
            "metadata": {"env": "production", "team": "platform"},
        }
    }}


class VMUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    metadata: Optional[Dict[str, str]] = None


class AddressInfo(BaseModel):
    ip: str
    version: int
    type: str  # "fixed" or "floating"
    mac: Optional[str] = None


class VMResponse(BaseModel):
    id: str
    name: str
    status: VMStatus
    flavor_id: str
    image_id: str
    host: Optional[str] = None
    availability_zone: Optional[str] = None
    key_name: Optional[str] = None
    security_groups: List[str] = []
    addresses: Dict[str, List[AddressInfo]] = {}
    metadata: Dict[str, str] = {}
    created_at: datetime
    updated_at: datetime
    launched_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    progress: int = Field(0, ge=0, le=100)
    task_state: Optional[str] = None
    power_state: Optional[int] = None

    model_config = {"from_attributes": True}


class VMListResponse(BaseModel):
    vms: List[VMResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# ── Action Schemas ────────────────────────────────────────────────────────────

class RebootRequest(BaseModel):
    type: RebootType = Field(RebootType.SOFT, description="SOFT=graceful, HARD=forced")


class ResizeRequest(BaseModel):
    flavor_id: str = Field(..., description="Target flavor ID to resize to")


class ConsoleRequest(BaseModel):
    console_type: str = Field("novnc", description="Console type: novnc, spice, rdp")


class ConsoleResponse(BaseModel):
    type: str
    url: str
    expires_at: Optional[datetime] = None


class ActionResponse(BaseModel):
    success: bool
    message: str
    vm_id: str
    action: str
    request_id: Optional[str] = None


# ── Snapshot Schemas ──────────────────────────────────────────────────────────

class SnapshotCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)


class SnapshotResponse(BaseModel):
    id: str
    name: str
    vm_id: str
    status: str
    size: Optional[int] = None  # GB
    description: Optional[str] = None
    metadata: Dict[str, str] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SnapshotListResponse(BaseModel):
    snapshots: List[SnapshotResponse]
    total: int


# ── Flavor / Image Schemas ────────────────────────────────────────────────────

class FlavorResponse(BaseModel):
    id: str
    name: str
    vcpus: int
    ram_mb: int
    disk_gb: int
    ephemeral_gb: int = 0
    swap_mb: int = 0
    is_public: bool = True
    rxtx_factor: float = 1.0


class ImageResponse(BaseModel):
    id: str
    name: str
    status: str
    size: Optional[int] = None
    disk_format: Optional[str] = None
    container_format: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    min_disk: int = 0
    min_ram: int = 0
    tags: List[str] = []


# ── Metrics ───────────────────────────────────────────────────────────────────

class VMMetrics(BaseModel):
    vm_id: str
    cpu_util_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_read_bytes: int
    disk_write_bytes: int
    network_in_bytes: int
    network_out_bytes: int
    timestamp: datetime


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str
    type: Optional[str] = None
    vm_id: Optional[str] = None
    request_id: Optional[str] = None


# ── New Action Schemas (SDK-complete) ─────────────────────────────────────────

class LockRequest(BaseModel):
    locked_reason: Optional[str] = Field(
        None, max_length=255,
        description="Human-readable reason for locking the VM",
    )
    model_config = {"json_schema_extra": {"example": {"locked_reason": "Maintenance window"}}}


class RescueRequest(BaseModel):
    admin_pass: Optional[str] = Field(None, description="Admin password for rescued server")
    image_ref: Optional[str] = Field(None, description="Image ID to boot into rescue mode")


class MigrateRequest(BaseModel):
    host: Optional[str] = Field(None, description="Target compute host (blank = scheduler decides)")


class LiveMigrateRequest(BaseModel):
    host: Optional[str] = Field(None, description="Target host for live migration")
    block_migration: Optional[bool] = Field(None, description="Move disk too (auto-detect if None)")
    force: bool = Field(False, description="Bypass scheduler validation (admin only)")


class EvacuateRequest(BaseModel):
    host: Optional[str] = Field(None, description="Target host to evacuate to")
    admin_pass: Optional[str] = Field(None, description="Admin password for evacuated server")
    force: bool = Field(False, description="Bypass scheduler host validation")


class BackupRequest(BaseModel):
    name: str = Field(..., description="Name of the backup image")
    backup_type: str = Field(..., description="Backup type: 'daily' or 'weekly'")
    rotation: int = Field(..., ge=1, description="Max backups to keep. Oldest deleted when exceeded.")
    model_config = {"json_schema_extra": {
        "example": {"name": "web-server-backup", "backup_type": "daily", "rotation": 7}
    }}


class SecurityGroupRequest(BaseModel):
    name: str = Field(..., description="Security group name or ID to add/remove")
    model_config = {"json_schema_extra": {"example": {"name": "web-sg"}}}


class FloatingIPRequest(BaseModel):
    address: str = Field(..., description="Floating IP address to attach/detach")
    fixed_address: Optional[str] = Field(
        None, description="Fixed IP to associate with (needed when VM has multiple interfaces)"
    )
    model_config = {"json_schema_extra": {"example": {"address": "203.0.113.42"}}}


class MetadataResponse(BaseModel):
    vm_id: str
    metadata: Dict[str, str]


class MetadataDeleteRequest(BaseModel):
    keys: List[str] = Field(..., description="List of metadata keys to delete")
    model_config = {"json_schema_extra": {"example": {"keys": ["env", "team"]}}}
