"""Standard-library LLM client supporting multiple provider presets and env overrides."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PRESETS: Dict[str, Dict[str, Any]] = {
    "anthropic": {
        "key_env": "ANTHROPIC_API_KEY",
        "base": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-5-5",
    },
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
    },
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "key_env": "OPENROUTER_API_KEY",
        "base": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "ollama": {
        "key_env": None,
        "base": "http://localhost:11434/v1",
        "model": "llama3.1",
    },
}

RETRY_DELAYS: List[float] = [5.0, 15.0, 30.0]
USER_AGENT: str = "RootCause-QA/1.0"


def provider() -> Optional[str]:
    """Select LLM provider from LLM_PROVIDER or detect first preset whose key is set."""
    explicit = os.environ.get("LLM_PROVIDER")
    if explicit:
        return explicit.lower()

    for p in ["anthropic", "gemini", "groq", "openrouter"]:
        key_env = PRESETS[p]["key_env"]
        if key_env and os.environ.get(key_env):
            return p

    return None


def available() -> bool:
    """Return True if an LLM provider is configured and ready."""
    p = provider()
    if not p:
        return False
    if p not in PRESETS:
        return True
    key_env = PRESETS[p]["key_env"]
    return True if key_env is None else bool(os.environ.get(key_env))


def describe() -> str:
    """Return human-readable summary of the active LLM configuration."""
    p = provider()
    if not p:
        return "No LLM provider configured (baseline mode)"
    preset = PRESETS.get(p, {})
    model = os.environ.get("LLM_MODEL") or preset.get("model", "unknown")
    base = os.environ.get("LLM_BASE_URL") or preset.get("base", "")
    return f"{p} (model: {model}, base: {base})"


def missing_hint() -> str:
    """Return helpful message describing how to configure LLM keys or local providers."""
    return (
        "Set one of GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, or ANTHROPIC_API_KEY, "
        "or set LLM_PROVIDER=ollama for local inference. LLM_MODEL overrides the default model."
    )


def chat(
    system: str,
    user: str,
    max_tokens: int = 2000,
    timeout: int = 120,
) -> str:
    """Send chat request using the active provider with backoff retries on 429/503."""
    p = provider()
    if not p:
        raise RuntimeError("No LLM provider configured. Set an API key or LLM_PROVIDER.")

    preset = PRESETS.get(p, {})
    base_url = (os.environ.get("LLM_BASE_URL") or preset.get("base", "")).rstrip("/")
    # Note: Model names evolve; LLM_MODEL environment variable overrides the preset default
    model = os.environ.get("LLM_MODEL") or preset.get("model", "")
    key_env = preset.get("key_env")
    api_key = os.environ.get(key_env) if key_env else ""

    if p == "anthropic":
        url = f"{base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": USER_AGENT,
        }
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    else:
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

    raw_data = json.dumps(body).encode("utf-8")
    delays = list(RETRY_DELAYS)

    while True:
        req = urllib.request.Request(url, data=raw_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8", errors="replace"))
                if p == "anthropic":
                    return data["content"][0]["text"]
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and delays:
                wait_time = delays.pop(0)
                time.sleep(wait_time)
                continue
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code} from {p}: {err_body}") from exc


class LLMClient:
    """Wrapper class providing object-oriented interface for LLM calls."""

    def __init__(self, provider_name: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize LLMClient with optional provider or model override."""
        self.provider_name = provider_name
        self.model = model

    def chat(self, system: str, user: str, max_tokens: int = 2000, timeout: int = 120) -> str:
        """Forward chat invocation to module-level chat."""
        return chat(system, user, max_tokens, timeout)

    def ask(self, prompt: str, system: str = "") -> str:
        """Execute single-turn prompt chat."""
        return chat(system=system, user=prompt)
