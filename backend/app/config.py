"""Settings loaded from the environment — one field per .env.example variable."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Root .env serves host-side runs (backend/ has no .env of its own); real env
    # vars — e.g. compose's environment block — always take precedence.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://agentdesk:agentdesk@localhost:5432/agentdesk"
    jwt_secret: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    vector_db_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    webhook_secret_encryption_key: str = ""
    slack_webhook_url: str = ""
    # Not in .env.example — dev default for the Vite server; override in deployment
    frontend_origin: str = "http://localhost:5173"
    # File storage (TRD Section 8): local disk in the prototype, 10MB default cap.
    # The size limit becomes Admin-configurable with the admin_config module (Phase 9).
    attachment_dir: str = "attachments"
    attachment_max_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
