import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache

_backend_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv_path = _backend_dir / ".env"

from dotenv import load_dotenv
load_dotenv(load_dotenv_path, override=True)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Precosquin API"
    PROJECT_DESCRIPTION: str = "API para gestión de artistas del festival Precosquin"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    API_V1_PREFIX: str = "/v1"

    CORS_ORIGINS: List[str] = [
        "http://localhost:4200",
        "http://localhost:3000",
        "https://app.precosquin.com",
        "https://staging.precosquin.com",
        "https://precosquin.com",
        "https://precosquinpiramides.com",
        "http://precosquinpiramides.com",
        "https://precosquin-frontend.onrender.com",
        "https://precosquin-backend.onrender.com",
    ]
    ALLOWED_HOSTS: List[str] = ["*"]

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_ANON_KEY: str = ""

    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@precosquin.com"
    SENDGRID_FROM_NAME: str = "Precosquin"

    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = ""
    WHATSAPP_API_VERSION: str = "v18.0"

    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "audio/mpeg",
        "audio/wav",
        "video/mp4",
        "video/quicktime",
    ]

    RATE_LIMIT_DEFAULT: int = 1000
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    LOG_LEVEL: str = "info"

    FRONTEND_URL: str = "http://localhost:4200"
    API_URL: str = "http://localhost:8000"

    class Config:
        env_file = str(load_dotenv_path)
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()