import os
import uuid
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ValidationError
import jwt

load_dotenv()

# HS256 es simétrico: quien conozca esta clave puede emitir tokens válidos para
# cualquier tenant, y el aislamiento RLS de Postgres deja de tener efecto.
# Por eso no admite valor por defecto: si falta, el proceso no arranca.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no está configurada. Añádela a tu archivo .env "
        "(genera una con: openssl rand -hex 32)."
    )
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY es demasiado corta (mínimo 32 caracteres). "
        "Genera una con: openssl rand -hex 32"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    # El tenant_id fija app.current_tenant en la capa de datos (src/services/db.py).
    # Tiparlo como UUID hace que Pydantic rechace en el borde cualquier valor malformado
    # antes de que llegue ahí, y garantiza la forma canónica aguas abajo.
    tenant_id: uuid.UUID

# Mock Database of users
# NOTA: no es un sistema de autenticación real. Las contraseñas están en claro y
# sirven únicamente para demostrar el aislamiento multi-tenant del sandbox.
FAKE_USERS_DB = {
    "bryan": {
        "username": "bryan",
        "password": "password123",
        "tenant_id": "00000000-0000-0000-0000-000000000000"
    },
    "empresa_x": {
        "username": "empresa_x",
        "password": "password123",
        "tenant_id": "11111111-1111-1111-1111-111111111111"
    }
}

router = APIRouter(prefix="/auth", tags=["Auth"])

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_dict = FAKE_USERS_DB.get(form_data.username)
    if not user_dict or form_data.password != user_dict["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_dict["username"], "tenant_id": user_dict["tenant_id"]},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if username is None or tenant_id is None:
            raise credentials_exception
        # Un tenant_id mal formado levanta ValidationError aquí, no un 500 aguas abajo.
        return User(username=username, tenant_id=tenant_id)
    except (jwt.PyJWTError, ValidationError):
        raise credentials_exception
