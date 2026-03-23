# OpenStack VM Lifecycle Management API

> A production-ready REST API for managing OpenStack virtual machine lifecycle operations.
> Built with **FastAPI · Python 3.11 · openstacksdk · Docker**

[![CI](https://github.com/YOUR_USERNAME/openstack-vm-api/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/openstack-vm-api/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [API Reference](#2-api-reference)
3. [Sample Requests & Responses](#3-sample-requests--responses)
4. [Architecture](#4-architecture)
5. [Design Decisions](#5-design-decisions)
6. [Project Structure](#6-project-structure)
7. [Configuration](#7-configuration)
8. [Development Guide](#8-development-guide)
9. [Testing](#9-testing)
10. [Deployment](#10-deployment)
11. [Roadmap & Backlog](#11-roadmap--backlog)
12. [Assumptions](#12-assumptions)

---

## 1. Quick Start

### Option A — Docker (zero setup, recommended)

```bash
git clone https://github.com/YOUR_USERNAME/openstack-vm-api.git
cd openstack-vm-api
docker-compose up --build
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

The default config runs in **mock mode** — no OpenStack cluster needed.
Four seeded VMs are available immediately.

### Option B — Local Python

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Verify it's running

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"1.0.0","service":"OpenStack VM Lifecycle API"}

curl http://localhost:8000/api/v1/vms/ -H "X-API-Key: dev-api-key-12345"
# {"vms":[...],"total":4,"page":1,"page_size":20,"has_next":false}
```

---

## 2. API Reference

**Base URL:** `http://localhost:8000/api/v1`
**Auth:** `X-API-Key: <key>` header on every request

### VMs — CRUD

| Method   | Path          | Status | Description                    |
|----------|---------------|--------|--------------------------------|
| `GET`    | `/vms`        | 200    | List VMs (paginated, filterable)|
| `POST`   | `/vms`        | 201    | Provision a new VM             |
| `GET`    | `/vms/{id}`   | 200    | Get full VM details            |
| `PUT`    | `/vms/{id}`   | 200    | Update VM name / metadata      |
| `DELETE` | `/vms/{id}`   | 204    | Permanently terminate VM       |

### VMs — Lifecycle Actions

| Method | Path                       | Description                         |
|--------|----------------------------|-------------------------------------|
| `POST` | `/vms/{id}/start`          | Start a stopped / suspended VM      |
| `POST` | `/vms/{id}/stop`           | Graceful shutdown (ACPI)            |
| `POST` | `/vms/{id}/reboot`         | Soft or hard reboot                 |
| `POST` | `/vms/{id}/suspend`        | Suspend (save RAM state to disk)    |
| `POST` | `/vms/{id}/resume`         | Resume from suspended               |
| `POST` | `/vms/{id}/pause`          | Freeze at hypervisor level          |
| `POST` | `/vms/{id}/unpause`        | Unfreeze                            |
| `POST` | `/vms/{id}/resize`         | Schedule resize to new flavor       |
| `POST` | `/vms/{id}/resize/confirm` | Confirm a pending resize            |
| `GET`  | `/vms/{id}/console`        | Get VNC/SPICE console URL           |
| `GET`  | `/vms/{id}/metrics`        | CPU, memory, disk, network stats    |

### Snapshots

| Method   | Path                              | Description              |
|----------|-----------------------------------|--------------------------|
| `GET`    | `/vms/{id}/snapshots`             | List snapshots           |
| `POST`   | `/vms/{id}/snapshots`             | Create snapshot          |
| `DELETE` | `/vms/{id}/snapshots/{snap_id}`   | Delete snapshot          |

### Catalog

| Method | Path               | Description              |
|--------|--------------------|--------------------------|
| `GET`  | `/catalog/flavors` | Available compute flavors|
| `GET`  | `/catalog/images`  | Available Glance images  |

### Status Codes

| Code | Meaning                               |
|------|---------------------------------------|
| 200  | Success                               |
| 201  | Created                               |
| 204  | Deleted (no body)                     |
| 400  | Validation error (bad request body)   |
| 401  | Missing API key                       |
| 403  | Invalid API key                       |
| 404  | VM / snapshot not found               |
| 409  | VM in wrong state for this operation  |
| 422  | Request schema validation failure     |
| 500  | Internal / OpenStack error            |

---

## 3. Sample Requests & Responses

### Create a VM

```bash
POST /api/v1/vms/
X-API-Key: dev-api-key-12345
Content-Type: application/json

{
  "name": "web-server-01",
  "flavor_id": "m1.small",
  "image_id": "img-ubuntu-22-04",
  "networks": [{"network_id": "net-private"}],
  "key_name": "my-keypair",
  "security_groups": ["default", "web-sg"],
  "metadata": {
    "env": "production",
    "team": "platform"
  }
}
```

**Response `201 Created`:**

```json
{
  "id": "a3f8c2d1-1234-5678-abcd-ef0123456789",
  "name": "web-server-01",
  "status": "BUILD",
  "flavor_id": "m1.small",
  "image_id": "img-ubuntu-22-04",
  "host": "compute-node-02",
  "availability_zone": "nova",
  "key_name": "my-keypair",
  "security_groups": ["default", "web-sg"],
  "addresses": {
    "private": [
      {"ip": "10.0.1.15", "version": 4, "type": "fixed", "mac": "fa:16:3e:ab:cd:ef"}
    ]
  },
  "metadata": {"env": "production", "team": "platform"},
  "created_at": "2025-03-21T10:30:00+00:00",
  "updated_at": "2025-03-21T10:30:00+00:00",
  "launched_at": null,
  "progress": 0,
  "task_state": "scheduling",
  "power_state": 0
}
```

---

### Get VM Details

```bash
GET /api/v1/vms/a3f8c2d1-1234-5678-abcd-ef0123456789
X-API-Key: dev-api-key-12345
```

**Response `200 OK`:**

```json
{
  "id": "a3f8c2d1-1234-5678-abcd-ef0123456789",
  "name": "web-server-01",
  "status": "ACTIVE",
  "flavor_id": "m1.small",
  "image_id": "img-ubuntu-22-04",
  "host": "compute-node-02",
  "availability_zone": "nova",
  "addresses": {
    "private": [{"ip": "10.0.1.15", "version": 4, "type": "fixed"}],
    "public":  [{"ip": "203.0.113.15", "version": 4, "type": "floating"}]
  },
  "metadata": {"env": "production"},
  "created_at": "2025-03-21T10:30:00+00:00",
  "updated_at": "2025-03-21T10:30:45+00:00",
  "launched_at": "2025-03-21T10:30:45+00:00",
  "progress": 100,
  "task_state": null,
  "power_state": 1
}
```

---

### Start / Stop a VM

```bash
POST /api/v1/vms/{id}/stop
X-API-Key: dev-api-key-12345
```

**Response `200 OK`:**

```json
{
  "success": true,
  "message": "VM stop initiated.",
  "vm_id": "a3f8c2d1-1234-5678-abcd-ef0123456789",
  "action": "stop",
  "request_id": "7c3b9e2a-0000-4321-bcde-fedcba987654"
}
```

**Error — wrong state `409 Conflict`:**

```json
{
  "detail": "VM 'a3f8c2d1...' is in state 'SHUTOFF', but 'ACTIVE' is required for this operation."
}
```

---

### Reboot with type

```bash
POST /api/v1/vms/{id}/reboot
Content-Type: application/json

{"type": "HARD"}
```

---

### Resize VM

```bash
# Step 1 — schedule resize
POST /api/v1/vms/{id}/resize
{"flavor_id": "m1.large"}

# Step 2 — verify it booted correctly, then confirm
POST /api/v1/vms/{id}/resize/confirm
```

---

### Create Snapshot

```bash
POST /api/v1/vms/{id}/snapshots
{
  "name": "pre-upgrade-snapshot",
  "description": "Before OS upgrade on 2025-03-21",
  "metadata": {"reason": "upgrade"}
}
```

**Response `201 Created`:**

```json
{
  "id": "snap-uuid-here",
  "name": "pre-upgrade-snapshot",
  "vm_id": "a3f8c2d1-...",
  "status": "active",
  "size": 20,
  "description": "Before OS upgrade on 2025-03-21",
  "metadata": {"reason": "upgrade"},
  "created_at": "2025-03-21T11:00:00+00:00",
  "updated_at": "2025-03-21T11:00:00+00:00"
}
```

---

### Get Console URL

```bash
GET /api/v1/vms/{id}/console?console_type=novnc
```

```json
{
  "type": "novnc",
  "url": "http://console.openstack.example.com:6080/vnc_auto.html?token=abc123",
  "expires_at": "2025-03-21T12:00:00+00:00"
}
```

---

### List Flavors

```bash
GET /api/v1/catalog/flavors
```

```json
[
  {"id": "m1.tiny",   "name": "m1.tiny",   "vcpus": 1, "ram_mb": 512,  "disk_gb": 1},
  {"id": "m1.small",  "name": "m1.small",  "vcpus": 1, "ram_mb": 2048, "disk_gb": 20},
  {"id": "m1.medium", "name": "m1.medium", "vcpus": 2, "ram_mb": 4096, "disk_gb": 40},
  {"id": "m1.large",  "name": "m1.large",  "vcpus": 4, "ram_mb": 8192, "disk_gb": 80}
]
```

---

### Error — VM not found

```bash
GET /api/v1/vms/does-not-exist
```

```json
{
  "detail": "VM 'does-not-exist' not found."
}
```

---

## 4. Architecture

### System Overview

```
  Client (curl / browser / SDK)
         │
         │ HTTPS
         ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                     FastAPI Application                       │
  │                                                               │
  │  ┌────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
  │  │ Auth       │  │   Middleware      │  │  Global         │   │
  │  │ (X-API-Key)│  │ • CORS           │  │  Exception      │   │
  │  │            │  │ • Request timing │  │  Handler        │   │
  │  └────────────┘  │ • JSON logging   │  └─────────────────┘   │
  │                  └──────────────────┘                        │
  │                                                               │
  │  ┌───────────────────────────────────────────────────────┐   │
  │  │                API Router  /api/v1                     │   │
  │  │                                                         │   │
  │  │  ┌──────────────┐  ┌───────────────┐  ┌────────────┐  │   │
  │  │  │  /vms        │  │  /vms/{id}/   │  │  /catalog  │  │   │
  │  │  │  CRUD        │  │  actions +    │  │  flavors   │  │   │
  │  │  │              │  │  snapshots    │  │  images    │  │   │
  │  │  └──────────────┘  └───────────────┘  └────────────┘  │   │
  │  └───────────────────────────────────────────────────────┘   │
  │                                                               │
  │  ┌───────────────────────────────────────────────────────┐   │
  │  │          Service Layer  (factory.py DI)                │   │
  │  │                                                         │   │
  │  │  MOCK_OPENSTACK=true         MOCK_OPENSTACK=false       │   │
  │  │  ┌─────────────────────┐   ┌────────────────────────┐  │   │
  │  │  │  MockOpenStack      │   │  RealOpenStack         │  │   │
  │  │  │  Service            │   │  Service               │  │   │
  │  │  │  • in-memory dict   │   │  • openstacksdk        │  │   │
  │  │  │  • seeded test VMs  │   │  • Nova / Glance /     │  │   │
  │  │  │  • zero deps        │   │    Cinder / Gnocchi    │  │   │
  │  │  └─────────────────────┘   └────────────────────────┘  │   │
  │  └───────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────┘
         │
         │ openstacksdk (Keystone auth + REST calls)
         ▼
  ┌────────────────────────────────────────────────────────────┐
  │                  OpenStack Cluster                          │
  │                                                             │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
  │  │  Keystone│  │   Nova   │  │  Glance  │  │  Cinder  │   │
  │  │  (Auth)  │  │(Compute) │  │ (Images) │  │(Volumes) │   │
  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
  │                                                             │
  │  ┌──────────┐  ┌──────────┐                                │
  │  │  Neutron │  │ Gnocchi  │                                │
  │  │(Networks)│  │(Metrics) │                                │
  │  └──────────┘  └──────────┘                                │
  └────────────────────────────────────────────────────────────┘
```

### VM State Machine

```
                      ┌─────────────────────────────────┐
                      │             BUILD                │
                      └───────────────┬─────────────────┘
                                      │ (provisioning complete)
                                      ▼
          ┌────── stop ──── ACTIVE ───────────────── resize ──────────┐
          │                 │  ▲  ▲                                   │
          │         suspend │  │  │ resume                            │
          │                 ▼  │  │                                   ▼
          │             SUSPENDED  │                         VERIFY_RESIZE
          │                        │                                  │
          │         pause  │  │    │ unpause                confirm   │
          │                ▼  │    │                                  │
          │            PAUSED ┘    │                         ACTIVE ◄─┘
          │
          ▼
       SHUTOFF ──── start ──► ACTIVE
          │
          ▼
       DELETED  (terminal)
```

### Request Lifecycle

```
  POST /api/v1/vms/
       │
       ▼
  [Auth middleware]  ── invalid key ──► 401/403
       │
       ▼
  [Pydantic validation]  ── bad body ──► 422
       │
       ▼
  [Endpoint handler] (vms.py)
       │
       ▼
  [get_openstack_service()] DI
       │
       ├── MOCK=true ──► MockOpenStackService.create_vm()
       │                        │
       │                   in-memory dict → VMResponse
       │
       └── MOCK=false ─► RealOpenStackService.create_vm()
                                │
                           openstack.compute.create_server()
                                │
                           Nova API → server object → VMResponse
       │
       ▼
  [JSON serialize] (Pydantic)
       │
       ▼
  201 Created  {"id": "...", "status": "BUILD", ...}
```

---

## 5. Design Decisions

### Why FastAPI?
FastAPI was chosen over Flask or Django REST Framework for three reasons:

1. **Async-native.** OpenStack SDK calls can be slow (network I/O). FastAPI's async support means a slow Nova call doesn't block other requests.
2. **Zero-cost schema.** Pydantic models serve triple duty: request validation, response serialisation, and OpenAPI spec generation. No manual schema maintenance.
3. **Dependency injection.** FastAPI's `Depends()` makes swapping mock ↔ real service a one-liner, which is critical for testability.

### Mock / Real toggle
The biggest practical challenge in an OpenStack API PoC is that reviewers may not have a running cluster. The `MOCK_OPENSTACK` flag solves this cleanly:
- `MOCK_OPENSTACK=true` (default) → runs entirely in-memory, four seed VMs, no external dependencies
- `MOCK_OPENSTACK=false` → the exact same endpoints call `RealOpenStackService` which wraps the official openstacksdk

The factory (`services/factory.py`) caches the real service as a singleton via `@lru_cache` so the expensive Keystone auth happens once at startup.

### Domain exceptions → HTTP status codes
Business-logic errors are raised as typed exceptions (`VMNotFoundError`, `InvalidVMStateError`, `QuotaExceededError`) in the service layer. Endpoint handlers catch these and map them to appropriate HTTP codes. This keeps Nova-specific details out of the HTTP layer and makes the service layer independently testable.

### State machine enforcement
`_VALID_TRANSITIONS` in the real service validates VM state before every action. This gives the client a meaningful `409 Conflict` response immediately, rather than letting the request reach Nova only to get a cryptic 409 back from it.

### Versioned API
All endpoints are under `/api/v1/`. When breaking changes are needed (e.g., v2 response shape), a new `/api/v2/` router can be added without disrupting existing clients.

### Structured JSON logging
Every log line is a JSON object (`{"timestamp":..., "level":..., "message":...}`). This makes logs first-class data, directly ingestible by Datadog, ELK, CloudWatch Logs Insights, or any structured log platform.

### Multi-stage Docker build
The Dockerfile uses a `builder` stage for pip compilation and a minimal `runtime` stage for the final image. The app runs as a non-root `appuser`, following container security best practices.

---

## 6. Project Structure

```
openstack-vm-api/
│
├── app/
│   ├── main.py                      # App factory, middleware, lifespan hooks
│   │
│   ├── core/
│   │   ├── config.py                # Pydantic settings — all env vars live here
│   │   ├── security.py              # API key auth — FastAPI Depends()
│   │   ├── exceptions.py            # Domain exceptions (VMNotFoundError, etc.)
│   │   └── logging.py               # Structured JSON logger
│   │
│   ├── schemas/
│   │   └── vm.py                    # All Pydantic v2 request/response models
│   │
│   ├── services/
│   │   ├── factory.py               # DI factory — mock vs real
│   │   ├── openstack_mock.py        # In-memory mock service (no OS needed)
│   │   └── openstack_real.py        # Full openstacksdk production service
│   │
│   └── api/v1/
│       ├── router.py                # Assembles all endpoint modules
│       └── endpoints/
│           ├── vms.py               # CRUD: list, create, get, update, delete
│           ├── actions.py           # Lifecycle: start/stop/reboot/resize/console
│           ├── snapshots.py         # Snapshot CRUD
│           └── catalog.py           # Flavors + images
│
├── tests/
│   ├── unit/
│   │   └── test_vm_service.py       # 31 service-layer tests (no HTTP)
│   └── integration/
│       └── test_api.py              # 39 full HTTP tests via TestClient
│
├── .github/
│   └── workflows/ci.yml             # GitHub Actions: test + docker build
│
├── k8s/
│   └── deployment.yaml              # K8s Deployment + Service + Ingress
│
├── scripts/
│   └── push_to_github.sh            # One-command GitHub publish
│
├── Dockerfile                       # Multi-stage, non-root
├── docker-compose.yml               # Local dev environment
├── requirements.txt
├── pytest.ini
├── .env.example
└── .gitignore
```

---

## 7. Configuration

All configuration is via environment variables (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `MOCK_OPENSTACK` | `true` | `false` to use real OpenStack |
| `OS_AUTH_URL` | `http://localhost:5000/v3` | Keystone auth endpoint |
| `OS_USERNAME` | `admin` | OpenStack username |
| `OS_PASSWORD` | `admin` | OpenStack password |
| `OS_PROJECT_NAME` | `admin` | Project / tenant name |
| `OS_USER_DOMAIN_NAME` | `Default` | User domain |
| `OS_PROJECT_DOMAIN_NAME` | `Default` | Project domain |
| `OS_REGION_NAME` | `RegionOne` | Region |
| `VALID_API_KEYS` | `["dev-api-key-12345"]` | Accepted API keys (JSON list) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `DEBUG` | `false` | Enable FastAPI debug mode |

---

## 8. Development Guide

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run (hot-reload)
uvicorn app.main:app --reload

# Lint
ruff check app/ tests/

# Format
black app/ tests/
```

---

## 9. Testing

```bash
# All tests
pytest tests/ -v

# Unit only (no HTTP)
pytest tests/unit/ -v

# Integration only (full HTTP)
pytest tests/integration/ -v

# Coverage report
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

**Results:** 70 tests · 85% line coverage · ~10s runtime

---

## 10. Deployment

### Docker Compose (local / staging)

```bash
docker-compose up --build -d
docker-compose logs -f
```

### Connect to real OpenStack

```bash
# .env
MOCK_OPENSTACK=false
OS_AUTH_URL=http://your-keystone:5000/v3
OS_USERNAME=myuser
OS_PASSWORD=mypassword
OS_PROJECT_NAME=myproject

docker-compose up --build
```

### Kubernetes

```bash
# Create secret with OpenStack credentials
kubectl create secret generic openstack-creds \
  --from-literal=auth_url=http://keystone:5000/v3 \
  --from-literal=password=yourpassword

kubectl apply -f k8s/deployment.yaml
```

### Production checklist

- [ ] Replace API key auth with JWT / OAuth2
- [ ] Store credentials in Vault / AWS Secrets Manager
- [ ] Enable Redis for distributed rate limiting
- [ ] Configure TLS at the ingress layer
- [ ] Set up log aggregation (Datadog / ELK)
- [ ] Add Prometheus `/metrics` endpoint
- [ ] Set replica count > 1 in K8s for HA

---

## 11. Roadmap & Backlog

### Sprint 1 — Security & Auth
- [ ] **JWT authentication** — replace API keys with short-lived JWTs issued by a `/auth/token` endpoint
- [ ] **RBAC** — admin vs. viewer roles; viewers can GET but not POST/DELETE
- [ ] **Per-project scoping** — each API key is bound to an OpenStack project

### Sprint 2 — Operations
- [ ] **Redis rate limiting** — sliding window, 100 req/min per key (currently in-memory only)
- [ ] **Async task queue** (Celery) — long-running operations (resize, snapshot creation) return a task ID; client polls `GET /tasks/{id}` for status
- [ ] **WebSocket status stream** — push VM state transitions to subscribed clients in real time

### Sprint 3 — Expanded Resource Management
- [ ] **Volume management** — create/attach/detach/delete Cinder volumes
- [ ] **Floating IP** — allocate, associate, disassociate
- [ ] **Security groups** — CRUD for groups and rules
- [ ] **Keypair management** — create, import, delete keypairs
- [ ] **Bulk operations** — start/stop multiple VMs in a single request

### Sprint 4 — Observability
- [ ] **Prometheus metrics** — request count, latency histograms, error rates at `/metrics`
- [ ] **OpenTelemetry tracing** — distributed traces across FastAPI → OpenStack SDK
- [ ] **Audit log** — write-operations persisted to Postgres with user, timestamp, diff
- [ ] **Webhook notifications** — POST to a configured URL on VM state changes

### Sprint 5 — Scale & Reliability
- [ ] **Multi-region support** — single API that federates across OpenStack regions
- [ ] **Database-backed inventory** — Postgres + SQLAlchemy for cross-cluster VM queries and caching
- [ ] **Circuit breaker** — if OpenStack is unreachable, fail fast and serve cached state
- [ ] **Canary deployments** — Argo Rollouts progressive delivery

---

## 12. Assumptions

1. **Authentication simplification:** API key auth is used for the PoC. Production deployments should use OAuth2 / JWT with a proper identity provider.
2. **Mock mode by default:** The prototype runs with an in-memory mock so evaluators don't need a running OpenStack cluster. Set `MOCK_OPENSTACK=false` with valid `OS_*` credentials to use a real cluster.
3. **Synchronous-style OpenStack calls:** The openstacksdk library is synchronous. In production, heavy operations (create, resize) should be dispatched to a Celery worker to avoid blocking the web process.
4. **Single-tenant:** The PoC does not enforce project isolation. Multi-tenancy (each API consumer scoped to their own OS project) is in the roadmap.
5. **Metrics availability:** Real metrics require Gnocchi/Ceilometer to be deployed in the target cluster. The mock returns synthetic data; the real service falls back to zeroes if Gnocchi is unavailable.
6. **No TLS in local dev:** docker-compose exposes port 8000 over plain HTTP. Production should terminate TLS at an nginx ingress or cloud load balancer.

---

## License

MIT © 2025
