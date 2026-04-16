"""Ollama HTTP client for local LLM inference."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"
DEFAULT_BASE_URL = "http://ollama:11434"


class OllamaClient:
    """Synchronous HTTP client for the Ollama /api/generate endpoint."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.1) -> str:
        """Send a generate request to Ollama. Returns generated text."""
        return self._call_api(prompt, system=system, temperature=temperature, images=None)

    def generate_with_images(
        self,
        prompt: str,
        images: list[str],
        system: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        """Send a multimodal generate request with base64-encoded images."""
        return self._call_api(prompt, system=system, temperature=temperature, images=images)

    def _call_api(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        images: list[str] | None,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                body = json.loads(resp.read().decode())
                return body.get("response", "")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return f"[Error] Model '{self.model}' not found. Run: ollama pull {self.model}"
            return f"[Error] Ollama HTTP {e.code}: {e.reason}"
        except (OSError, ConnectionRefusedError) as e:
            return f"[Error] Ollama unreachable at {self.base_url}: {e}"

    def health_check(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5):
                return True
        except Exception:
            return False
