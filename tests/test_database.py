from sqlalchemy import create_engine, text

from arxiv_daily.database import create_db_and_tables


def test_create_db_migrates_abstract_translation_title_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE paperabstracttranslation (
                    id INTEGER PRIMARY KEY,
                    arxiv_id VARCHAR NOT NULL,
                    content TEXT,
                    model VARCHAR NOT NULL,
                    generated_at DATETIME NOT NULL
                )
                """
            )
        )

    create_db_and_tables(engine)

    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(paperabstracttranslation)")).mappings().all()
    assert "title_content" in {column["name"] for column in columns}


def test_create_db_migrates_paper_affiliations_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE paper (
                    arxiv_id VARCHAR PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    abstract TEXT,
                    authors_json TEXT,
                    primary_category VARCHAR NOT NULL,
                    categories_json TEXT,
                    fetched_for_date VARCHAR NOT NULL,
                    relevance_score FLOAT NOT NULL,
                    matched_keywords_json TEXT,
                    created_at DATETIME NOT NULL,
                    refreshed_at DATETIME NOT NULL
                )
                """
            )
        )

    create_db_and_tables(engine)

    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(paper)")).mappings().all()
    assert "affiliations_json" in {column["name"] for column in columns}


def test_create_db_migrates_fetch_run_saved_papers_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE arxivfetchrun (
                    id INTEGER PRIMARY KEY,
                    target_date VARCHAR NOT NULL,
                    run_date VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    force_refresh BOOLEAN NOT NULL,
                    network_requests INTEGER NOT NULL,
                    cached_pages INTEGER NOT NULL,
                    message TEXT,
                    created_at DATETIME NOT NULL,
                    finished_at DATETIME
                )
                """
            )
        )

    create_db_and_tables(engine)

    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(arxivfetchrun)")).mappings().all()
    assert "saved_papers" in {column["name"] for column in columns}


def test_create_db_migrates_full_text_summary_figures_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE paperfulltextsummary (
                    id INTEGER PRIMARY KEY,
                    arxiv_id VARCHAR NOT NULL,
                    content TEXT,
                    model VARCHAR NOT NULL,
                    source_url VARCHAR NOT NULL,
                    source_chars INTEGER NOT NULL,
                    used_chars INTEGER NOT NULL,
                    truncated BOOLEAN NOT NULL,
                    generated_at DATETIME NOT NULL
                )
                """
            )
        )

    create_db_and_tables(engine)

    with engine.connect() as connection:
        columns = connection.execute(text("PRAGMA table_info(paperfulltextsummary)")).mappings().all()
    assert "figures_json" in {column["name"] for column in columns}


def test_create_db_creates_auth_tables():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    create_db_and_tables(engine)

    with engine.connect() as connection:
        user_columns = connection.execute(text("PRAGMA table_info(user)")).mappings().all()
        session_columns = connection.execute(text("PRAGMA table_info(usersession)")).mappings().all()
    assert {"username", "password_hash", "role", "enabled", "must_change_password"}.issubset(
        {column["name"] for column in user_columns}
    )
    assert {"token_hash", "user_id", "expires_at", "revoked_at"}.issubset(
        {column["name"] for column in session_columns}
    )
