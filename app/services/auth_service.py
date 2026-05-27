from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    RegisterRequest,
    TokenResponse,
)
from app.services.email_service import send_activation_email, send_password_reset_email
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.utils.tokens import generate_activation_token, generate_password_reset_token
from app.config import settings
from jose import JWTError


class AuthService:

    @staticmethod
    async def register(db: Session, data: RegisterRequest) -> dict:
        if db.query(User).filter(User.email == data.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="E-mail jest juz zarejestrowany")

        token, expires = generate_activation_token()
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            is_active=False,
            activation_token=token,
            activation_token_expires=expires,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        await send_activation_email(user.email, user.first_name, token)
        return {"message": "Sprawdz skrzynke e-mail, aby aktywowac konto."}

    @staticmethod
    def activate(db: Session, token: str) -> dict:
        user = db.query(User).filter(User.activation_token == token).first()
        if not user:
            raise HTTPException(status_code=400, detail="Token nieprawidlowy")
        if user.activation_token_expires and \
                user.activation_token_expires.replace(tzinfo=timezone.utc) \
                < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token wygasl")

        user.is_active = True
        user.activation_token = None
        user.activation_token_expires = None
        db.commit()
        return {"message": "Konto zostalo aktywowane. Mozesz sie zalogowac."}

    @staticmethod
    def login(db: Session, data: LoginRequest) -> TokenResponse:
        user = db.query(User).filter(User.email == data.email).first()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Nieprawidlowy e-mail lub haslo")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Konto nie jest aktywowane. Sprawdz skrzynke e-mail.")

        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    def refresh(db: Session, refresh_token: str) -> TokenResponse:
        try:
            user_id = decode_token(refresh_token, expected_type="refresh")
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Nieprawidlowy refresh token")
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Uzytkownik nie istnieje")
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def forgot_password(db: Session, email: str) -> dict:
        user = db.query(User).filter(User.email == email).first()
        # Odpowiedz taka sama niezaleznie od istnienia konta (bezpieczenstwo)
        if user and user.is_active:
            token, expires = generate_password_reset_token()
            user.password_reset_token = token
            user.password_reset_expires = expires
            db.commit()
            await send_password_reset_email(user.email, user.first_name, token)
        return {"message": "Jesli konto istnieje, wyslalismy link do resetu hasla."}

    @staticmethod
    def reset_password(db: Session, data: PasswordResetConfirm) -> dict:
        user = db.query(User).filter(User.password_reset_token == data.token).first()
        if not user:
            raise HTTPException(status_code=400, detail="Token nieprawidlowy")
        if user.password_reset_expires and \
                user.password_reset_expires.replace(tzinfo=timezone.utc) \
                < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token wygasl")

        user.hashed_password = hash_password(data.new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        db.commit()
        return {"message": "Haslo zostalo zmienione."}
