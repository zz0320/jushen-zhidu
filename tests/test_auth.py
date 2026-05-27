from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from arxiv_daily.app import create_app
from arxiv_daily.auth import create_user, verify_password
from arxiv_daily.config import Settings
from arxiv_daily.models import User, UserSession
from auth_helpers import TEST_PASSWORD, authenticated_client


def _app_and_engine(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    app = create_app(settings=Settings(database_path=tmp_path / "test.sqlite3"), engine=engine)
    return app, engine


def test_first_run_requires_admin_setup_and_creates_admin(tmp_path):
    app, engine = _app_and_engine(tmp_path)
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/setup-admin")

    setup_page = client.get("/setup-admin")
    assert setup_page.status_code == 200
    assert "创建管理员账号" in setup_page.text

    created = client.post(
        "/setup-admin",
        data={
            "username": "Chief.Admin",
            "display_name": "总管理员",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            "next": "/users",
        },
        follow_redirects=False,
    )

    assert created.status_code == 303
    assert created.headers["location"].startswith("/users")
    assert "jushen_session" in created.headers["set-cookie"]
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "chief.admin")).one()
        assert user.role == "admin"
        assert user.enabled is True
        assert verify_password(TEST_PASSWORD, user.password_hash)


def test_login_logout_and_admin_page_access(tmp_path):
    app, engine = _app_and_engine(tmp_path)
    with Session(engine) as session:
        create_user(
            session,
            username="admin",
            display_name="Admin",
            password=TEST_PASSWORD,
            role="admin",
            must_change_password=False,
        )
    client = TestClient(app)

    bad_login = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password", "next": "/settings"},
        follow_redirects=False,
    )
    assert bad_login.headers["location"].startswith("/login")

    login = client.post(
        "/login",
        data={"username": "admin", "password": TEST_PASSWORD, "next": "/settings"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"].startswith("/settings")
    assert client.get("/settings").status_code == 200

    logout = client.post("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert client.get("/settings", follow_redirects=False).headers["location"].startswith("/login")


def test_role_permissions_separate_reader_editor_and_admin(tmp_path):
    app, engine = _app_and_engine(tmp_path)

    viewer = authenticated_client(app, engine, role="viewer")
    assert viewer.get("/").status_code == 200
    assert viewer.post("/fetch-jobs", data={"day": "2026-05-25"}).status_code == 403

    editor = authenticated_client(app, engine, role="editor")
    assert editor.post("/settings/qwen", data={}, follow_redirects=False).headers["location"].startswith("/?error=")

    admin = authenticated_client(app, engine, role="admin")
    users_page = admin.get("/users")
    assert users_page.status_code == 200
    assert "用户管理" in users_page.text


def test_cross_origin_post_is_rejected(tmp_path):
    app, engine = _app_and_engine(tmp_path)
    admin = authenticated_client(app, engine, role="admin")

    response = admin.post(
        "/users",
        data={
            "username": "bad.origin",
            "role": "viewer",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
        headers={"origin": "https://attacker.example"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")
    with Session(engine) as session:
        assert session.exec(select(User).where(User.username == "bad.origin")).first() is None


def test_admin_creates_user_and_reset_forces_password_change(tmp_path):
    app, engine = _app_and_engine(tmp_path)
    admin = authenticated_client(app, engine, role="admin")

    response = admin.post(
        "/users",
        data={
            "username": "reader.one",
            "display_name": "Reader One",
            "role": "viewer",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("/users?message=")

    reader = TestClient(app)
    login = reader.post(
        "/login",
        data={"username": "reader.one", "password": TEST_PASSWORD, "next": "/"},
        follow_redirects=False,
    )
    assert login.headers["location"].startswith("/account/password")
    assert reader.get("/", follow_redirects=False).headers["location"].startswith("/account/password")

    new_password = "ReaderPass123!"
    changed = reader.post(
        "/account/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": new_password,
            "new_password_confirm": new_password,
        },
        follow_redirects=False,
    )
    assert changed.headers["location"].startswith("/account/password?message=")
    assert reader.get("/", follow_redirects=False).status_code == 200

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "reader.one")).one()
        assert user.must_change_password is False
        assert session.exec(select(UserSession).where(UserSession.user_id == user.id)).first() is not None
