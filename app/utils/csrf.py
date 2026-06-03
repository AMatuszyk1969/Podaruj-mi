"""
CSRF protection — Double Submit Cookie pattern.

Jak to działa:
  1. Każda odpowiedź GET ustawia ciasteczko pm_csrf (httponly=False, żeby JS mogło go czytać).
  2. Dla żądań POST base.html wstrzykuje token przez:
     - hx-headers dla HTMX (nagłówek X-CSRFToken),
     - hidden field csrf_token dla zwykłych formularzy (JS submit-listener).
  3. Middleware porównuje token z ciasteczka z tokenem z nagłówka/pola formularza.
  4. Pliki multipart (upload avatara) są pomijane — przeglądarka wymusza same-origin
     dla <input type="file">, a endpoint wymaga uwierzytelnienia.
  5. Trasy /api/* używają Bearer token — CSRF ich nie dotyczy.
"""
import hmac
import secrets
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

CSRF_COOKIE = "pm_csrf"
CSRF_HEADER = "X-CSRFToken"
CSRF_FIELD  = "csrf_token"
_SAFE        = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_SKIP_PREFIX = ("/api/", "/health", "/static/", "/docs", "/redoc", "/openapi")


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Pomiń trasy API i zasoby statyczne
        if any(path.startswith(p) for p in _SKIP_PREFIX):
            return await call_next(request)

        if request.method not in _SAFE:
            cookie_token = request.cookies.get(CSRF_COOKIE, "")

            # 1. Nagłówek (HTMX / AJAX)
            request_token = request.headers.get(CSRF_HEADER, "")

            if not request_token:
                content_type = request.headers.get("content-type", "")
                if "multipart/form-data" in content_type:
                    # Upload pliku — bezpieczny bez CSRF (patrz docstring)
                    return await call_next(request)
                if "application/x-www-form-urlencoded" in content_type:
                    # 2. Pole formularza — czytamy i cachujemy body
                    body = await request.body()
                    request._body = body  # cache: Starlette re-użyje przy form()
                    parsed = parse_qs(body.decode(errors="replace"), keep_blank_values=True)
                    request_token = parsed.get(CSRF_FIELD, [""])[0]

            if not cookie_token or not request_token or \
               not hmac.compare_digest(cookie_token, request_token):
                return Response(
                    "Błąd CSRF: nieprawidłowy token. Odśwież stronę i spróbuj ponownie.",
                    status_code=403,
                    media_type="text/plain; charset=utf-8",
                )

        response = await call_next(request)

        # Ustaw ciasteczko CSRF jeśli nie istnieje (przy GET)
        if request.method in _SAFE and CSRF_COOKIE not in request.cookies:
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_urlsafe(32),
                httponly=False,   # JS musi móc je czytać
                samesite="lax",
                secure=not settings.is_development,
                max_age=86_400 * 7,
            )

        return response
