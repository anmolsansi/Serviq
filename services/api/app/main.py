from fastapi import FastAPI

from app.modules.health.router import router as health_router

app = FastAPI(title="Serviq API")
app.include_router(health_router)
