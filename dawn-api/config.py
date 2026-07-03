from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str

    # LLM
    llm_mode: str = "deepseek"  # "deepseek" | "local"

    # DeepSeek
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Local llama.cpp
    local_model_path: Optional[str] = None
    local_model_n_ctx: int = 4096
    local_model_n_threads: int = 4

    # Auth
    dawn_api_key: str = "dev-key"
    
    # Tools
    filesystem_sandbox_root: str = "./sandbox"
    skills_install_root: str = "./installed_skills"
    tools_enabled: str = "filesystem,git,websearch,install_skill,terminal,web_fetch"

    # Web search
    brave_search_api_key: Optional[str] = None

    # Auth tiers
    dawn_api_keys: Optional[str] = None  # JSON: {"sk-owner-xxx": "owner", "sk-app-yyy": "service"}

    # OCR — optional explicit path to the tesseract binary. Leave unset on
    # Linux (VPS deploy) where `apt-get install tesseract-ocr` puts it on
    # PATH already. On Windows dev machines, PATH resolution is often
    # session/shell-dependent (PowerShell vs cmd, User vs Machine scope,
    # requires a fresh terminal after install) — setting this explicitly
    # sidesteps all of that.
    # e.g. in .env: TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
    tesseract_cmd: Optional[str] = None

    # CORS
    allowed_origins: str = "http://localhost:3000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
