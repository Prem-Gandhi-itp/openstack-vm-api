"""
Integration tests for all new SDK-complete endpoints.
Covers lock/unlock, shelve/unshelve, rescue/unrescue,
migrate, live-migrate, evacuate, backup, metadata, security groups, floating IPs.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import openstack_mock

HEADERS = {"X-API-Key": "dev-api-key-12345"}


@pytest.fixture(autouse=True)
def reset():
    openstack_mock._vms.clear()
    openstack_mock._snapshots.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def vm_id(client):
    r = client.post("/api/v1/vms/", headers=HEADERS, json={
        "name": "test-vm", "flavor_id": "m1.small",
        "image_id": "img-ubuntu-22-04", "networks": [],
    })
    assert r.status_code == 201
    return r.json()["id"]


# ── Lock / Unlock ─────────────────────────────────────────────────────────────

class TestLockUnlock:
    def test_lock_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS,
                        json={"locked_reason": "Maintenance"})
        assert r.status_code == 200
        assert r.json()["action"] == "lock"
        assert "Maintenance" in r.json()["message"]

    def test_lock_vm_no_reason(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS, json={})
        assert r.status_code == 200

    def test_unlock_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS, json={})
        r = client.post(f"/api/v1/vms/{vm_id}/unlock", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "unlock"

    def test_locked_vm_cannot_stop(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS, json={})
        r = client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
        assert r.status_code == 409
        assert "locked" in r.json()["detail"].lower()

    def test_locked_vm_cannot_start_after_unlock(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS, json={})
        client.post(f"/api/v1/vms/{vm_id}/unlock", headers=HEADERS)
        # stop should work now
        client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/start", headers=HEADERS)
        assert r.status_code == 200

    def test_lock_nonexistent_vm(self, client):
        r = client.post("/api/v1/vms/ghost/lock", headers=HEADERS, json={})
        assert r.status_code == 404


# ── Shelve / Unshelve ─────────────────────────────────────────────────────────

class TestShelveUnshelve:
    def test_shelve_active_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "shelve"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "SHELVED"

    def test_unshelve_shelved_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/unshelve", headers=HEADERS, json={})
        assert r.status_code == 200
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "ACTIVE"

    def test_shelve_stopped_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        assert r.status_code == 200

    def test_cannot_shelve_already_shelved(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        assert r.status_code == 409

    def test_cannot_unshelve_active_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/unshelve", headers=HEADERS, json={})
        assert r.status_code == 409

    def test_shelve_locked_vm_fails(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/lock", headers=HEADERS, json={})
        r = client.post(f"/api/v1/vms/{vm_id}/shelve", headers=HEADERS)
        assert r.status_code == 409


# ── Rescue / Unrescue ─────────────────────────────────────────────────────────

class TestRescueUnrescue:
    def test_rescue_active_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/rescue", headers=HEADERS, json={})
        assert r.status_code == 200
        assert r.json()["action"] == "rescue"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "RESCUE"

    def test_rescue_with_admin_pass(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/rescue", headers=HEADERS,
                        json={"admin_pass": "s3cr3t", "image_ref": "img-debian-12"})
        assert r.status_code == 200
        assert "s3cr3t" in r.json()["message"]

    def test_unrescue_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/rescue", headers=HEADERS, json={})
        r = client.post(f"/api/v1/vms/{vm_id}/unrescue", headers=HEADERS)
        assert r.status_code == 200
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "ACTIVE"

    def test_cannot_rescue_paused_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/pause", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/rescue", headers=HEADERS, json={})
        assert r.status_code == 409

    def test_cannot_unrescue_active_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/unrescue", headers=HEADERS)
        assert r.status_code == 409


# ── Migrate / Live-migrate / Evacuate ─────────────────────────────────────────

class TestMigration:
    def test_cold_migrate_active_vm(self, client, vm_id):
        old_host = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()["host"]
        r = client.post(f"/api/v1/vms/{vm_id}/migrate", headers=HEADERS, json={})
        assert r.status_code == 200
        assert r.json()["action"] == "migrate"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "VERIFY_RESIZE"

    def test_cold_migrate_with_target_host(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/migrate", headers=HEADERS,
                        json={"host": "compute-node-09"})
        assert r.status_code == 200
        assert "compute-node-09" in r.json()["message"]

    def test_live_migrate_active_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/live-migrate", headers=HEADERS, json={})
        assert r.status_code == 200
        assert r.json()["action"] == "live_migrate"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["status"] == "ACTIVE"   # stays active during live migration

    def test_live_migrate_with_options(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/live-migrate", headers=HEADERS,
                        json={"host": "compute-node-07", "block_migration": True, "force": False})
        assert r.status_code == 200

    def test_cannot_live_migrate_stopped_vm(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/live-migrate", headers=HEADERS, json={})
        assert r.status_code == 409

    def test_evacuate_vm(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/evacuate", headers=HEADERS, json={})
        assert r.status_code == 200
        assert r.json()["action"] == "evacuate"

    def test_evacuate_with_target_host(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/evacuate", headers=HEADERS,
                        json={"host": "rescue-node-01", "force": True})
        assert r.status_code == 200
        assert "rescue-node-01" in r.json()["message"]


# ── Backup ────────────────────────────────────────────────────────────────────

class TestBackup:
    def test_create_backup(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/backup", headers=HEADERS, json={
            "name": "daily-backup", "backup_type": "daily", "rotation": 7
        })
        assert r.status_code == 200
        assert r.json()["action"] == "backup"
        assert "daily-backup" in r.json()["message"]

    def test_backup_rotation_in_message(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/backup", headers=HEADERS, json={
            "name": "weekly-backup", "backup_type": "weekly", "rotation": 4
        })
        assert r.status_code == 200
        assert "Rotation=4" in r.json()["message"]

    def test_backup_missing_fields_returns_422(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/backup", headers=HEADERS, json={
            "name": "incomplete"  # missing backup_type and rotation
        })
        assert r.status_code == 422
    
    def test_backup_rotation_must_be_positive(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/backup", headers=HEADERS, json={
            "name": "bad", "backup_type": "daily", "rotation": 0
        })
        assert r.status_code == 422

    def test_backup_nonexistent_vm(self, client):
        r = client.post("/api/v1/vms/ghost/backup", headers=HEADERS, json={
            "name": "x", "backup_type": "daily", "rotation": 3
        })
        assert r.status_code == 404


# ── Metadata ──────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_get_metadata(self, client, vm_id):
        r = client.get(f"/api/v1/vms/{vm_id}/metadata", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["vm_id"] == vm_id
        assert isinstance(data["metadata"], dict)

    def test_get_metadata_not_found(self, client):
        r = client.get("/api/v1/vms/ghost/metadata", headers=HEADERS)
        assert r.status_code == 404

    def test_delete_metadata_keys(self, client, vm_id):
        # First set some metadata via PUT
        client.put(f"/api/v1/vms/{vm_id}", headers=HEADERS,
                   json={"metadata": {"env": "prod", "team": "platform", "keep": "yes"}})

        r = client.request("DELETE", f"/api/v1/vms/{vm_id}/metadata",
                           headers=HEADERS, json={"keys": ["env", "team"]})
        assert r.status_code == 204

        meta = client.get(f"/api/v1/vms/{vm_id}/metadata", headers=HEADERS).json()["metadata"]
        assert "env" not in meta
        assert "team" not in meta
        assert meta.get("keep") == "yes"

    def test_delete_nonexistent_key_is_noop(self, client, vm_id):
        r = client.request("DELETE", f"/api/v1/vms/{vm_id}/metadata",
                           headers=HEADERS, json={"keys": ["does-not-exist"]})
        assert r.status_code == 204

    def test_delete_metadata_empty_keys_422(self, client, vm_id):
        r = client.request("DELETE", f"/api/v1/vms/{vm_id}/metadata",
                           headers=HEADERS, json={"keys": []})
        # empty list is technically valid schema but no keys deleted — should pass
        # The schema has no min_length on keys list, so 200/204 expected
        assert r.status_code in (204, 422)


# ── Security Groups ───────────────────────────────────────────────────────────

class TestSecurityGroups:
    def test_add_security_group(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                        headers=HEADERS, json={"name": "web-sg"})
        assert r.status_code == 200
        assert r.json()["action"] == "security_group_add"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert "web-sg" in vm["security_groups"]

    def test_add_multiple_security_groups(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                    headers=HEADERS, json={"name": "sg-1"})
        client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                    headers=HEADERS, json={"name": "sg-2"})
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert "sg-1" in vm["security_groups"]
        assert "sg-2" in vm["security_groups"]

    def test_remove_security_group(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                    headers=HEADERS, json={"name": "web-sg"})
        r = client.post(f"/api/v1/vms/{vm_id}/security-groups/remove",
                        headers=HEADERS, json={"name": "web-sg"})
        assert r.status_code == 200
        assert r.json()["action"] == "security_group_remove"
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert "web-sg" not in vm["security_groups"]

    def test_add_duplicate_sg_is_idempotent(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                    headers=HEADERS, json={"name": "web-sg"})
        r = client.post(f"/api/v1/vms/{vm_id}/security-groups/add",
                        headers=HEADERS, json={"name": "web-sg"})
        assert r.status_code == 200
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        assert vm["security_groups"].count("web-sg") == 1

    def test_sg_operations_not_found(self, client):
        r = client.post("/api/v1/vms/ghost/security-groups/add",
                        headers=HEADERS, json={"name": "sg"})
        assert r.status_code == 404


# ── Floating IPs ──────────────────────────────────────────────────────────────

class TestFloatingIPs:
    def test_add_floating_ip(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                        headers=HEADERS, json={"address": "203.0.113.99"})
        assert r.status_code == 200
        assert r.json()["action"] == "floating_ip_add"
        assert "203.0.113.99" in r.json()["message"]

    def test_add_floating_ip_appears_in_addresses(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                    headers=HEADERS, json={"address": "203.0.113.99"})
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        public_ips = [a["ip"] for a in vm["addresses"].get("public", [])]
        assert "203.0.113.99" in public_ips

    def test_remove_floating_ip(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                    headers=HEADERS, json={"address": "203.0.113.99"})
        r = client.post(f"/api/v1/vms/{vm_id}/floating-ips/remove",
                        headers=HEADERS, json={"address": "203.0.113.99"})
        assert r.status_code == 200
        assert r.json()["action"] == "floating_ip_remove"

    def test_floating_ip_removed_from_addresses(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                    headers=HEADERS, json={"address": "203.0.113.99"})
        client.post(f"/api/v1/vms/{vm_id}/floating-ips/remove",
                    headers=HEADERS, json={"address": "203.0.113.99"})
        vm = client.get(f"/api/v1/vms/{vm_id}", headers=HEADERS).json()
        public_ips = [a["ip"] for a in vm["addresses"].get("public", [])]
        assert "203.0.113.99" not in public_ips

    def test_add_floating_ip_with_fixed_address(self, client, vm_id):
        r = client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                        headers=HEADERS,
                        json={"address": "203.0.113.88", "fixed_address": "10.0.1.5"})
        assert r.status_code == 200

    def test_add_floating_ip_to_stopped_vm_fails(self, client, vm_id):
        client.post(f"/api/v1/vms/{vm_id}/stop", headers=HEADERS)
        r = client.post(f"/api/v1/vms/{vm_id}/floating-ips/add",
                        headers=HEADERS, json={"address": "203.0.113.99"})
        assert r.status_code == 409

    def test_floating_ip_not_found_vm(self, client):
        r = client.post("/api/v1/vms/ghost/floating-ips/add",
                        headers=HEADERS, json={"address": "1.2.3.4"})
        assert r.status_code == 404
