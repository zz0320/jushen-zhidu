from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from arxiv_daily.auth import create_user

TEST_PASSWORD = "TestPass123!"


def authenticated_client(app, engine: Engine, *, role: str = "admin") -> TestClient:
    with Session(engine) as session:
        create_user(
            session,
            username=f"{role}-user",
            display_name=f"{role.title()} User",
            password=TEST_PASSWORD,
            role=role,
            must_change_password=False,
        )
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": f"{role}-user", "password": TEST_PASSWORD, "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client
