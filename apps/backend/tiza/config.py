from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TIZA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/tiza.db"
    demo_mode: bool = True
    demo_access_code: str = Field(default="246810", min_length=6, max_length=64)
    agent_mode: Literal["deterministic_demo", "bedrock"] = "deterministic_demo"
    session_secure: bool = False
    session_ttl_hours: int = 24
    material_dir: Path = Path("data/materials")
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_key: str | None = None
    supabase_material_bucket: str = "materials"
    redis_url: str = "redis://localhost:6379/0"

    @model_validator(mode="after")
    def production_is_explicit(self):
        if not self.demo_mode and (
            not self.supabase_url or not self.supabase_anon_key or not self.supabase_service_key
        ):
            raise ValueError("Supabase URL, anon key, and backend service key are required outside demo mode")
        if not self.demo_mode and self.agent_mode != "bedrock":
            raise ValueError("Production requires TIZA_AGENT_MODE=bedrock")
        if not self.demo_mode and not self.session_secure:
            raise ValueError("Production requires secure session cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
