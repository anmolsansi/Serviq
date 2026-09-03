from __future__ import annotations

import pytest

from app.core.config import load_settings
from app.core.database import DatabaseConfigurationError, sqlalchemy_database_url
from tests.test_config import BASE_ENV


def test_plain_postgresql_url_uses_psycopg_dialect() -> None:
    settings = load_settings(BASE_ENV)

    assert sqlalchemy_database_url(settings).startswith("postgresql+psycopg://")


def test_already_adapted_database_url_is_preserved() -> None:
    settings = load_settings(
        BASE_ENV
        | {"DATABASE_URL": "postgresql+psycopg://serviq:serviq@localhost:5432/serviq"}
    )

    assert (
        sqlalchemy_database_url(settings)
        == "postgresql+psycopg://serviq:serviq@localhost:5432/serviq"
    )


def test_non_postgresql_database_url_fails_without_echoing_value() -> None:
    unsafe = "mysql://user:super-secret@localhost/database"
    settings = load_settings(BASE_ENV | {"DATABASE_URL": unsafe})

    with pytest.raises(DatabaseConfigurationError) as error:
        sqlalchemy_database_url(settings)

    assert str(error.value) == "DATABASE_URL must use the PostgreSQL scheme"
    assert unsafe not in str(error.value)
