from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=MessageResponse)
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    return await AuthService.register(db, data)


@router.get("/activate", response_model=MessageResponse)
def activate(token: str = Query(...), db: Session = Depends(get_db)):
    return AuthService.activate(db, token)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return AuthService.login(db, data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return AuthService.refresh(db, data.refresh_token)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: PasswordResetRequest, db: Session = Depends(get_db)):
    return await AuthService.forgot_password(db, data.email)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    return AuthService.reset_password(db, data)
