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
    # file.filename lo controla el cliente, así que nunca se usa como ruta: con
    # '../' escribiría (y el finally borraría) fuera del directorio temporal, y dos
    # subidas simultáneas con el mismo nombre compartirían archivo entre tenants.
    # A disco va con un nombre aleatorio; el original solo se conserva como metadato.
    source_name = os.path.basename(file.filename.replace("\\", "/"))
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as buffer:
            temp_file_path = buffer.name
            shutil.copyfileobj(file.file, buffer)

        # 3. Llamar al motor de ingestión con RLS
        result = await ingest_file(temp_file_path, current_user.tenant_id, source=source_name)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 4. Limpieza: Borrar el archivo temporal
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

