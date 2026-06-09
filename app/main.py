from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from fastapi.responses import RedirectResponse

from app.config import settings
from app.utils.observability import configure_logging, init_sentry

# Logowanie i monitoring błędów – jak najwcześniej, by łapać też błędy startu
configure_logging()
init_sentry()

from app.database import engine
from app.models import *  # noqa: F401, F403, E402  – rejestruje modele w Base
from app.database import Base  # noqa: E402
from app.routers import auth, families, friends, occasions, pages, users  # noqa: E402
from app.services.scheduler import start_scheduler, stop_scheduler  # noqa: E402
from app.utils.cookie_auth import _LoginRequired  # noqa: E402
from app.utils.csrf import CSRFMiddleware  # noqa: E402

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.GENERAL_RATE_LIMIT])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)  # tworzy tabele jesli nie istnieja (dev)
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="API platformy do koordynacji prezentow",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF ochrona dla stron HTML (nie dotyczy tras /api/*)
app.add_middleware(CSRFMiddleware)


# Przekierowanie do /login gdy trasa wymaga autentykacji
@app.exception_handler(_LoginRequired)
async def _login_required_handler(request, exc):
    return RedirectResponse("/login", status_code=303)

# ── Routers ───────────────────────────────────────────────────────────────────

PREFIX = settings.API_V1_PREFIX

app.include_router(pages.router)                      # strony HTML (bez prefiksu)
app.include_router(auth.router,      prefix=PREFIX)
app.include_router(users.router,     prefix=PREFIX)
app.include_router(friends.router,   prefix=PREFIX)
app.include_router(families.router,  prefix=PREFIX)
app.include_router(occasions.router, prefix=PREFIX)

# ── Static files (awatary w dev) ──────────────────────────────────────────────

import os  # noqa: E402
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}
