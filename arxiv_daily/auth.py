from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import Response
from sqlmodel import Session, select

from .config import Settings
from .models import User, UserSession, utc_now

PASSWORD_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260_000
ROLE_LEVELS = {"viewer": 10, "editor": 20, "admin": 30}
ROLE_LABELS = {"viewer": "阅读者", "editor": "编辑者", "admin": "管理员"}


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_role(role: str) -> str:
    role = role.strip().lower()
    return role if role in ROLE_LEVELS else "viewer"


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def role_allows(actual_role: str, required_role: str) -> bool:
    return ROLE_LEVELS.get(actual_role, 0) >= ROLE_LEVELS.get(required_role, 0)


def validate_username(username: str) -> Optional[str]:
    username = normalize_username(username)
    if not username:
        return "用户名不能为空。"
    if len(username) < 3 or len(username) > 40:
        return "用户名长度需要在 3 到 40 个字符之间。"
    allowed = set(string.ascii_lowercase + string.digits + "._-")
    if any(char not in allowed for char in username):
        return "用户名只能包含小写字母、数字、点、下划线和短横线。"
    return None


def validate_password(password: str, username: str = "") -> Optional[str]:
    if len(password) < 10:
        return "密码至少需要 10 个字符。"
    normalized_username = normalize_username(username)
    if normalized_username and normalized_username in password.lower():
        return "密码不能包含用户名。"
    classes = [
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    ]
    if len(password) < 16 and sum(1 for item in classes if item) < 3:
        return "短密码需要至少包含大小写字母、数字、符号中的三类。"
    return None


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{PASSWORD_SCHEME}${iterations}${salt}${encoded_digest}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, raw_iterations, salt, expected = encoded_hash.split("$", 3)
        iterations = int(raw_iterations)
    except (ValueError, TypeError):
        return False
    if scheme != PASSWORD_SCHEME:
        return False
    actual = hash_password(password, iterations=iterations, salt=salt).split("$", 3)[3]
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def user_count(session: Session) -> int:
    return len(session.exec(select(User.id)).all())


def active_admin_count(session: Session) -> int:
    return len(session.exec(select(User).where(User.role == "admin", User.enabled == True)).all())  # noqa: E712


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str,
    display_name: str = "",
    must_change_password: bool = True,
) -> User:
    normalized_username = normalize_username(username)
    user = User(
        username=normalized_username,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=normalize_role(role),
        enabled=True,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def find_user_by_username(session: Session, username: str) -> Optional[User]:
    return session.exec(select(User).where(User.username == normalize_username(username))).first()


def create_user_session(session: Session, user: User, settings: Settings, user_agent: str = "") -> str:
    raw_token = secrets.token_urlsafe(32)
    now = utc_now()
    user_session = UserSession(
        token_hash=token_hash(raw_token),
        user_id=user.id or 0,
        created_at=now,
        expires_at=now + timedelta(days=settings.auth_session_days),
        last_seen_at=now,
        user_agent=user_agent[:500],
    )
    user.last_login_at = now
    user.updated_at = now
    session.add(user_session)
    session.add(user)
    session.commit()
    return raw_token


def read_current_user(session: Session, token: str) -> Tuple[Optional[User], Optional[UserSession]]:
    if not token:
        return None, None
    user_session = session.get(UserSession, token_hash(token))
    if user_session is None or user_session.revoked_at is not None:
        return None, None
    if _as_utc(user_session.expires_at) <= utc_now():
        user_session.revoked_at = utc_now()
        session.add(user_session)
        session.commit()
        return None, None
    user = session.get(User, user_session.user_id)
    if user is None or not user.enabled:
        user_session.revoked_at = utc_now()
        session.add(user_session)
        session.commit()
        return None, None
    user_session.last_seen_at = utc_now()
    session.add(user_session)
    session.commit()
    session.refresh(user)
    session.refresh(user_session)
    return user, user_session


def revoke_session(session: Session, token: str) -> None:
    if not token:
        return
    user_session = session.get(UserSession, token_hash(token))
    if user_session is not None and user_session.revoked_at is None:
        user_session.revoked_at = utc_now()
        session.add(user_session)
        session.commit()


def revoke_user_sessions(session: Session, user_id: int, *, keep_token_hash: str = "") -> int:
    rows = session.exec(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at == None)  # noqa: E711
    ).all()
    count = 0
    for row in rows:
        if keep_token_hash and row.token_hash == keep_token_hash:
            continue
        row.revoked_at = utc_now()
        session.add(row)
        count += 1
    if count:
        session.commit()
    return count


def set_login_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )


def clear_login_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.auth_cookie_name, httponly=True, secure=settings.auth_cookie_secure, samesite="lax")


def request_next_url(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    return path


def safe_next_url(raw_next: str, default: str = "/") -> str:
    if not raw_next:
        return default
    parsed = urlsplit(raw_next)
    if parsed.scheme or parsed.netloc or not raw_next.startswith("/") or raw_next.startswith("//"):
        return default
    return raw_next
