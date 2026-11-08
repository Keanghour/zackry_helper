# zackry_cli/templates/files.py
#
# Each constant below is the text of one file that `zackry i`
# writes into a new FastAPI project.

# ----------------------------
# app/main.py
# ----------------------------
MAIN_PY = r'''from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.middlewares.audit import AuditMiddleware
from app.middlewares.errors import ErrorHandlerMiddleware
from app.routers import health

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code goes here (connect to services, warm caches ...)
    yield
    # Shutdown code goes here


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(AuditMiddleware)

register_exception_handlers(app)

app.include_router(health.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"app": settings.APP_NAME, "docs": "/docs"}
'''

# ----------------------------
# app/core/
# ----------------------------
CONFIG_PY = r'''from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "FastAPI App"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Encryption (Fernet key, see app/utils/encryption.py)
    ENCRYPTION_KEY: str = ""

    # Database (used only when database support is enabled)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "app_db"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
'''

SECURITY_PY = r'''from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid or expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
'''

LOGGING_PY = r'''import logging

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
'''

EXCEPTIONS_PY = r'''from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base exception for errors you want to return to the client."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": exc.message},
        )
'''

# ----------------------------
# app/routers, services
# ----------------------------
HEALTH_ROUTER = r'''from fastapi import APIRouter

from app.services.health_service import get_health

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    return get_health()
'''

HEALTH_SERVICE = r'''from app.core.config import settings


def get_health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
'''

# ----------------------------
# app/models, schemas
# ----------------------------
MODELS_BASE = r'''"""
Base for database models.

When database support is enabled, models inherit from Base:

    from app.models.base import Base

    class User(Base):
        __tablename__ = "users"
        ...
"""

try:
    from app.db.base import Base  # exists only when database support is enabled
except ImportError:  # pragma: no cover
    Base = None
'''

COMMON_SCHEMA = r'''from pydantic import BaseModel


class MessageResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
'''

# ----------------------------
# app/dependencies
# ----------------------------
AUTH_DEPENDENCY = r'''import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Use as: user = Depends(get_current_user)"""
    if credentials is None:
        raise UnauthorizedException("Missing token")

    try:
        return decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise UnauthorizedException("Invalid or expired token")
'''

DATABASE_DEPENDENCY = r'''from typing import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Use as: db: Session = Depends(get_db)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

# ----------------------------
# app/middlewares
# ----------------------------
MIDDLEWARE_AUDIT_PY = r'''import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("audit")


class AuditMiddleware(BaseHTTPMiddleware):
    """Logs every request: method, path, status code and duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
'''

MIDDLEWARE_ERRORS_PY = r'''import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("errors")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catches unexpected errors and returns a clean 500 response."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Internal server error"},
            )
'''

# ----------------------------
# app/utils
# ----------------------------
ENCRYPTION_PY = r'''from cryptography.fernet import Fernet

from app.core.config import settings


def generate_key() -> str:
    """Run once and put the result in ENCRYPTION_KEY in your .env file."""
    return Fernet.generate_key().decode("utf-8")


def _fernet() -> Fernet:
    if not settings.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY is empty. Set it in your .env file.")
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
'''

HELPERS_PY = r'''import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())
'''

VALIDATORS_PY = r'''import re

EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value))


def is_strong_password(value: str) -> bool:
    """At least 8 characters with a letter and a number."""
    return (
        len(value) >= 8
        and any(c.isalpha() for c in value)
        and any(c.isdigit() for c in value)
    )
'''

# ----------------------------
# tests
# ----------------------------
TESTS_CONFTEST = r'''import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
'''

TEST_HEALTH = r'''def test_health(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
'''

# ----------------------------
# Environment files
# ----------------------------
ENV_FILE = r'''APP_NAME=FastAPI App
APP_VERSION=0.1.0
DEBUG=true

SECRET_KEY=change-me-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=
'''

ENV_EXAMPLE = r'''APP_NAME=FastAPI App
APP_VERSION=0.1.0
DEBUG=false

SECRET_KEY=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

ENCRYPTION_KEY=
'''

GITIGNORE = r'''# Python
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/

# Virtual environments
venv/
.venv/

# Environment
.env

# IDE / OS
.vscode/
.idea/
.DS_Store

# Build
dist/
build/
*.egg-info/

# Logs
*.log
'''

REQUIREMENTS = r'''# Web
fastapi>=0.110
uvicorn[standard]>=0.27
gunicorn>=22.0
uvicorn-worker>=0.2
pydantic-settings>=2.2

# Security
PyJWT>=2.8
bcrypt>=4.1
cryptography>=42.0

# Testing
pytest>=8.0
httpx>=0.27
'''

PIP_CONF = r'''[global]
timeout = 60
disable-pip-version-check = true
'''

# ----------------------------
# README.md
# ----------------------------
README = r'''# FastAPI Project

Created with **zackry-cli** (`zackry i`).

## Run

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs
- ReDoc:   http://127.0.0.1:8000/redoc
- Health:  http://127.0.0.1:8000/api/v1/health

## Test

```bash
pytest
```

## Structure

```
app/
├── core/          config, security, logging, exceptions
├── routers/       API endpoints
├── services/      business logic
├── repositories/  data access
├── models/        database models
├── schemas/       request / response models
├── dependencies/  FastAPI dependencies (auth, db)
├── middlewares/   audit + error handling
└── utils/         encryption, helpers, validators
tests/
```
'''