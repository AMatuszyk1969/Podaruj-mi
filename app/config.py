from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "Podaruj mi"
    FRONTEND_URL: str = "http://localhost:5173"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite:///./app.db"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200   # 30 dni
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90
    ACTIVATION_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 2

    # Mail
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_SERVER: str
    MAIL_PORT: int = 587
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # Supabase (opcjonalne w dev)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_BUCKET: str = "avatars"

    # Rate limiting
    LOGIN_RATE_LIMIT: str = "5/minute"
    GENERAL_RATE_LIMIT: str = "100/minute"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
