def test_smoke() -> None:
    from app.main import app

    assert app.title == "Serviq LLM Gateway"
