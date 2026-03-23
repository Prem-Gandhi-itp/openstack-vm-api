"""
OpenStack VM Lifecycle Management API
Main application entry point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting OpenStack VM Lifecycle API...")
    yield
    logger.info("Shutting down OpenStack VM Lifecycle API...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
## OpenStack VM Lifecycle Management API

A production-ready REST API for managing OpenStack virtual machine lifecycle operations.

### Features
- **VM Management**: Create, read, update, delete virtual machines
- **Lifecycle Operations**: Start, stop, reboot, suspend, resume VMs
- **Snapshot Management**: Create and manage VM snapshots
- **Console Access**: Get VNC/SPICE console URLs
- **Metrics**: VM resource utilization and health monitoring

### Authentication
All endpoints require a valid API key passed via the `X-API-Key` header.

### Rate Limiting
API requests are rate-limited to 100 requests/minute per API key.
    """,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "service": settings.PROJECT_NAME,
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API info."""
    return {
        "message": "OpenStack VM Lifecycle Management API",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
    }
