"""
LLM client — wraps LM Studio's OpenAI-compatible endpoint.
Drop-in replacement: swap base_url/model for Ollama, OpenAI, Anthropic, etc.
"""

import json
import urllib.request
import urllib.error
from typing import Generator

# ── Default config (override via env or config.py) ─────────────────────────
BASE_URL  = "http://localhost:1234/v1"
MODEL     = "local-model"   # LM Studio shows the loaded model name in its UI
TIMEOUT   = 60


def _headers():
    return {"Content-Type": "application/json"}


def chat(messages: list[dict],
         system: str = None,
         temperature: float = 0.7,
         max_tokens: int = 512,
         stream: bool = False) -> str:
    """
    Send a chat completion request. Returns the assistant reply as a string.
    messages: list of {"role": "user"|"assistant", "content": "..."}
    """
    if system:
        full_messages = [{"role": "system", "content": system}] + messages
    else:
        full_messages = messages

    payload = json.dumps({
        "model":       MODEL,
        "messages":    full_messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "stream":      False,
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers=_headers(),
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"\n[LLM] Cannot reach LM Studio at {BASE_URL}\n"
            f"  → Make sure LM Studio is running and a model is loaded.\n"
            f"  → Error: {e}"
        )


def ping() -> bool:
    """Returns True if LM Studio is reachable."""
    try:
        req = urllib.request.Request(f"{BASE_URL}/models", headers=_headers())
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def configure(base_url: str = None, model: str = None, timeout: int = None):
    """Runtime config override."""
    global BASE_URL, MODEL, TIMEOUT
    if base_url:  BASE_URL = base_url.rstrip("/")
    if model:     MODEL    = model
    if timeout:   TIMEOUT  = timeout
