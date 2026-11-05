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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_datasets_columns() -> None:
    """Add Sprint-2 profiling columns to the datasets table if they are missing.

    Uses raw SQL with dialect-aware ``IF NOT EXISTS`` (PostgreSQL) or a
    ``has_column`` probe (other dialects) so it is safe to run on every
    startup regardless of whether the columns already exist.
    """
    new_columns = [
        ("data_class", "VARCHAR(50)"),
        ("quality_score", "DOUBLE PRECISION"),
        ("profile_json", "JSON"),
        ("pii_json", "JSON"),
    ]

    dialect = engine.dialect.name  # 'postgresql', 'sqlite', …

    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            try:
                if dialect == "postgresql":
                    stmt = (
                        f"ALTER TABLE datasets "
                        f"ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                    )
                    conn.execute(__import__("sqlalchemy").text(stmt))
                else:
                    # Generic fallback: probe with has_column
                    inspector = __import__("sqlalchemy", fromlist=["inspect"]).inspect(
                        engine
                    )
                    existing = [c["name"] for c in inspector.get_columns("datasets")]
                    if col_name not in existing:
                        stmt = f"ALTER TABLE datasets ADD COLUMN {col_name} {col_type};"
                        conn.execute(__import__("sqlalchemy").text(stmt))
            except Exception as exc:  # column already exists or other benign error
                print(f"[DB MIGRATE] Skipping column '{col_name}': {exc}")
        try:
            conn.commit()
        except Exception:
            pass  # autocommit mode — commit is a no-op


def init_db():
    """Create all tables and seed initial users if in development/test."""
    from app import models
    from app.auth import hash_password

    Base.metadata.create_all(bind=engine)

    # Ensure Sprint-2 profiling columns exist in an already-created table
    _migrate_datasets_columns()

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
