import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    secret_key: str
    gemini_api_key: str
    model_workout: str
    model_fallback: str
    database_url: str
    cookie_secure: bool


def get_settings() -> Settings:
    secret = os.getenv("SECRET_KEY", "")
    if len(secret) < 32 or secret.startswith("replace-"):
        raise RuntimeError("Set a random SECRET_KEY of at least 32 characters in .env")
    return Settings(
        secret_key=secret,
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        model_workout=os.getenv("MODEL_WORKOUT", "gemini-3.5-flash"),
        model_fallback=os.getenv("MODEL_FALLBACK", "gemini-3.5-flash-lite"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./fitbuddy.db"),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )
