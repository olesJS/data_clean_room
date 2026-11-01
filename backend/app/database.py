import os
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres_password@localhost:5432/app_db",
)

# Normalize postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Normalize postgresql:// to postgresql+psycopg2:// if psycopg3 is not present
if DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith(
    "postgresql+"
):
    try:
        import psycopg  # noqa: F401
    except ImportError:
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configure Async engine and session (psycopg3 or aiosqlite)
async_url = DATABASE_URL
if async_url.startswith("postgresql://"):
    async_url = async_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif async_url.startswith("postgresql+psycopg2://"):
    async_url = async_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
elif async_url.startswith("sqlite://") and not async_url.startswith(
    "sqlite+aiosqlite://"
):
    async_url = async_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

async_connect_args = {}
if "sqlite" in async_url:
    async_connect_args["check_same_thread"] = False

async_engine = create_async_engine(
    async_url,
    echo=False,
    connect_args=async_connect_args,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def init_db():
    """Create all tables and seed initial users if in development/test."""
    from app import models
    from app.auth import hash_password

    Base.metadata.create_all(bind=engine)

    env = os.getenv("ENV", "development").lower()
    seed_env = os.getenv("SEED_USERS")
    should_seed = (
        seed_env.lower() in ("true", "1", "yes")
        if seed_env is not None
        else (env in ("development", "test", "dev"))
    )

    if not should_seed:
        return

    db = SessionLocal()
    try:
        default_users = [
            (
                "provider@example.com",
                "password123",
                "DataProvider",
            ),
            (
                "consumer@example.com",
                "password123",
                "DataConsumer",
            ),
            (
                "steward@example.com",
                "password123",
                "DataSteward",
            ),
        ]

        for email, password, role in default_users:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if not existing:
                user = models.User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=role,
                )
                db.add(user)
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[DB INIT WARNING] Could not seed users: {exc}")
    finally:
        db.close()
