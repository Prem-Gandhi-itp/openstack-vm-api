"""
Unit tests for the MockOpenStackService (and by extension, any real service
that satisfies the same interface).

Run: pytest tests/unit/test_vm_service.py -v
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.services.openstack_mock import MockOpenStackService
from app.core.exceptions import (
    VMNotFoundError,
    InvalidVMStateError,
    SnapshotNotFoundError,
    QuotaExceededError,
)


@pytest.fixture
def service():
    """Fresh service instance with a clean in-memory store for each test."""
    svc = MockOpenStackService()
    # Clear the module-level stores so tests are isolated
    from app.services import openstack_mock
    openstack_mock._vms.clear()
    openstack_mock._snapshots.clear()
    return svc


@pytest.fixture
def sample_vm_data():
    return {
        "name": "test-vm-01",
        "flavor_id": "m1.small",
        "image_id": "img-ubuntu-22-04",
        "networks": [],
        "key_name": "my-key",
        "security_groups": ["default"],
        "user_data": None,
        "metadata": {"env": "test"},
        "availability_zone": None,
        "count": 1,
    }


# ── CRUD Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_vm_returns_active(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    assert vm.id is not None
    assert vm.name == "test-vm-01"
    assert vm.status.value == "ACTIVE"
    assert vm.flavor_id == "m1.small"


@pytest.mark.asyncio
async def test_create_vm_sets_timestamps(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    assert isinstance(vm.created_at, datetime)
    assert isinstance(vm.launched_at, datetime)


@pytest.mark.asyncio
async def test_get_vm_existing(service, sample_vm_data):
    created = await service.create_vm(sample_vm_data)
    fetched = await service.get_vm(created.id)
    assert fetched.id == created.id
    assert fetched.name == created.name


@pytest.mark.asyncio
async def test_get_vm_not_found(service):
    with pytest.raises(VMNotFoundError):
        await service.get_vm("nonexistent-id-xyz")


@pytest.mark.asyncio
async def test_list_vms_empty(service):
    result = await service.list_vms()
    assert result["total"] == 0
    assert result["vms"] == []


@pytest.mark.asyncio
async def test_list_vms_pagination(service, sample_vm_data):
    for i in range(5):
        data = {**sample_vm_data, "name": f"vm-{i:02d}"}
        await service.create_vm(data)
    page1 = await service.list_vms(page=1, page_size=3)
    assert len(page1["vms"]) == 3
    assert page1["total"] == 5
    assert page1["has_next"] is True

    page2 = await service.list_vms(page=2, page_size=3)
    assert len(page2["vms"]) == 2
    assert page2["has_next"] is False


@pytest.mark.asyncio
async def test_list_vms_status_filter(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.stop_vm(vm.id)

    active_result = await service.list_vms(status="ACTIVE")
    shutoff_result = await service.list_vms(status="SHUTOFF")

    assert all(v.status.value == "ACTIVE" for v in active_result["vms"])
    assert any(v.id == vm.id for v in shutoff_result["vms"])


@pytest.mark.asyncio
async def test_update_vm_name(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    updated = await service.update_vm(vm.id, {"name": "renamed-vm"})
    assert updated.name == "renamed-vm"


@pytest.mark.asyncio
async def test_update_vm_metadata(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    updated = await service.update_vm(vm.id, {"metadata": {"key": "value"}})
    assert updated.metadata["key"] == "value"
    assert updated.metadata["env"] == "test"  # original metadata preserved


@pytest.mark.asyncio
async def test_delete_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.delete_vm(vm.id)
    with pytest.raises(VMNotFoundError):
        await service.get_vm(vm.id)


@pytest.mark.asyncio
async def test_delete_nonexistent_vm(service):
    with pytest.raises(VMNotFoundError):
        await service.delete_vm("ghost-vm-id")


# ── Lifecycle Action Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_active_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    assert vm.status.value == "ACTIVE"
    await service.stop_vm(vm.id)
    stopped = await service.get_vm(vm.id)
    assert stopped.status.value == "SHUTOFF"


@pytest.mark.asyncio
async def test_start_stopped_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.stop_vm(vm.id)
    await service.start_vm(vm.id)
    started = await service.get_vm(vm.id)
    assert started.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_cannot_stop_already_stopped_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.stop_vm(vm.id)
    with pytest.raises(InvalidVMStateError) as exc_info:
        await service.stop_vm(vm.id)
    assert exc_info.value.current_state == "SHUTOFF"


@pytest.mark.asyncio
async def test_cannot_start_active_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    with pytest.raises(InvalidVMStateError):
        await service.start_vm(vm.id)


@pytest.mark.asyncio
async def test_reboot_active_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.reboot_vm(vm.id, reboot_type="SOFT")
    rebooted = await service.get_vm(vm.id)
    assert rebooted.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_hard_reboot(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.reboot_vm(vm.id, reboot_type="HARD")
    rebooted = await service.get_vm(vm.id)
    assert rebooted.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_suspend_and_resume(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.suspend_vm(vm.id)
    suspended = await service.get_vm(vm.id)
    assert suspended.status.value == "SUSPENDED"

    await service.resume_vm(vm.id)
    resumed = await service.get_vm(vm.id)
    assert resumed.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_pause_and_unpause(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.pause_vm(vm.id)
    paused = await service.get_vm(vm.id)
    assert paused.status.value == "PAUSED"

    await service.unpause_vm(vm.id)
    unpaused = await service.get_vm(vm.id)
    assert unpaused.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_resize_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.resize_vm(vm.id, "m1.large")
    resized = await service.get_vm(vm.id)
    assert resized.status.value == "VERIFY_RESIZE"
    assert resized.flavor_id == "m1.large"


@pytest.mark.asyncio
async def test_confirm_resize(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.resize_vm(vm.id, "m1.large")
    await service.confirm_resize(vm.id)
    confirmed = await service.get_vm(vm.id)
    assert confirmed.status.value == "ACTIVE"


@pytest.mark.asyncio
async def test_get_console_active_vm(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    console = await service.get_console(vm.id)
    assert console.url.startswith("http")
    assert "token=" in console.url


@pytest.mark.asyncio
async def test_get_console_stopped_vm_raises(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    await service.stop_vm(vm.id)
    with pytest.raises(InvalidVMStateError):
        await service.get_console(vm.id)


# ── Snapshot Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_snapshot(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    snap = await service.create_snapshot(vm.id, "snap-01", "Test snapshot", {})
    assert snap.id is not None
    assert snap.vm_id == vm.id
    assert snap.name == "snap-01"
    assert snap.status == "active"

    snaps = await service.list_snapshots(vm.id)
    assert len(snaps) == 1
    assert snaps[0].id == snap.id


@pytest.mark.asyncio
async def test_delete_snapshot(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    snap = await service.create_snapshot(vm.id, "snap-to-delete", None, {})
    await service.delete_snapshot(vm.id, snap.id)
    remaining = await service.list_snapshots(vm.id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_snapshot(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    with pytest.raises(SnapshotNotFoundError):
        await service.delete_snapshot(vm.id, "no-such-snap")


@pytest.mark.asyncio
async def test_snapshot_of_nonexistent_vm(service):
    with pytest.raises(VMNotFoundError):
        await service.create_snapshot("no-vm", "snap", None, {})


# ── Metrics Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_metrics(service, sample_vm_data):
    vm = await service.create_vm(sample_vm_data)
    metrics = await service.get_vm_metrics(vm.id)
    assert metrics.vm_id == vm.id
    assert 0 <= metrics.cpu_util_percent <= 100
    assert metrics.memory_total_mb > 0


@pytest.mark.asyncio
async def test_get_metrics_not_found(service):
    with pytest.raises(VMNotFoundError):
        await service.get_vm_metrics("missing-id")


# ── Catalog Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_flavors(service):
    flavors = await service.list_flavors()
    assert len(flavors) >= 4
    names = [f.name for f in flavors]
    assert "m1.small" in names
    assert "m1.large" in names


@pytest.mark.asyncio
async def test_list_images(service):
    images = await service.list_images()
    assert len(images) >= 1
    assert any("Ubuntu" in i.name for i in images)
