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
    from app.config import settings
    from app.services.storage_service import delete_avatar, detect_image_type, save_avatar

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Plik za duzy (max 2 MB)")

    img_type = detect_image_type(content)
    if img_type not in ("jpeg", "png", "gif", "webp"):
        raise HTTPException(status_code=400, detail="Niedozwolony typ pliku")

    old_avatar = current_user.avatar_url
    try:
        avatar_url = await save_avatar(content, img_type, settings.FRONTEND_URL)
    except Exception:
        raise HTTPException(status_code=502, detail="Nie udalo sie zapisac zdjecia")

    current_user.avatar_url = avatar_url
    db.commit()
    await delete_avatar(old_avatar)
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
