"""Settings from the environment. The app refuses to start without the required keys (playbook §9.1)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str                      # the application role (vb_app) — DML only (§6.6)
    migration_database_url: str            # the owner role (vb_owner) — migrations only
    jwt_secret_key: str                    # env only, never a fallback (§9.1)
    row_token_key: str                     # signs import row tokens; never the JWT secret (4a-R3)
    frontend_url: str = "http://localhost:5180"
    # D-11: accounts are FTC staff only. Comma-separated email domains, e.g. "fortience.com".
    allowed_email_domains: str
    token_days_default: int = 1            # scaffold §1: 1 day, 30 with remember-me
    token_days_remember: int = 30
    max_body_bytes: int = 1_048_576        # ingress cap for ordinary JSON routes (R2-S8)
    # H1: the anonymous first-run setup exists only where this is switched on (local dev).
    # Cloud environments create the first admin with `python -m seeds.create_admin`.
    allow_first_run_setup: bool = False
    enable_api_docs: bool = False          # M9: /docs, /redoc, /openapi.json off by default

    @property
    def email_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if len(s.jwt_secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    if len(s.row_token_key) < 32 or s.row_token_key == s.jwt_secret_key:
        raise RuntimeError("ROW_TOKEN_KEY must be at least 32 characters and differ from JWT_SECRET_KEY")
    if not s.email_domains:
        raise RuntimeError("ALLOWED_EMAIL_DOMAINS must name at least one FTC domain")
    return s
