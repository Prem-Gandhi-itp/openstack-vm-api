"""
Integration tests — spins up the real FastAPI app with TestClient.
Tests the full HTTP request/response cycle including auth, validation,
routing, and error handling.

Run: pytest tests/integration/test_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import openstack_mock

VALID_KEY = "dev-api-key-12345"
HEADERS = {"X-API-Key": VALID_KEY}


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the in-memory VM store before each test."""
    openstack_mock._vms.clear()
    openstack_mock._snapshots.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def vm_id(client):
    """Creates a VM and returns its ID for use in other tests."""
    resp = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "test-vm",
        "flavor_id": "m1.small",
        "image_id": "img-ubuntu-22-04",
        "networks": [],
        "security_groups": ["default"],
        "metadata": {},
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Auth Tests ────────────────────────────────────────────────────────────────

def test_missing_api_key_returns_401(client):
    resp = client.get("/api/v1/vms/")
    assert resp.status_code == 401


def test_invalid_api_key_returns_403(client):
    resp = client.get("/api/v1/vms/", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403


def test_valid_api_key_passes(client):
    resp = client.get("/api/v1/vms/", headers=HEADERS)
    assert resp.status_code == 200


# ── Health Check ──────────────────────────────────────────────────────────────

def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()


# ── VM List ───────────────────────────────────────────────────────────────────

def test_list_vms_empty(client):
    resp = client.get("/api/v1/vms/", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vms"] == []
    assert data["total"] == 0
    assert data["page"] == 1


def test_list_vms_pagination_params(client, vm_id):
    resp = client.get("/api/v1/vms/?page=1&page_size=5", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "has_next" in data
    assert data["page_size"] == 5


def test_list_vms_invalid_page_size(client):
    resp = client.get("/api/v1/vms/?page_size=999", headers=HEADERS)
    assert resp.status_code == 422  # Pydantic validation error


def test_list_vms_status_filter(client, vm_id):
    # Stop the VM
    client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)

    resp = client.get("/api/v1/vms/?status=SHUTOFF", headers=HEADERS)
    assert resp.status_code == 200
    vms = resp.json()["vms"]
    assert all(v["status"] == "SHUTOFF" for v in vms)


# ── VM Create ─────────────────────────────────────────────────────────────────

def test_create_vm_success(client):
    resp = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "new-vm",
        "flavor_id": "m1.medium",
        "image_id": "img-ubuntu-22-04",
        "networks": [{"network_id": "net-private"}],
        "security_groups": ["default", "web"],
        "metadata": {"env": "staging"},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new-vm"
    assert data["status"] == "ACTIVE"
    assert data["flavor_id"] == "m1.medium"
    assert "id" in data


def test_create_vm_missing_required_field(client):
    resp = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "incomplete-vm",
        # missing flavor_id and image_id
    })
    assert resp.status_code == 422


def test_create_vm_invalid_name(client):
    resp = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "invalid name with spaces!!",
        "flavor_id": "m1.small",
        "image_id": "img-ubuntu-22-04",
    })
    assert resp.status_code == 422


def test_create_vm_count_too_high(client):
    resp = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "bulk-vm",
        "flavor_id": "m1.small",
        "image_id": "img-ubuntu-22-04",
        "count": 99,  # exceeds max of 10
    })
    assert resp.status_code == 422


# ── VM Get ────────────────────────────────────────────────────────────────────

def test_get_vm_success(client, vm_id):
    resp = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == vm_id


def test_get_vm_not_found(client):
    resp = client.get("/api/v1/vms/nonexistent-vm-id", headers=HEADERS)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ── VM Update ─────────────────────────────────────────────────────────────────

def test_update_vm_name(client, vm_id):
    resp = client.put(f"/api/v1/vms/{vm_id}", headers=HEADERS, json={"name": "renamed-vm"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed-vm"


def test_update_vm_metadata(client, vm_id):
    resp = client.put(f"/api/v1/vms/{vm_id}", headers=HEADERS, json={"metadata": {"cost_center": "eng"}})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["cost_center"] == "eng"


def test_update_nonexistent_vm(client):
    resp = client.put("/api/v1/vms/ghost", headers=HEADERS, json={"name": "x"})
    assert resp.status_code == 404


# ── VM Delete ─────────────────────────────────────────────────────────────────

def test_delete_vm_success(client, vm_id):
    resp = client.delete(f"/api/v1/vms/{vm_id}", headers=HEADERS)
    assert resp.status_code == 204

    get_resp = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS)
    assert get_resp.status_code == 404


def test_delete_nonexistent_vm(client):
    resp = client.delete("/api/v1/vms/ghost-id", headers=HEADERS)
    assert resp.status_code == 404


# ── Lifecycle Actions ─────────────────────────────────────────────────────────

def test_stop_active_vm(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["action"] == "stop"


def test_start_stopped_vm(client, vm_id):
    client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    resp = client.post(f"/api/v1/vms/{vm_id}/start", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["action"] == "start"


def test_stop_already_stopped_returns_409(client, vm_id):
    client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    resp = client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    assert resp.status_code == 409


def test_reboot_soft(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/reboot", headers=HEADERS, json={"type": "SOFT"})
    assert resp.status_code == 200
    assert "SOFT" in resp.json()["message"]


def test_reboot_hard(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/reboot", headers=HEADERS, json={"type": "HARD"})
    assert resp.status_code == 200


def test_suspend_resume_cycle(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/suspend", headers=HEADERS)
    assert resp.status_code == 200

    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "SUSPENDED"

    resp = client.post(f"/api/v1/vms/{vm_id}/resume", headers=HEADERS)
    assert resp.status_code == 200

    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "ACTIVE"


def test_pause_unpause_cycle(client, vm_id):
    client.post(f"/api/v1/vms/{vm_id}/pause", headers=HEADERS)
    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "PAUSED"

    client.post(f"/api/v1/vms/{vm_id}/unpause", headers=HEADERS)
    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "ACTIVE"


def test_resize_and_confirm(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/resize", headers=HEADERS, json={"flavor_id": "m1.large"})
    assert resp.status_code == 200

    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "VERIFY_RESIZE"
    assert vm["flavor_id"] == "m1.large"

    resp = client.post(f"/api/v1/vms/{vm_id}/resize/confirm", headers=HEADERS)
    assert resp.status_code == 200
    vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    assert vm["status"] == "ACTIVE"


def test_console_active_vm(client, vm_id):
    resp = client.get(f"/api/v1/vms/{vm_id}/console", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert data["url"].startswith("http")


def test_console_stopped_vm_returns_409(client, vm_id):
    client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    resp = client.get(f"/api/v1/vms/{vm_id}/console", headers=HEADERS)
    assert resp.status_code == 409


def test_get_metrics(client, vm_id):
    resp = client.get(f"/api/v1/vms/{vm_id}/metrics", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vm_id"] == vm_id
    assert "cpu_util_percent" in data
    assert "memory_used_mb" in data


# ── Snapshot Tests ────────────────────────────────────────────────────────────

def test_create_and_list_snapshot(client, vm_id):
    resp = client.post(f"/api/v1/vms/{vm_id}/snapshots", headers=HEADERS, json={
        "name": "my-snapshot",
        "description": "Before upgrade",
        "metadata": {"reason": "upgrade"},
    })
    assert resp.status_code == 201
    snap = resp.json()
    assert snap["name"] == "my-snapshot"
    assert snap["vm_id"] == vm_id

    list_resp = client.get(f"/api/v1/vms/{vm_id}/snapshots", headers=HEADERS)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


def test_delete_snapshot(client, vm_id):
    snap = client.post(f"/api/v1/vms/{vm_id}/snapshots", headers=HEADERS, json={"name": "to-delete"}).json()
    del_resp = client.delete(f"/api/v1/vms/{vm_id}/snapshots/{snap['id']}", headers=HEADERS)
    assert del_resp.status_code == 204

    list_resp = client.get(f"/api/v1/vms/{vm_id}/snapshots", headers=HEADERS)
    assert list_resp.json()["total"] == 0


def test_snapshot_vm_not_found(client):
    resp = client.post("/api/v1/vms/ghost/snapshots", headers=HEADERS, json={"name": "snap"})
    assert resp.status_code == 404


# ── Catalog Tests ─────────────────────────────────────────────────────────────

def test_list_flavors(client):
    resp = client.get("/api/v1/catalog/flavors", headers=HEADERS)
    assert resp.status_code == 200
    flavors = resp.json()
    assert len(flavors) >= 4
    assert any(f["name"] == "m1.small" for f in flavors)


def test_list_images(client):
    resp = client.get("/api/v1/catalog/images", headers=HEADERS)
    assert resp.status_code == 200
    images = resp.json()
    assert len(images) >= 1
    assert any("Ubuntu" in i["name"] for i in images)


# ── Response Shape Tests ──────────────────────────────────────────────────────

def test_vm_response_has_required_fields(client, vm_id):
    resp = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
    required = ["id", "name", "status", "flavor_id", "image_id", "created_at", "updated_at"]
    for field in required:
        assert field in resp, f"Missing field: {field}"


def test_action_response_has_request_id(client, vm_id):
    client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
    resp = client.post(f"/api/v1/vms/{vm_id}/start", headers=HEADERS).json()
    assert "request_id" in resp
    assert resp["request_id"] is not None


def test_process_time_header_present(client):
    resp = client.get("/health")
    assert "x-process-time" in resp.headers
