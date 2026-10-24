import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres_password@localhost:5432/app_db",
)

# Normalize postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed initial users if necessary."""
    from app import models
    from app.auth import hash_password

    Base.metadata.create_all(bind=engine)

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
