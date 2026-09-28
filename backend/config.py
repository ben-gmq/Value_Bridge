"""Settings from the environment. The app refuses to start without the required keys (playbook §9.1)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str                      # the application role (vb_app) — DML only (§6.6)
    migration_database_url: str            # the owner role (vb_owner) — migrations only
    jwt_secret_key: str                    # env only, never a fallback (§9.1)
    frontend_url: str = "http://localhost:5173"
    # D-11: accounts are FTC staff only. Comma-separated email domains, e.g. "fortience.com".
    allowed_email_domains: str
    token_days_default: int = 1            # scaffold §1: 1 day, 30 with remember-me
    token_days_remember: int = 30
    max_body_bytes: int = 1_048_576        # ingress cap for ordinary JSON routes (R2-S8)

    @property
    def email_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if len(s.jwt_secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    if not s.email_domains:
        raise RuntimeError("ALLOWED_EMAIL_DOMAINS must name at least one FTC domain")
    return s
