from fastapi import FastAPI

from app.routers.chat import router as chat_router
from app.routers.health import router as health_router

app = FastAPI(title="KnowledgePilot AI")


app.include_router(health_router)
app.include_router(chat_router)
