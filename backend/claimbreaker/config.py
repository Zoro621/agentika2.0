from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

if not os.getenv("CB_PARSER_MODE"):
    load_dotenv(".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CB_", env_file=None if os.getenv("CB_PARSER_MODE") else ".env", extra="ignore"
    )
    data_dir: Path = Path(".claimbreaker")
    database_url: str = "sqlite:///.claimbreaker/claimbreaker.db"
    session_secret: str = ""
    secure_cookies: bool = False
    offline: bool = False
    provider: Literal["auto", "openai", "ollama", "deterministic"] = "auto"
    openai_model: str = "gpt-6-luna"
    openai_reasoning: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    runner: str = "auto"
    runner_url: str = ""
    runner_token: str = ""
    e2b_template: str = "claimbreaker-cpu-v1"
    docker_image: str = "claimbreaker-runner:0.1.0"
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "claimbreaker"
    max_upload: int = 50 * 1024 * 1024
    max_extracted: int = 250 * 1024 * 1024
    max_entries: int = 2000
    max_pdf_pages: int = 100
    retention_days: int = 7
    max_case_seconds: int = 600
    max_agent_steps: int = 24
    max_session_cases: int = 12

    def prepare(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.session_secret:
            import secrets

            secret_path = self.data_dir / "session.key"
            if not secret_path.exists():
                secret_path.write_text(secrets.token_urlsafe(48))
            self.session_secret = secret_path.read_text().strip()


@lru_cache
def settings():
    value = Settings()
    value.prepare()
    return value
