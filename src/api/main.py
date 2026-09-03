from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import chat, ingest
from src.api import auth

app = FastAPI(
    title="AI Engineer Sandbox API",
    description="API de Producción para RAG Avanzado (Híbrido + Cross-Encoder + Instructor + JWT/RLS)",
    version="1.0.0"
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
