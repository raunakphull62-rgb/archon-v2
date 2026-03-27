import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — simulated AI knowledge base
# ---------------------------------------------------------------------------

_KNOWN_FRAMEWORKS = {"fastapi", "flask", "django", "express", "rails"}
_KNOWN_DATABASES  = {"postgresql", "mysql", "sqlite", "mongodb", "redis"}

_FRAMEWORK_DEFAULTS: dict[str, str] = {
    "api":      "fastapi",
    "web":      "django",
    "realtime": "fastapi",
    "admin":    "django",
    "micro":    "fastapi",
}

_DB_DEFAULTS: dict[str, str] = {
    "user":    "postgresql",
    "product": "postgresql",
    "session": "redis",
    "file":    "mongodb",
    "log":     "mongodb",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return text.lower().strip()


def _extract_features(prompt: str) -> list[str]:
    feature_keywords = [
        "authentication", "auth",
        "authorization",
        "crud",
        "search",
        "upload",
        "payment",
        "notification",
        "dashboard",
        "reporting",
        "api",
        "websocket",
        "caching",
        "rate limiting",
        "email",
    ]
    found: list[str] = []
    normalised = _normalise(prompt)
    for kw in feature_keywords:
        if kw in normalised and kw not in found:
            found.append(kw)
    # Deduplicate aliases
    if "auth" in found and "authentication" not in found:
        found[found.index("auth")] = "authentication"
    if "auth" in found:
        found.remove("auth")
    return found or ["crud"]


def _extract_entities(prompt: str) -> list[str]:
    """Return capitalised nouns that look like domain entities."""
    words = re.findall(r"\b[A-Z][a-z]{2,}\b", prompt)
    # Fallback: pick meaningful lowercase nouns
    if not words:
        candidates = re.findall(
            r"\b(user|product|order|item|post|comment|category|invoice|"
            r"customer|employee|event|ticket|message|report)\b",
            _normalise(prompt),
        )
        words = list(dict.fromkeys(c.capitalize() for c in candidates))
    return list(dict.fromkeys(words)) or ["User", "Item"]


def _detect_framework(prompt: str) -> str:
    normalised = _normalise(prompt)
    for fw in _KNOWN_FRAMEWORKS:
        if fw in normalised:
            return fw
    for keyword, fw in _FRAMEWORK_DEFAULTS.items():
        if keyword in normalised:
            return fw
    return "fastapi"


def _detect_database(prompt: str, entities: list[str]) -> str:
    normalised = _normalise(prompt)
    for db in _KNOWN_DATABASES:
        if db in normalised:
            return db
    for entity in entities:
        for keyword, db in _DB_DEFAULTS.items():
            if keyword in entity.lower():
                return db
    return "postgresql"


def _validate_non_empty(value: Any, name: str) -> None:
    if not value:
        raise ValueError(f"{name} must not be empty.")


# ---------------------------------------------------------------------------
# 1. analyzer_agent
# ---------------------------------------------------------------------------

async def analyzer_agent(prompt: str) -> dict:
    """
    Extract structured metadata from a free-text prompt.

    Returns
    -------
    {
        "features":  [...],
        "entities":  [...],
        "database":  "...",
        "framework": "..."
    }
    """
    _validate_non_empty(prompt, "prompt")
    logger.info("analyzer_agent | analysing prompt (%d chars)", len(prompt))

    features  = _extract_features(prompt)
    entities  = _extract_entities(prompt)
    framework = _detect_framework(prompt)
    database  = _detect_database(prompt, entities)

    result = {
        "features":  features,
        "entities":  entities,
        "database":  database,
        "framework": framework,
    }
    logger.debug("analyzer_agent | result=%s", result)
    return result


# ---------------------------------------------------------------------------
# 2. planner_agent
# ---------------------------------------------------------------------------

def _build_folder_structure(framework: str, entities: list[str]) -> dict:
    base: dict[str, Any] = {
        "app/": {
            "__init__.py": None,
            "main.py":     None,
            "config.py":   None,
            "database.py": None,
            "models/":     {"__init__.py": None, **{f"{e.lower()}.py": None for e in entities}},
            "schemas/":    {"__init__.py": None, **{f"{e.lower()}.py": None for e in entities}},
            "routers/":    {"__init__.py": None, **{f"{e.lower()}.py": None for e in entities}},
            "services/":   {"__init__.py": None, **{f"{e.lower()}.py": None for e in entities}},
            "utils/":      {"__init__.py": None, "security.py": None, "helpers.py": None},
        },
        "tests/": {
            "__init__.py": None,
            **{f"test_{e.lower()}.py": None for e in entities},
        },
        ".env.example":    None,
        "requirements.txt": None,
        "README.md":       None,
    }
    if framework == "fastapi":
        base["app/"]["dependencies.py"] = None
    elif framework == "django":
        base["app/"]["admin.py"] = None
        base["app/"]["urls.py"]  = None
    return base


def _build_routes(entities: list[str], features: list[str]) -> list[dict]:
    routes: list[dict] = []

    for entity in entities:
        slug = entity.lower() + "s"
        for method, path, summary in [
            ("GET",    f"/{slug}",        f"List all {entity}s"),
            ("POST",   f"/{slug}",        f"Create a new {entity}"),
            ("GET",    f"/{slug}/{{id}}", f"Get {entity} by ID"),
            ("PUT",    f"/{slug}/{{id}}", f"Update {entity} by ID"),
            ("DELETE", f"/{slug}/{{id}}", f"Delete {entity} by ID"),
        ]:
            routes.append({"method": method, "path": path, "summary": summary})

    if "authentication" in features:
        routes += [
            {"method": "POST", "path": "/auth/register", "summary": "Register a new user"},
            {"method": "POST", "path": "/auth/login",    "summary": "Obtain access token"},
            {"method": "POST", "path": "/auth/logout",   "summary": "Invalidate token"},
            {"method": "POST", "path": "/auth/refresh",  "summary": "Refresh access token"},
        ]

    if "search" in features:
        for entity in entities:
            routes.append({
                "method":  "GET",
                "path":    f"/{entity.lower()}s/search",
                "summary": f"Search {entity}s by query",
            })

    if "upload" in features:
        routes.append({"method": "POST", "path": "/uploads", "summary": "Upload a file"})

    return routes


async def planner_agent(data: dict) -> dict:
    """
    Produce a folder structure and route list from analyzer output.

    Returns
    -------
    {
        "folder_structure": {...},
        "routes":           [{"method": "...", "path": "...", "summary": "..."}, ...]
    }
    """
    _validate_non_empty(data, "data")

    framework = data.get("framework", "fastapi")
    entities  = data.get("entities", ["Item"])
    features  = data.get("features", ["crud"])

    logger.info(
        "planner_agent | framework=%s entities=%s features=%s",
        framework, entities, features,
    )

    result = {
        "folder_structure": _build_folder_structure(framework, entities),
        "routes":           _build_routes(entities, features),
        "framework":        framework,
        "database":         data.get("database", "postgresql"),
        "entities":         entities,
        "features":         features,
    }
    logger.debug("planner_agent | %d routes planned", len(result["routes"]))
    return result


# ---------------------------------------------------------------------------
# 3. code_generator_agent
# ---------------------------------------------------------------------------

def _gen_main(framework: str) -> str:
    if framework == "fastapi":
        return '''\
from fastapi import FastAPI
from app.routers import api_router
from app.database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Generated API", version="1.0.0")
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
'''
    return '''\
from flask import Flask
from app.database import db

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    db.init_app(app)
    return app

app = create_app()
'''


def _gen_config(database: str) -> str:
    return f'''\
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Generated API"
    debug: bool = False
    database_url: str = os.getenv(
        "DATABASE_URL",
        "{'postgresql://user:pass@localhost:5432/db' if database == 'postgresql' else database + '://localhost/db'}"
    )
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    access_token_expire_minutes: int = 30

    model_config = {{"env_file": ".env"}}


settings = Settings()
'''


def _gen_database(database: str) -> str:
    if database in ("postgresql", "sqlite", "mysql"):
        return '''\
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''
    return '''\
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.database_url)
db = client.get_default_database()
'''


def _gen_model(entity: str) -> str:
    return f'''\
from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class {entity}(Base):
    __tablename__ = "{entity.lower()}s"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<{entity} id={{self.id}} name={{self.name!r}}>"
'''


def _gen_schema(entity: str) -> str:
    return f'''\
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class {entity}Base(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class {entity}Create({entity}Base):
    pass


class {entity}Update(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class {entity}Response({entity}Base):
    id:         int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {{"from_attributes": True}}
'''


def _gen_service(entity: str) -> str:
    e = entity.lower()
    return f'''\
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.{e} import {entity}
from app.schemas.{e} import {entity}Create, {entity}Update


def get_all(db: Session, skip: int = 0, limit: int = 100) -> list[{entity}]:
    return db.query({entity}).offset(skip).limit(limit).all()


def get_by_id(db: Session, item_id: int) -> {entity}:
    obj = db.query({entity}).filter({entity}.id == item_id).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="{entity} not found")
    return obj


def create(db: Session, payload: {entity}Create) -> {entity}:
    obj = {entity}(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, item_id: int, payload: {entity}Update) -> {entity}:
    obj = get_by_id(db, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, item_id: int) -> None:
    obj = get_by_id(db, item_id)
    db.delete(obj)
    db.commit()
'''


def _gen_router(entity: str) -> str:
    e = entity.lower()
    return f'''\
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.{e} import {entity}Create, {entity}Update, {entity}Response
from app.services import {e} as service

router = APIRouter(prefix="/{e}s", tags=["{entity}s"])


@router.get("/", response_model=list[{entity}Response])
def list_{e}s(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return service.get_all(db, skip=skip, limit=limit)


@router.post("/", response_model={entity}Response, status_code=status.HTTP_201_CREATED)
def create_{e}(payload: {entity}Create, db: Session = Depends(get_db)):
    return service.create(db, payload)


@router.get("/{{item_id}}", response_model={entity}Response)
def get_{e}(item_id: int, db: Session = Depends(get_db)):
    return service.get_by_id(db, item_id)


@router.put("/{{item_id}}", response_model={entity}Response)
def update_{e}(item_id: int, payload: {entity}Update, db: Session = Depends(get_db)):
    return service.update(db, item_id, payload)


@router.delete("/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_{e}(item_id: int, db: Session = Depends(get_db)):
    service.delete(db, item_id)
'''


def _gen_requirements(framework: str, database: str) -> str:
    packages = [
        "fastapi>=0.110.0" if framework == "fastapi" else "flask>=3.0.0",
        "uvicorn[standard]>=0.29.0",
        "pydantic>=2.6.0",
        "pydantic-settings>=2.2.0",
        "sqlalchemy>=2.0.0",
        "alembic>=1.13.0",
        "python-dotenv>=1.0.0",
    ]
    if database == "postgresql":
        packages.append("psycopg2-binary>=2.9.9")
    elif database == "mysql":
        packages.append("pymysql>=1.1.0")
    elif database == "mongodb":
        packages.append("motor>=3.3.0")
    return "\n".join(packages) + "\n"


def _gen_env_example(database: str) -> str:
    db_url = {
        "postgresql": "postgresql://user:password@localhost:5432/mydb",
        "mysql":      "mysql+pymysql://user:password@localhost:3306/mydb",
        "sqlite":     "sqlite:///./app.db",
        "mongodb":    "mongodb://localhost:27017/mydb",
        "redis":      "redis://localhost:6379/0",
    }.get(database, "postgresql://user:password@localhost:5432/mydb")

    return f"""\
DATABASE_URL={db_url}
SECRET_KEY=super-secret-key-change-in-production
DEBUG=false
ACCESS_TOKEN_EXPIRE_MINUTES=30
"""


async def code_generator_agent(plan: dict) -> dict:
    """
    Generate source file contents from a planner output.

    Returns
    -------
    {"filename.py": "file content", ...}
    """
    _validate_non_empty(plan, "plan")

    framework = plan.get("framework", "fastapi")
    database  = plan.get("database",  "postgresql")
    entities  = plan.get("entities",  ["Item"])

    logger.info(
        "code_generator_agent | framework=%s database=%s entities=%s",
        framework, database, entities,
    )

    files: dict[str, str] = {
        "app/main.py":     _gen_main(framework),
        "app/config.py":   _gen_config(database),
        "app/database.py": _gen_database(database),
        "requirements.txt": _gen_requirements(framework, database),
        ".env.example":    _gen_env_example(database),
    }

    for entity in entities:
        e = entity.lower()
        files[f"app/models/{e}.py"]   = _gen_model(entity)
        files[f"app/schemas/{e}.py"]  = _gen_schema(entity)
        files[f"app/services/{e}.py"] = _gen_service(entity)
        files[f"app/routers/{e}.py"]  = _gen_router(entity)

    # __init__ stubs
    for pkg in ("app", "app/models", "app/schemas", "app/services", "app/routers", "app/utils", "tests"):
        files[f"{pkg}/__init__.py"] = ""

    logger.info("code_generator_agent | %d files generated", len(files))
    return files
