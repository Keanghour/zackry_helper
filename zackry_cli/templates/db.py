# zackry_cli/templates/db.py

DB_BASE_PY = r'''from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All database models inherit from this class."""
'''

DB_SESSION_PY = r'''from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
'''

# Appended to .env when database support is enabled
ENV_DB = r'''
# Database (PostgreSQL)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=app_db
'''

# Appended to requirements.txt when database support is enabled
REQUIREMENTS_DB = r'''
# Database
sqlalchemy>=2.0
psycopg2-binary>=2.9
'''