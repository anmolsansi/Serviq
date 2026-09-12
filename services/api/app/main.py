from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.http_errors import register_core_error_handlers
from app.core.session import lifespan_session_store
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.invitations.router import accept_router as invitation_accept_router
from app.modules.invitations.router import router as invitations_router
from app.modules.knowledge.router import router as knowledge_sources_router
from app.modules.members.router import router as members_router
from app.modules.organizations.router import router as organizations_router
from app.modules.providers.model_router import router as models_router
from app.modules.providers.router import router as providers_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with lifespan_session_store():
        yield


app = FastAPI(title="Serviq API", lifespan=lifespan)
register_core_error_handlers(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(invitations_router)
app.include_router(invitation_accept_router)
app.include_router(members_router)
app.include_router(providers_router)
app.include_router(models_router)
app.include_router(knowledge_sources_router)
