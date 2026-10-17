from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect
import claimbreaker.db as database


def test_initial_migration_creates_and_reverses_empty_schema(monkeypatch):
    isolated = create_engine("sqlite://")
    monkeypatch.setattr(database, "engine", isolated)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    assert {"cases", "artifacts", "jobs", "events", "executions"}.issubset(
        inspect(isolated).get_table_names()
    )
    command.downgrade(config, "base")
    assert "cases" not in inspect(isolated).get_table_names()
