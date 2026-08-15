from fastapi import FastAPI

from app.core.http_errors import register_core_error_handlers
from app.modules.health.router import router as health_router
from app.modules.invitations.router import router as invitations_router
from app.modules.organizations.router import router as organizations_router

app = FastAPI(title="Serviq API")
register_core_error_handlers(app)
app.include_router(health_router)
app.include_router(organizations_router)
app.include_router(invitations_router)
