from __future__ import annotations

from datetime import date
from typing import Optional

import typer
from sqlmodel import Session

from .arxiv import FetchQuotaExceeded, fetch_papers_for_date
from .config import get_settings
from .database import build_engine, create_db_and_tables
from .dates import parse_day
from .defaults import init_default_config
from .app_settings import resolve_runtime_settings
from .summaries import generate_paper_full_text_summary, generate_paper_summary

main = typer.Typer(help="arXiv embodied intelligence paper workspace.")


def _display_model_name(value: str) -> str:
    return "智能模型" if "qwen" in (value or "").lower() else value


def _session() -> tuple[Session, object]:
    settings = get_settings()
    engine = build_engine(settings)
    create_db_and_tables(engine)
    session = Session(engine)
    init_default_config(session)
    return session, settings


@main.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the local FastAPI web app."""
    import uvicorn

    if reload:
        uvicorn.run("arxiv_daily.app:create_app", factory=True, host=host, port=port, reload=True)
        return

    from .app import create_app

    uvicorn.run(create_app, factory=True, host=host, port=port)


@main.command("init-db")
def init_db() -> None:
    """Create the SQLite database and seed default categories/keywords."""
    session, settings = _session()
    session.close()
    typer.echo(f"Initialized database at {settings.database_path}")


@main.command()
def fetch(
    day: Optional[str] = typer.Option(None, "--date", "-d", help="Date in YYYY-MM-DD, default today."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Ignore cached arXiv pages and call arXiv again."),
) -> None:
    """Fetch arXiv papers for one local day."""
    session, settings = _session()
    target_day = parse_day(day, settings.timezone)
    try:
        result = fetch_papers_for_date(session, target_day, settings, force_refresh=force_refresh)
    except FetchQuotaExceeded as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        session.close()
    typer.echo(
        f"{target_day}: fetched={result.fetched}, matched={result.matched}, "
        f"saved={result.saved}, updated={result.updated}, "
        f"skipped_no_keyword={result.skipped_no_keyword}, skipped_excluded={result.skipped_excluded}, "
        f"network_requests={result.network_requests}, cached_pages={result.cached_pages}"
    )


@main.command("summarize-paper")
def summarize_paper(
    arxiv_id: str = typer.Argument(..., help="arXiv id, for example 2605.15157v1."),
    force: bool = typer.Option(False, "--force", help="Regenerate even if a summary exists."),
    full_text: bool = typer.Option(False, "--full-text", help="Use downloaded PDF text instead of metadata/abstract only."),
) -> None:
    """Generate an intelligent summary for one paper."""
    session, settings = _session()
    try:
        runtime_settings = resolve_runtime_settings(session, settings)
        if full_text:
            summary = generate_paper_full_text_summary(session, arxiv_id, runtime_settings, force=force)
            typer.echo(
                f"{arxiv_id}: generated full-text summary id={summary.id}, "
                f"model={_display_model_name(summary.model)}"
            )
        else:
            summary = generate_paper_summary(session, arxiv_id, runtime_settings, force=force)
            typer.echo(
                f"{arxiv_id}: generated abstract summary id={summary.id}, "
                f"model={_display_model_name(summary.model)}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
