"""Przechowywanie avatarów: Supabase Storage w produkcji, lokalny dysk w dev."""
import logging
import os
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AVATAR_LOCAL_DIR = "frontend/static/avatars"
_MIME = {"jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
_PUBLIC_MARKER = "/storage/v1/object/public/"


def detect_image_type(data: bytes) -> str | None:
    """Typ obrazu z magic bytes — niezależne od imghdr (usuniętego w Python 3.13)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def supabase_configured() -> bool:
    """True, gdy Supabase Storage jest realnie skonfigurowane (nie placeholder)."""
    url = settings.SUPABASE_URL or ""
    return bool(
        url and settings.SUPABASE_KEY and settings.SUPABASE_BUCKET
        and "your-project" not in url
    )


async def save_avatar(content: bytes, img_type: str, base_url: str) -> str:
    """Zapisuje avatar i zwraca publiczny URL. Supabase jeśli skonfigurowane,
    w przeciwnym razie lokalny katalog static (dev)."""
    filename = f"{uuid.uuid4()}.{img_type}"

    if supabase_configured():
        mime = _MIME.get(img_type, "application/octet-stream")
        upload_url = (f"{settings.SUPABASE_URL}/storage/v1/object/"
                      f"{settings.SUPABASE_BUCKET}/{filename}")
        headers = {
            "Authorization": f"Bearer {settings.SUPABASE_KEY}",
            "Content-Type": mime,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(upload_url, headers=headers, content=content)
            resp.raise_for_status()
        return (f"{settings.SUPABASE_URL}/storage/v1/object/public/"
                f"{settings.SUPABASE_BUCKET}/{filename}")

    # Fallback dev – lokalny dysk
    os.makedirs(AVATAR_LOCAL_DIR, exist_ok=True)
    with open(f"{AVATAR_LOCAL_DIR}/{filename}", "wb") as f:
        f.write(content)
    return f"{base_url.rstrip('/')}/static/avatars/{filename}"


async def delete_avatar(avatar_url: str | None) -> None:
    """Best-effort usunięcie starego avatara (Supabase lub lokalnie). Nie rzuca."""
    if not avatar_url:
        return
    try:
        if _PUBLIC_MARKER in avatar_url and supabase_configured():
            filename = avatar_url.rsplit("/", 1)[-1]
            del_url = (f"{settings.SUPABASE_URL}/storage/v1/object/"
                       f"{settings.SUPABASE_BUCKET}/{filename}")
            headers = {"Authorization": f"Bearer {settings.SUPABASE_KEY}"}
            async with httpx.AsyncClient(timeout=10) as client:
                await client.delete(del_url, headers=headers)
        elif "/static/avatars/" in avatar_url:
            filename = avatar_url.rsplit("/static/avatars/", 1)[-1]
            path = os.path.join(AVATAR_LOCAL_DIR, filename)
            if os.path.exists(path):
                os.remove(path)
    except Exception as exc:
        logger.warning("Nie udalo sie usunac starego avatara %s: %s", avatar_url, exc)
