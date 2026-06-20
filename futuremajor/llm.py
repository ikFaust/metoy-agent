from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def load_env(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_config_value(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is not None:
        return value
    try:
        import streamlit as st

        secret = st.secrets.get(key)
        if secret is not None:
            return str(secret)
    except Exception:
        pass
    return default


class GLMClient:
    def __init__(self) -> None:
        load_env()
        self.api_key = get_config_value("ZHIPU_API_KEY")
        self.base_url = get_config_value("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        self.model = get_config_value("ZHIPU_MODEL", "glm-4-plus")
        self.thinking = get_config_value("ZHIPU_THINKING", "").strip()
        self.max_tokens = int(get_config_value("ZHIPU_MAX_TOKENS", "4096"))
        self.temperature = float(get_config_value("ZHIPU_TEMPERATURE", "0.35"))
        self.timeout = float(get_config_value("ZHIPU_TIMEOUT", "18"))

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.api_key != "your_zhipu_api_key_here")

    def complete(self, system: str, user: str) -> str:
        if not self.available:
            raise RuntimeError("ZHIPU_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Package 'openai' is not installed. Run pip install -r requirements.txt.") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        extra_body = {}
        if self.thinking:
            extra_body["thinking"] = {"type": self.thinking}
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body=extra_body or None,
        )
        return response.choices[0].message.content or ""

    def complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        text = self.complete(system, user)
        try:
            import json

            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass
        return fallback
