from fastapi import FastAPI

from app.connectivity import router as connectivity_router

app = FastAPI(title="Serviq LLM Gateway")
app.include_router(connectivity_router)
