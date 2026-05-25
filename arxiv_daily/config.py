from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _path_from_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    timezone: str = "Asia/Shanghai"
    arxiv_base_url: str = "https://export.arxiv.org/api/query"
    arxiv_page_size: int = 100
    arxiv_max_results: int = 300
    arxiv_request_delay_seconds: float = 5.0
    arxiv_user_agent: str = "jushen-zhidu/0.1 (arXiv API client)"
    arxiv_retry_count: int = 3
    arxiv_retry_base_delay_seconds: float = 30.0
    arxiv_daily_network_fetch_limit: int = 5
    arxiv_cache_enabled: bool = True
    arxiv_empty_cache_ttl_seconds: float = 1800.0
    arxiv_rate_limit_path: Optional[Path] = None
    request_timeout_seconds: float = 30.0
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.7-max"
    qwen_vision_model: str = "qwen3.6-plus"
    qwen_pdf_model: str = "qwen-doc-turbo"
    qwen_temperature: float = 0.2
    qwen_max_tokens_single: int = 1800
    qwen_max_tokens_full_text: int = 4096
    full_text_max_chars: int = 90_000
    full_text_figure_limit: int = 6
    full_text_pdf_upload_enabled: bool = True

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def effective_arxiv_rate_limit_path(self) -> Path:
        if self.arxiv_rate_limit_path is not None:
            return self.arxiv_rate_limit_path
        return self.database_path.parent / ".arxiv-api-rate-limit"

    @property
    def effective_arxiv_request_delay_seconds(self) -> float:
        return max(3.0, self.arxiv_request_delay_seconds)


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def get_settings() -> Settings:
    return Settings(
        database_path=_path_from_env("ARXIV_DAILY_DB", "data/arxiv_daily.sqlite3"),
        timezone=os.getenv("ARXIV_DAILY_TIMEZONE", "Asia/Shanghai"),
        arxiv_base_url=os.getenv("ARXIV_BASE_URL", "https://export.arxiv.org/api/query"),
        arxiv_page_size=int(os.getenv("ARXIV_PAGE_SIZE", "100")),
        arxiv_max_results=int(os.getenv("ARXIV_MAX_RESULTS", "300")),
        arxiv_request_delay_seconds=float(os.getenv("ARXIV_REQUEST_DELAY_SECONDS", "5.0")),
        arxiv_user_agent=os.getenv("ARXIV_USER_AGENT", "jushen-zhidu/0.1 (arXiv API client)"),
        arxiv_retry_count=int(os.getenv("ARXIV_RETRY_COUNT", "3")),
        arxiv_retry_base_delay_seconds=float(os.getenv("ARXIV_RETRY_BASE_DELAY_SECONDS", "30")),
        arxiv_daily_network_fetch_limit=int(os.getenv("ARXIV_DAILY_NETWORK_FETCH_LIMIT", "5")),
        arxiv_cache_enabled=_bool_from_env("ARXIV_CACHE_ENABLED", True),
        arxiv_empty_cache_ttl_seconds=float(os.getenv("ARXIV_EMPTY_CACHE_TTL_SECONDS", "1800")),
        arxiv_rate_limit_path=(
            _path_from_env("ARXIV_RATE_LIMIT_FILE", "")
            if os.getenv("ARXIV_RATE_LIMIT_FILE")
            else None
        ),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        qwen_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        qwen_base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        qwen_model=os.getenv("QWEN_MODEL", "qwen3.7-max"),
        qwen_vision_model=os.getenv("QWEN_VISION_MODEL", "qwen3.6-plus"),
        qwen_pdf_model=os.getenv("QWEN_PDF_MODEL", "qwen-doc-turbo"),
        qwen_temperature=float(os.getenv("QWEN_TEMPERATURE", "0.2")),
        qwen_max_tokens_single=int(os.getenv("QWEN_MAX_TOKENS_SINGLE", "1800")),
        qwen_max_tokens_full_text=int(os.getenv("QWEN_MAX_TOKENS_FULL_TEXT", "4096")),
        full_text_max_chars=int(os.getenv("FULL_TEXT_MAX_CHARS", "90000")),
        full_text_figure_limit=int(os.getenv("FULL_TEXT_FIGURE_LIMIT", "6")),
        full_text_pdf_upload_enabled=_bool_from_env("FULL_TEXT_PDF_UPLOAD_ENABLED", True),
    )
