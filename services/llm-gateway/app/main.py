from fastapi import FastAPI

from app.connectivity import router as connectivity_router
from app.http_boundary import (
    InternalGatewayBoundaryMiddleware,
    register_gateway_error_handlers,
)
from app.routing.embeddings import router as embeddings_router

app = FastAPI(title="Serviq LLM Gateway")
register_gateway_error_handlers(app)
app.add_middleware(InternalGatewayBoundaryMiddleware)
app.include_router(connectivity_router)
app.include_router(embeddings_router)
