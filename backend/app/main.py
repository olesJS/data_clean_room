import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine, init_db
from app.routers import (
    audit,
    auth,
    catalog,
    datasets,
    exchange,
    legal_basis,
    publication,
    quality,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as exc:
        print(f"[STARTUP WARNING] Could not initialize database: {exc}")
    yield


app = FastAPI(title="Data Clean Room API", lifespan=lifespan)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,http://localhost:80,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(datasets.router)
app.include_router(legal_basis.router)
app.include_router(quality.router)
app.include_router(publication.router)
app.include_router(exchange.router)
app.include_router(catalog.router)


@app.get("/")
def read_root():
    return {"message": "Data Clean Room API is up and running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def db_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
