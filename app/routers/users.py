from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import AvatarResponse, UserPublic, UserUpdateRequest
from app.utils.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return UserPublic.model_validate(current_user)


@router.patch("/me", response_model=UserPublic)
def update_me(
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.first_name is not None:
        current_user.first_name = data.first_name
    if data.last_name is not None:
        current_user.last_name = data.last_name
    db.commit()
    db.refresh(current_user)
    return UserPublic.model_validate(current_user)


@router.post("/me/avatar", response_model=AvatarResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Plik za duzy (max 2 MB)")

    # Walidacja MIME przez naglowek bajtow
    import imghdr
    img_type = imghdr.what(None, h=content[:32])
    if img_type not in ("jpeg", "png", "gif", "webp"):
        raise HTTPException(status_code=400, detail="Niedozwolony typ pliku")

    # W dev: zapisz lokalnie; w prod: upload do Supabase Storage
    from app.config import settings
    import os, uuid
    filename = f"{uuid.uuid4()}.{img_type}"

    if settings.is_development:
        static_dir = "frontend/static/avatars"
        os.makedirs(static_dir, exist_ok=True)
        filepath = f"{static_dir}/{filename}"
        with open(filepath, "wb") as f:
            f.write(content)
        avatar_url = f"{settings.FRONTEND_URL}/static/avatars/{filename}"
    else:
        # Supabase Storage upload
        raise HTTPException(status_code=501, detail="Supabase storage nie jest skonfigurowany")

    current_user.avatar_url = avatar_url
    db.commit()
    return AvatarResponse(avatar_url=avatar_url)


@router.get("/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Uzytkownik nie istnieje")
    return UserPublic.model_validate(user)
