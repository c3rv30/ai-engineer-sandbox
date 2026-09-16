from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
import logging
import os
import shutil
import tempfile
import uuid
from src.services.ingestion import ingest_file, IngestionResult
from src.api.auth import get_current_user, User
from src.services.filenames import source_name

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# El texto de una excepción interna no se le devuelve al cliente (SEC-06): un PDF
# ilegible hacía que el 500 incluyera la ruta absoluta del temporal del servidor.
logger = logging.getLogger(__name__)

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
    origin = source_name(file.filename)
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as buffer:
            temp_file_path = buffer.name
            shutil.copyfileobj(file.file, buffer)

        # 3. Llamar al motor de ingestión con RLS
        result = await ingest_file(temp_file_path, current_user.tenant_id, source=origin)
        return result

    except Exception:
        # El 400 de extensión no permitida se levanta antes del try: sigue llegando
        # íntegro al cliente, como debe, porque es un mensaje escrito para él.
        error_id = uuid.uuid4().hex[:8]
        logger.exception("Fallo en POST /ingest/ [%s]", error_id)
        raise HTTPException(status_code=500, detail=f"Error interno ({error_id})")
    finally:
        # 4. Limpieza: Borrar el archivo temporal
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

