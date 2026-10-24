from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth import create_access_token, get_current_user, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()

    if not user or not verify_password(login_data.password, user.hashed_password):
        log_event(
            actor=login_data.email,
            action="LOGIN",
            object="auth",
            result="FAILURE",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    log_event(
        actor=user.email,
        action="LOGIN",
        object="auth",
        result="SUCCESS",
        db=db,
    )

    access_token = create_access_token(
        data={"sub": user.email, "email": user.email, "role": user.role, "id": user.id}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
