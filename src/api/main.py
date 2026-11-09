from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import chat, ingest
from src.api import auth
from src.services.db import close_pool, get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warming up the pool avoids paying for the connections on the first request. If
    # Postgres is not available, the API starts anyway and the error shows up on every request.
    try:
        await get_pool()
    except Exception as e:
        print(f"⚠️ Could not open the Postgres pool at startup: {e}")
    yield
    await close_pool()


app = FastAPI(
    title="AI Engineer Sandbox API",
    description="Production API for advanced RAG (Hybrid + Cross-Encoder + Instructor + JWT/RLS)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(ingest.router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "API running"}
