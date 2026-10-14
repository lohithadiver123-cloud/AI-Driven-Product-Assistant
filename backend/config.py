"""
Application configuration settings.
Centralizes all configurable values for the PM Copilot backend.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables with sensible defaults."""

    # MongoDB configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME: str = os.getenv("DB_NAME", "pm_copilot")

    # JWT configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "pm-copilot-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # AI / Gemini configuration (Milestone 2 & 3 Pure AI)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # AI / OpenRouter configuration (free tier — OpenAI-compatible)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

    # AI / Groq configuration (Milestone 2)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # AI / Mistral configuration (free Experiment tier, OpenAI-compatible API)
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

    # CORS configuration - allow all origins for development
    CORS_ORIGINS: list = ["*"]

    # File upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: set = {"csv", "json"}

    # Feedback source types
    FEEDBACK_SOURCES: list = [
        "app_review",
        "support_ticket",
        "survey",
        "social_media",
        "email",
        "other",
    ]

    # Feedback categories
    FEEDBACK_CATEGORIES: list = [
        "bug_report",
        "feature_request",
        "performance_issue",
        "general_feedback",
    ]

    # Pagination defaults
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100


# Singleton settings instance
settings = Settings()
