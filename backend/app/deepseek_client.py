from __future__ import annotations

import time
from typing import Any

import httpx


class DeepseekClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.model = (model or "deepseek-chat").strip()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str | None:
        if not self.is_enabled():
            return None

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(2):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code >= 500 or resp.status_code == 429:
                        if attempt == 0:
                            time.sleep(0.8)
                            continue
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        return None
                    msg = choices[0].get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    return None
            except Exception:
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                return None
        return None
