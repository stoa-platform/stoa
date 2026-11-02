"""Migration URLs must select the installed sync driver across SQLAlchemy versions."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


@pytest.mark.parametrize("driver", ["postgresql+asyncpg", "postgresql", "postgresql+psycopg2"])
@pytest.mark.parametrize("from_environment", [True, False])
def test_regression_pr2971_alembic_selects_psycopg2(
    monkeypatch: pytest.MonkeyPatch, driver: str, from_environment: bool
) -> None:
    database_url = f"{driver}://localhost/stoa?ssl=require"
    if from_environment:
        monkeypatch.setenv("DATABASE_URL", database_url)
    else:
        from src.config import settings

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    api_root = Path(__file__).resolve().parents[1]
    # This test supplies every migration setting; loading alembic.ini would
    # reconfigure global logging and disable loggers used by later tests.
    config = Config()
    config.set_main_option("script_location", str(api_root / "alembic"))
    script = ScriptDirectory.from_config(config)

    # Execute the real migration environment offline, without contacting a DB.
    with EnvironmentContext(config, script, as_sql=True, fn=lambda _revision, _context: []):
        script.run_env()

    url = make_url(config.get_main_option("sqlalchemy.url"))
    assert url.drivername == "postgresql+psycopg2"
    assert url.query == {"sslmode": "require"}
    engine = create_engine(url)
    assert engine.dialect.driver == "psycopg2"
    engine.dispose()
