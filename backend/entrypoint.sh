#!/bin/sh
set -e

# Run baseline stamp if database has existing tables but no alembic_version
python -c "
import os
from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic import command
from app.database import DATABASE_URL

url = DATABASE_URL
if url:
    try:
        engine = create_engine(url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if 'users' in tables and 'alembic_version' not in tables:
            print('[MIGRATION] Existing tables detected without alembic_version. Stamping head...')
            cfg = Config('alembic.ini')
            command.stamp(cfg, 'head')
        engine.dispose()
    except Exception as e:
        print('[MIGRATION WARNING] Baseline check skipped:', e)
"

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
