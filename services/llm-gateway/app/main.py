from fastapi import FastAPI

from app.connectivity import router as connectivity_router
from app.routing.embeddings import router as embeddings_router

app = FastAPI(title="Serviq LLM Gateway")
app.include_router(connectivity_router)
app.include_router(embeddings_router)
