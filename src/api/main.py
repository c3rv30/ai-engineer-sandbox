from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import chat, ingest
from src.api import auth
from src.services.db import close_pool, get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Precalentar el pool evita pagar las conexiones en la primera petición. Si Postgres
    # no está disponible, la API arranca igual y el error aparece en cada petición.
    try:
        await get_pool()
    except Exception as e:
        print(f"⚠️ No se pudo abrir el pool de Postgres al arrancar: {e}")
    yield
    await close_pool()


app = FastAPI(
    title="AI Engineer Sandbox API",
    description="API de Producción para RAG Avanzado (Híbrido + Cross-Encoder + Instructor + JWT/RLS)",
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
