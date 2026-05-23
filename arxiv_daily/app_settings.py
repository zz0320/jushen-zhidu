from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional

from sqlmodel import Session, select

from .config import Settings
from .models import AppSetting, utc_now

QWEN_SETTING_KEYS = {
    "qwen_api_key",
    "qwen_base_url",
    "qwen_model",
    "qwen_vision_model",
    "qwen_pdf_model",
    "qwen_temperature",
    "qwen_max_tokens_single",
    "qwen_max_tokens_full_text",
    "qwen_max_tokens_daily",
    "daily_top_n",
    "daily_abstract_chars",
    "full_text_max_chars",
    "full_text_figure_limit",
    "full_text_pdf_upload_enabled",
}


def get_app_settings(session: Session) -> Dict[str, str]:
    rows = session.exec(select(AppSetting)).all()
    return {row.key: row.value for row in rows}


def set_app_setting(session: Session, key: str, value: str) -> None:
    existing = session.get(AppSetting, key)
    if existing is None:
        session.add(AppSetting(key=key, value=value))
        return
    existing.value = value
    existing.updated_at = utc_now()
    session.add(existing)


def delete_app_setting(session: Session, key: str) -> None:
    existing = session.get(AppSetting, key)
    if existing is not None:
        session.delete(existing)


def resolve_runtime_settings(session: Session, base_settings: Settings) -> Settings:
    saved = get_app_settings(session)
    api_key = saved.get("qwen_api_key") or base_settings.qwen_api_key
    return replace(
        base_settings,
        qwen_api_key=api_key,
        qwen_base_url=saved.get("qwen_base_url") or base_settings.qwen_base_url,
        qwen_model=saved.get("qwen_model") or base_settings.qwen_model,
        qwen_vision_model=saved.get("qwen_vision_model") or base_settings.qwen_vision_model,
        qwen_pdf_model=saved.get("qwen_pdf_model") or base_settings.qwen_pdf_model,
        qwen_temperature=_float_setting(saved.get("qwen_temperature"), base_settings.qwen_temperature),
        qwen_max_tokens_single=_int_setting(
            saved.get("qwen_max_tokens_single"), base_settings.qwen_max_tokens_single
        ),
        qwen_max_tokens_full_text=_int_setting(
            saved.get("qwen_max_tokens_full_text"), base_settings.qwen_max_tokens_full_text
        ),
        qwen_max_tokens_daily=_int_setting(saved.get("qwen_max_tokens_daily"), base_settings.qwen_max_tokens_daily),
        daily_top_n=_int_setting(saved.get("daily_top_n"), base_settings.daily_top_n),
        daily_abstract_chars=_int_setting(saved.get("daily_abstract_chars"), base_settings.daily_abstract_chars),
        full_text_max_chars=_int_setting(saved.get("full_text_max_chars"), base_settings.full_text_max_chars),
        full_text_figure_limit=_int_setting(
            saved.get("full_text_figure_limit"), base_settings.full_text_figure_limit
        ),
        full_text_pdf_upload_enabled=_bool_setting(
            saved.get("full_text_pdf_upload_enabled"), base_settings.full_text_pdf_upload_enabled
        ),
    )


def qwen_settings_view(session: Session, base_settings: Settings) -> Dict[str, object]:
    saved = get_app_settings(session)
    effective = resolve_runtime_settings(session, base_settings)
    api_key_source: Optional[str] = None
    if saved.get("qwen_api_key"):
        api_key_source = "界面保存"
    elif base_settings.qwen_api_key:
        api_key_source = "环境变量"
    return {
        "saved": saved,
        "effective": effective,
        "api_key_configured": bool(effective.qwen_api_key),
        "api_key_source": api_key_source or "未配置",
        "base_url_source": "界面保存" if saved.get("qwen_base_url") else "环境变量/默认值",
        "model_source": "界面保存" if saved.get("qwen_model") else "环境变量/默认值",
        "vision_model_source": "界面保存" if saved.get("qwen_vision_model") else "环境变量/默认值",
        "pdf_model_source": "界面保存" if saved.get("qwen_pdf_model") else "环境变量/默认值",
    }


def save_qwen_form(
    session: Session,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens_single: int,
    max_tokens_full_text: int,
    max_tokens_daily: int,
    daily_top_n: int,
    daily_abstract_chars: int,
    full_text_max_chars: int,
    full_text_figure_limit: int,
    clear_api_key: bool = False,
    vision_model: str = "",
    qwen_pdf_model: str = "",
    full_text_pdf_upload_enabled: bool = True,
) -> None:
    if clear_api_key:
        delete_app_setting(session, "qwen_api_key")
    elif api_key.strip():
        set_app_setting(session, "qwen_api_key", api_key.strip())

    set_app_setting(session, "qwen_base_url", base_url.strip())
    if model.strip():
        set_app_setting(session, "qwen_model", model.strip())
    if vision_model.strip():
        set_app_setting(session, "qwen_vision_model", vision_model.strip())
    if qwen_pdf_model.strip():
        set_app_setting(session, "qwen_pdf_model", qwen_pdf_model.strip())
    set_app_setting(session, "qwen_temperature", str(max(0.0, min(2.0, temperature))))
    set_app_setting(session, "qwen_max_tokens_single", str(max(256, max_tokens_single)))
    set_app_setting(session, "qwen_max_tokens_full_text", str(max(512, max_tokens_full_text)))
    set_app_setting(session, "qwen_max_tokens_daily", str(max(512, max_tokens_daily)))
    set_app_setting(session, "daily_top_n", str(max(1, daily_top_n)))
    set_app_setting(session, "daily_abstract_chars", str(max(200, daily_abstract_chars)))
    set_app_setting(session, "full_text_max_chars", str(max(10_000, full_text_max_chars)))
    set_app_setting(session, "full_text_figure_limit", str(max(0, min(12, full_text_figure_limit))))
    set_app_setting(session, "full_text_pdf_upload_enabled", "true" if full_text_pdf_upload_enabled else "false")
    session.commit()


def _float_setting(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def _int_setting(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _bool_setting(value: Optional[str], default: bool) -> bool:
    if value in (None, ""):
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}
