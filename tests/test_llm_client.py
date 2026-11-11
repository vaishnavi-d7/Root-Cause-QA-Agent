"""Unit tests for llm_client provider resolution, API formats, retries, and errors."""
import json
import os
import socket
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Generator
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llm_client


def test_provider_selection_order_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify provider precedence order, key detection, and model/base env overrides."""
    # 1. Clean environment: no provider configured
    for p_info in llm_client.PRESETS.values():
        if p_info["key_env"]:
            monkeypatch.delenv(p_info["key_env"], raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    assert llm_client.provider() is None
    assert llm_client.available() is False
    assert "No LLM provider configured" in llm_client.describe()

    # 2. Set Gemini key -> provider becomes gemini
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    assert llm_client.provider() == "gemini"
    assert llm_client.available() is True
    assert "gemini" in llm_client.describe()

    # 3. Set Anthropic key -> takes precedence over Gemini per PRESETS search order
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    assert llm_client.provider() == "anthropic"

    # 4. Explicit LLM_PROVIDER overrides any detected API key
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    assert llm_client.provider() == "groq"

    # 5. Model and base URL overrides
    monkeypatch.setenv("LLM_MODEL", "custom-model-v1")
    monkeypatch.setenv("LLM_BASE_URL", "http://custom-host:8080/v1")
    desc = llm_client.describe()
    assert "custom-model-v1" in desc
    assert "http://custom-host:8080/v1" in desc


class MockOpenAIHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler returning standard OpenAI chat completion JSON."""

    requests: list = []

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len).decode("utf-8"))
        MockOpenAIHandler.requests.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "body": body,
            }
        )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "choices": [
                {
                    "message": {
                        "content": "Simulated OpenAI response content",
                    }
                }
            ]
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


class MockAnthropicHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler returning Anthropic messages JSON."""

    requests: list = []

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len).decode("utf-8"))
        MockAnthropicHandler.requests.append(
            {
                "path": self.path,
                "api_key": self.headers.get("x-api-key"),
                "anthropic_version": self.headers.get("anthropic-version"),
                "body": body,
            }
        )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "content": [
                {
                    "type": "text",
                    "text": "Simulated Anthropic response text",
                }
            ]
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


def test_chat_openai_format_against_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify chat() sends correct schema and parses OpenAI-style response format."""
    MockOpenAIHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
    port = server.server_port
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    try:
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-openai-key")
        monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}")

        result = llm_client.chat(system="You are an analyst.", user="Hello RCA")
        assert result == "Simulated OpenAI response content"
        assert len(MockOpenAIHandler.requests) == 1

        req = MockOpenAIHandler.requests[0]
        assert req["path"] == "/chat/completions"
        assert req["auth"] == "Bearer test-openai-key"
        assert req["body"]["messages"][0]["content"] == "You are an analyst."
        assert req["body"]["messages"][1]["content"] == "Hello RCA"
    finally:
        server.shutdown()
        server.server_close()


def test_chat_anthropic_format_against_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify chat() sends correct schema and parses Anthropic-style response format."""
    MockAnthropicHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), MockAnthropicHandler)
    port = server.server_port
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    try:
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}")

        result = llm_client.chat(system="You are Claude.", user="Explain bug")
        assert result == "Simulated Anthropic response text"
        assert len(MockAnthropicHandler.requests) == 1

        req = MockAnthropicHandler.requests[0]
        assert req["path"] == "/messages"
        assert req["api_key"] == "test-anthropic-key"
        assert req["anthropic_version"] == "2023-06-01"
        assert req["body"]["system"] == "You are Claude."
        assert req["body"]["messages"][0]["content"] == "Explain bug"
    finally:
        server.shutdown()
        server.server_close()


class MockRetryHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler returning 429 on first call and 200 on second call."""

    call_count = 0

    def do_POST(self) -> None:
        MockRetryHandler.call_count += 1
        if MockRetryHandler.call_count == 1:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "rate limit exceeded"}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"choices": [{"message": {"content": "Recovered after retry"}}]}
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        pass


def test_chat_429_then_200_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify chat() retries on 429 HTTP error using configured backoff delays."""
    MockRetryHandler.call_count = 0
    server = HTTPServer(("127.0.0.1", 0), MockRetryHandler)
    port = server.server_port
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    try:
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(llm_client, "RETRY_DELAYS", [0.01, 0.02])

        result = llm_client.chat(system="sys", user="query")
        assert result == "Recovered after retry"
        assert MockRetryHandler.call_count == 2
    finally:
        server.shutdown()
        server.server_close()


def test_chat_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify chat() raises RuntimeError or URLError when connecting to an unreachable port."""
    # Find an unused closed port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setattr(llm_client, "RETRY_DELAYS", [0.01])

    with pytest.raises((RuntimeError, urllib.error.URLError)):
        llm_client.chat(system="sys", user="user", timeout=1)
