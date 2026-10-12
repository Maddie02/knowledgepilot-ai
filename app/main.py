from fastapi import FastAPI
from app.routers.health import router as health_router

app = FastAPI(title="KnowledgePilot AI")


app.include_router(health_router)