"""API v1 router — assembles all endpoint modules"""

from fastapi import APIRouter
from app.api.v1.endpoints import vms, actions, snapshots, catalog

api_router = APIRouter()

# VM CRUD
api_router.include_router(vms.router, prefix="/vms", tags=["VMs"])

# VM Lifecycle Actions (nested under /vms)
api_router.include_router(actions.router, prefix="/vms", tags=["VM Actions"])

# Snapshots (nested under /vms)
api_router.include_router(snapshots.router, prefix="/vms", tags=["Snapshots"])

# Catalog
api_router.include_router(catalog.router, prefix="/catalog", tags=["Catalog"])
