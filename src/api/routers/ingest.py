from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
import os
import shutil
import tempfile
from src.services.ingestion import ingest_file, IngestionResult
from src.api.auth import get_current_user, User

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# Archivos permitidos para evitar vulnerabilidades
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}

@router.post("/", response_model=IngestionResult)
async def ingest_endpoint(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1].lower()
    
    # 1. Validación estricta del tipo de archivo
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Extensión no permitida. Soportadas: {ALLOWED_EXTENSIONS}")
        
    # 2. Guardar el archivo temporalmente
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 3. Llamar al motor de ingestión con RLS
        result = await ingest_file(temp_file_path, current_user.tenant_id)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 4. Limpieza: Borrar el archivo temporal
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

