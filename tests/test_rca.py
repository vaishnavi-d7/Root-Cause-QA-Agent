"""Unit tests for RCA agent components and llm_client."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Generator
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llm_client
from qa_agent.models import Finding
from rca_agent.analyzer import Evidence, llm_rca
from rca_agent.git_tools import patch_applies, resolve_commit
from rca_agent.log_parser import Frame, ServerTrace, parse_server_log


def test_log_parser_sample_traceback() -> None:
    """Verify parse_server_log extracts path, method, exception, and frames skipping markers."""
    sample_log = """
[2026-10-22 14:27:53,231] ERROR in app: Exception on /discount?code=NOPE [GET]
Traceback (most recent call last):
  File "C:\\Python314\\Lib\\site-packages\\flask\\app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
  File "C:\\repo\\testapp\\repo\\app.py", line 111, in discount
    rate = DISCOUNTS[code.upper()]
           ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
KeyError: 'NOPE'
127.0.0.1 - - [22/Oct/2026 14:27:53] "GET /discount?code=NOPE HTTP/1.1" 500 -
"""
    traces = parse_server_log(sample_log)
    assert len(traces) == 1
    t = traces[0]
    assert t.path == "/discount?code=NOPE"
    assert t.method == "GET"
    assert t.exception == "KeyError: 'NOPE'"
    assert len(t.frames) == 2

    app_fr = t.frames[1]
    assert app_fr.line == 111
    assert app_fr.func == "discount"
    assert app_fr.code == "rate = DISCOUNTS[code.upper()]"


def test_patch_applies() -> None:
    """Verify patch_applies handles valid, wrong, and empty patches correctly."""
    repo_dir = ROOT_DIR / "testapp" / "repo"
    assert repo_dir.exists(), "testapp/repo must exist for patch test"

    # 1. Empty patch must return False
    assert patch_applies(repo_dir, "") is False
    assert patch_applies(repo_dir, "   \n") is False

    # 2. Valid patch
    valid_patch = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 # Mini Shop
 
 A lightweight shopping web application.
+# Test comment line
"""
    assert patch_applies(repo_dir, valid_patch) is True

    # 3. Invalid/wrong patch
    wrong_patch = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -100,3 +100,4 @@
 Nonexistent text in file
+Invalid added line
"""
    assert patch_applies(repo_dir, wrong_patch) is False


class MockLLMHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler simulating OpenAI chat completion endpoint."""

    request_count = 0

    def do_POST(self) -> None:
        MockLLMHandler.request_count += 1
        content_len = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(content_len)

        # First request in retry test returns 429
        if getattr(self.server, "simulate_429", False) and MockLLMHandler.request_count == 1:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "Rate limit reached"}}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "choices": [
                {
                    "message": {
                        "content": '{"suspected_commit": "abc1234", "root_cause": "Test cause"}'
                    }
                }
            ]
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


def test_llm_client_chat_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify llm_client.chat succeeds with OpenAI response and retries on 429."""
    server = HTTPServer(("127.0.0.1", 0), MockLLMHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "dummy-key")
        monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(llm_client, "RETRY_DELAYS", [0.05, 0.1])

        # Test A: standard successful chat
        MockLLMHandler.request_count = 0
        server.simulate_429 = False
        res = llm_client.chat("system prompt", "user query")
        assert "abc1234" in res
        assert MockLLMHandler.request_count == 1

        # Test B: 429 retry logic
        MockLLMHandler.request_count = 0
        server.simulate_429 = True
        res_retry = llm_client.chat("system prompt", "user query")
        assert "abc1234" in res_retry
        assert MockLLMHandler.request_count == 2
    finally:
        server.shutdown()
        server.server_close()


def test_llm_rca_resolves_short_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify llm_rca resolves a short SHA to the full SHA via resolve_commit."""
    repo_dir = ROOT_DIR / "testapp" / "repo"
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"
    assert gt_file.exists(), "ground_truth.json must exist"

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    b4_info = next(item for item in gt if item["bug_id"] == "B4")
    full_sha = b4_info["culprit_commit"]
    short_sha = full_sha[:7]

    finding = Finding(
        id="F03",
        kind="http_500",
        method="GET",
        url="http://127.0.0.1:5055/search?q=%27",
        route="/search",
        status=500,
        summary="HTTP 500 on /search",
        steps=[],
        console=[],
    )

    mock_evidence = Evidence(
        finding=finding,
        trace=ServerTrace(
            method="GET",
            path="/search",
            exception="sqlite3.OperationalError: unrecognized token",
            frames=[Frame(file=str(repo_dir / "app.py"), line=102, func="search", code="rows = conn.execute(...)")],
            raw="Traceback...",
        ),
        file="app.py",
        line=102,
        code_context="> 102: rows = conn.execute(...)",
        blame={"sha": b4_info["masked_by_commit"], "author": "Meena S", "date": "2026-10-06", "summary": "style: wrap long SQL line"},
        line_history="commit ...",
        blamed_commit="diff ...",
        file_log="commit ...",
    )

    mock_llm_response = json.dumps(
        {
            "suspected_commit": short_sha,
            "root_cause": "Search query parameter unescaped into SQL string.",
            "reasoning": [f"Commit {short_sha} introduced string interpolation."],
            "confidence": 0.95,
            "fix_patch": "",
        }
    )

    monkeypatch.setattr(llm_client, "chat", lambda system, user, **kwargs: mock_llm_response)

    result = llm_rca(finding, repo_dir, mock_evidence)
    assert result.suspected_commit == full_sha
    assert result.mode == "llm"
    assert result.confidence == 0.95
    assert len(result.reasoning) >= 1
