from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path_from_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    report_dir: Path
    timezone: str = "Asia/Shanghai"
    arxiv_base_url: str = "https://export.arxiv.org/api/query"
    arxiv_page_size: int = 100
    arxiv_max_results: int = 300
    arxiv_request_delay_seconds: float = 3.2
    arxiv_retry_count: int = 3
    request_timeout_seconds: float = 30.0
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_temperature: float = 0.2
    qwen_max_tokens_single: int = 1800
    qwen_max_tokens_full_text: int = 4096
    qwen_max_tokens_daily: int = 4096
    daily_top_n: int = 40
    daily_abstract_chars: int = 1200
    full_text_max_chars: int = 90_000

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def get_settings() -> Settings:
    return Settings(
        database_path=_path_from_env("ARXIV_DAILY_DB", "data/arxiv_daily.sqlite3"),
        report_dir=_path_from_env("ARXIV_DAILY_REPORT_DIR", "reports"),
        timezone=os.getenv("ARXIV_DAILY_TIMEZONE", "Asia/Shanghai"),
        arxiv_base_url=os.getenv("ARXIV_BASE_URL", "https://export.arxiv.org/api/query"),
        arxiv_page_size=int(os.getenv("ARXIV_PAGE_SIZE", "100")),
        arxiv_max_results=int(os.getenv("ARXIV_MAX_RESULTS", "300")),
        arxiv_request_delay_seconds=float(os.getenv("ARXIV_REQUEST_DELAY_SECONDS", "3.2")),
        arxiv_retry_count=int(os.getenv("ARXIV_RETRY_COUNT", "3")),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        qwen_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        qwen_base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        qwen_model=os.getenv("QWEN_MODEL", "qwen-plus"),
        qwen_temperature=float(os.getenv("QWEN_TEMPERATURE", "0.2")),
        qwen_max_tokens_single=int(os.getenv("QWEN_MAX_TOKENS_SINGLE", "1800")),
        qwen_max_tokens_full_text=int(os.getenv("QWEN_MAX_TOKENS_FULL_TEXT", "4096")),
        qwen_max_tokens_daily=int(os.getenv("QWEN_MAX_TOKENS_DAILY", "4096")),
        daily_top_n=int(os.getenv("DAILY_TOP_N", "40")),
        daily_abstract_chars=int(os.getenv("DAILY_ABSTRACT_CHARS", "1200")),
        full_text_max_chars=int(os.getenv("FULL_TEXT_MAX_CHARS", "90000")),
    )
