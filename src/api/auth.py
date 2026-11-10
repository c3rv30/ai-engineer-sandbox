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

# HS256 is symmetric: whoever knows this key can issue valid tokens for any tenant,
# and Postgres RLS isolation stops having any effect.
# That is why there is no default: if it is missing, the process does not start.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Add it to your .env file "
        "(generate one with: openssl rand -hex 32)."
    )
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY is too short (minimum 32 characters). "
        "Generate one with: openssl rand -hex 32"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    # tenant_id sets app.current_tenant in the data layer (src/services/db.py).
    # Typing it as UUID makes Pydantic reject any malformed value at the edge, before
    # it gets there, and guarantees the canonical form downstream.
    tenant_id: uuid.UUID

# Mock Database of users
# NOTE: this is not a real authentication system. The passwords are in plain text and
# exist only to demonstrate the sandbox's multi-tenant isolation.
FAKE_USERS_DB = {
    "bryan": {
        "username": "bryan",
        "password": "password123",
        "tenant_id": "00000000-0000-0000-0000-000000000000"
    },
    "company_x": {
        "username": "company_x",
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
        # A malformed tenant_id raises ValidationError here, not a 500 downstream.
        return User(username=username, tenant_id=tenant_id)
    except (jwt.PyJWTError, ValidationError):
        raise credentials_exception
