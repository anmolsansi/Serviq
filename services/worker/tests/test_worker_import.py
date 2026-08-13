from app.main import main


def test_worker_entry_point_imports_and_exits_cleanly() -> None:
    assert main() == 0
