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

    # Memory vault — file-based long-form memory (profile, daily notes,
    # project knowledge). See vault/vault.py.
    vault_root: str = "./vault"

    # Files — local storage for user-uploaded / DAWN-generated files.
    files_root: str = "./files"

    # Web search
    brave_search_api_key: Optional[str] = None

    # Auth tiers
    dawn_api_keys: Optional[str] = None

    # v5.0 - OSINT
    shodan_api_key: Optional[str] = None

    # OCR
    tesseract_cmd: Optional[str] = None

    # CORS — comma-separated list. Defaults cover the common local dev ports
    # (Next.js picks 3000, or 3001 if 3000 is taken). Override with
    # ALLOWED_ORIGINS in .env for production.
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # Public base URL of the DAWN API — used to build the OAuth redirect_uri
    # for MCP OAuth flows (e.g. "https://dawn-api.regentplatform.com"). Falls
    # back to localhost:8000 for local dev.
    dawn_public_url: str = "http://localhost:8000"

    # Fernet key used to encrypt MCP OAuth tokens at rest (access_token,
    # refresh_token, client_secret). Must be a 32-byte urlsafe base64 key
    # (generate with `python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"`). If unset, tokens are stored
    # in plaintext (dev fallback) and a warning is logged.
    dawn_token_encryption_key: Optional[str] = None

    # GitHub App credentials — used by the GitHub integration (tools/github.py
    # + routers/github_webhooks.py). Register a GitHub App in the org, generate
    # a private key, and set these the same way other secrets are handled.
    github_app_id: Optional[str] = None
    github_app_private_key: Optional[str] = None
    github_webhook_secret: Optional[str] = None
    # The GitHub App's own bot username — used to ignore events DAWN itself
    # authored (loop prevention).
    github_bot_username: Optional[str] = None

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
