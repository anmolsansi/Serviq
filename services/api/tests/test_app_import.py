from fastapi import FastAPI

from app.main import app


def test_app_imports_with_expected_title() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "Serviq API"
