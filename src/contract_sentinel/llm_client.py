from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any


class LlmClient:
    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model

    def _build_body(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> dict[str, Any]:
        msgs = messages.copy()
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        return {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.1,
            "stream": False,
        }

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        body = self._build_body(messages, system=system)
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {error_body[:500]}") from exc

        return result["choices"][0]["message"]["content"]
