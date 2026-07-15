from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Control Center Supabase (separate project for jarvis_* tables)
    cc_supabase_url: Optional[str] = None
    cc_supabase_service_key: Optional[str] = None

    # LLM
    llm_mode: str = "deepseek"

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
    tools_enabled: str = "filesystem,git,websearch,install_skill,terminal,web_fetch,ssh,nmap,osint,mcp"

    # Web search
    brave_search_api_key: Optional[str] = None

    # Auth tiers
    dawn_api_keys: Optional[str] = None

    # v5.0 - OSINT
    shodan_api_key: Optional[str] = None

    # OCR
    tesseract_cmd: Optional[str] = None

    # CORS
    allowed_origins: str = "http://localhost:3000"

    # Ingestion streaming config
    max_upload_gb: int = 30
    streaming_threshold_mb: int = 50
    max_ocr_pages: int = 5000
    max_pdf_pages: int = 10000
    max_spreadsheet_rows: int = 100000

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
