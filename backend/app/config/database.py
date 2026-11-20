from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
import os
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv
from sqlalchemy.ext.declarative import declarative_base

load_dotenv()


# Retrieve DATABASE_URL from environment.
# Temporary fallback keeps Azure working if the App Setting is missing.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

parsed_url = urlparse(DATABASE_URL)
if parsed_url.scheme.startswith("postgresql") and "sslmode=" not in (parsed_url.query or ""):
    query = parsed_url.query
    # Local Postgres (DATABASE_URL passed on the command line) has no SSL.
    ssl_mode = "disable" if parsed_url.hostname in ("localhost", "127.0.0.1", "::1") else "require"
    query = f"{query}&sslmode={ssl_mode}" if query else f"sslmode={ssl_mode}"
    DATABASE_URL = urlunparse(parsed_url._replace(query=query))

Base = declarative_base()

# SQLAlchemy setup
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    except OperationalError as exc:
        db.rollback()
        raise
    finally:
        db.close()


