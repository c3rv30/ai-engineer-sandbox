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

# The text of an internal exception is not returned to the client (SEC-06): an
# unreadable PDF made the 500 include the absolute path of the server's temporary file.
logger = logging.getLogger(__name__)

# Allowed file types, to avoid vulnerabilities
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg"}

@router.post("/", response_model=IngestionResult)
async def ingest_endpoint(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1].lower()
    
    # 1. Strict file type validation
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Supported: {ALLOWED_EXTENSIONS}")
        
    # 2. Save the file temporarily
    # file.filename is controlled by the client, so it is never used as a path: with
    # '../' it would write (and the finally would delete) outside the temporary
    # directory, and two simultaneous uploads with the same name would share a file
    # across tenants. It goes to disk under a random name; the original is kept only as metadata.
    origin = source_name(file.filename)
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as buffer:
            temp_file_path = buffer.name
            shutil.copyfileobj(file.file, buffer)

        # 3. Call the ingestion engine with RLS
        result = await ingest_file(temp_file_path, current_user.tenant_id, source=origin)
        return result

    except Exception:
        # The 400 for a disallowed file type is raised before the try: it still reaches
        # the client whole, as it should, because it is a message written for the client.
        error_id = uuid.uuid4().hex[:8]
        logger.exception("POST /ingest/ failed [%s]", error_id)
        raise HTTPException(status_code=500, detail=f"Internal error ({error_id})")
    finally:
        # 4. Cleanup: delete the temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
