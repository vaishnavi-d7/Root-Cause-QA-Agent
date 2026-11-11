"""Unit tests for server log traceback parser."""
from pathlib import Path
from rca_agent.log_parser import parse_server_log


def test_parse_real_flask_traceback(tmp_path: Path) -> None:
    """Verify parse_server_log extracts method, path, exception, and innermost app frame."""
    fake_repo = tmp_path / "my_app_repo"
    fake_repo.mkdir()
    app_file = fake_repo / "app.py"
    app_file.write_text("def search():\n    pass\n", encoding="utf-8")

    sample_log = f"""[2026-10-22 14:27:53,231] ERROR in app: Exception on /search?q=%27 [GET]
Traceback (most recent call last):
  File "C:\\Python314\\Lib\\site-packages\\flask\\app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
  File "{app_file}", line 42, in search
    cursor.execute(f"SELECT * FROM products WHERE name LIKE '%{{q}}%'")
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^
sqlite3.OperationalError: unrecognized token: "'"
127.0.0.1 - - [22/Oct/2026 14:27:53] "GET /search?q=%27 HTTP/1.1" 500 -
"""
    log_file = tmp_path / "server.log"
    log_file.write_text(sample_log, encoding="utf-8")
    content = log_file.read_text(encoding="utf-8")

    traces = parse_server_log(content)
    assert len(traces) == 1
    t = traces[0]

    assert t.method == "GET"
    assert t.path == "/search?q=%27"
    assert "sqlite3.OperationalError: unrecognized token" in t.exception

    # Verify app_frame finds innermost frame within repo and skips caret markers
    app_fr = t.app_frame(fake_repo)
    assert app_fr is not None
    assert app_fr.line == 42
    assert app_fr.func == "search"
    assert "SELECT * FROM products" in app_fr.code
    assert "^" not in app_fr.code
    assert "~" not in app_fr.code

