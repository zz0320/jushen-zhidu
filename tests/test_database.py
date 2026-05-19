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
