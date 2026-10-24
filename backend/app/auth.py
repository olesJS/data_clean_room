import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.models import User

ENV = os.getenv("ENV", "development").lower()
RAW_SECRET_KEY = os.getenv("SECRET_KEY")

if not RAW_SECRET_KEY:
    if ENV in ("development", "test", "dev"):
        RAW_SECRET_KEY = "dev_secret_key_data_clean_room_super_secure_32_bytes_token!"
    else:
        err = "CRITICAL CONFIG ERROR: SECRET_KEY environment variable must be set!"
        raise RuntimeError(err)

if len(RAW_SECRET_KEY.encode("utf-8")) < 32:
    if ENV not in ("development", "test", "dev"):
        err = "CRITICAL CONFIG ERROR: SECRET_KEY must be >= 32 bytes in production!"
        raise RuntimeError(err)
    SECRET_KEY = hashlib.sha256(RAW_SECRET_KEY.encode("utf-8")).hexdigest()
else:
    SECRET_KEY = RAW_SECRET_KEY

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    endpoint_path = request.url.path
    if not credentials or not credentials.credentials:
        log_event(
            actor="unauthenticated",
            action="UNAUTHORIZED_ACCESS",
            object=endpoint_path,
            result="UNAUTHORIZED",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        email: Optional[str] = payload.get("email") or payload.get("sub")
        if not email:
            raise ValueError("Token missing email")
    except Exception:
        log_event(
            actor="invalid_token",
            action="UNAUTHORIZED_ACCESS",
            object=endpoint_path,
            result="UNAUTHORIZED",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        log_event(
            actor=email or "unknown_user",
            action="UNAUTHORIZED_ACCESS",
            object=endpoint_path,
            result="UNAUTHORIZED",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(role_name: str):
    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role != role_name:
            log_event(
                actor=current_user.email,
                action="ACCESS_DENIED",
                object=request.url.path,
                result="FORBIDDEN",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: {role_name} role required",
            )
        return current_user

    return role_checker


def require_roles(allowed_roles: list[str] | tuple[str, ...]):
    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role not in allowed_roles:
            roles_str = ", ".join(allowed_roles)
            log_event(
                actor=current_user.email,
                action="ACCESS_DENIED",
                object=request.url.path,
                result="FORBIDDEN",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of [{roles_str}] roles",
            )
        return current_user

    return role_checker
