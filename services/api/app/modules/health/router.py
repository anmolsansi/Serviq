"""HTTP contract for Serviq API liveness and readiness probes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.modules.health.service import database_is_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> JSONResponse:
    """Report process liveness without checking external dependencies."""

    return JSONResponse(status_code=200, content={"status": "live"})


@router.get("/ready")
async def readiness() -> JSONResponse:
    """Report whether PostgreSQL is ready for API traffic."""

    if await database_is_ready():
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "dependency": "database"},
    )
