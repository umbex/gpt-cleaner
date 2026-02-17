from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .config import Settings


class LLMGatewayError(Exception):
    def __init__(self, message: str, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.upstream_status = upstream_status


class LLMGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        if settings.openai_api_key:
            try:
                from openai import OpenAI  # type: ignore

                kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
                if settings.openai_base_url:
                    kwargs["base_url"] = settings.openai_base_url
                self._client = OpenAI(**kwargs)
            except Exception:
                self._client = None

    @property
    def is_mock_mode(self) -> bool:
        return self._client is None

    def chat(self, messages: List[Dict[str, str]], model: str) -> Tuple[str, Dict[str, Any]]:
        if self._client is None:
            last_user = ""
            for item in reversed(messages):
                if item.get("role") == "user":
                    last_user = item.get("content", "")
                    break
            text = (
                "[MOCK MODE] Simulated response. "
                "No OPENAI_API_KEY configured. "
                f"Last received prompt: {last_user[:400]}"
            )
            return text, {"provider": "mock", "completion_tokens": 0, "prompt_tokens": 0}

        try:
            response = self._client.chat.completions.create(model=model, messages=messages)
        except Exception as exc:
            upstream_status = getattr(exc, "status_code", None)
            if upstream_status is None:
                response = getattr(exc, "response", None)
                upstream_status = getattr(response, "status_code", None)
            message = str(exc) or "Unknown provider error"
            raise LLMGatewayError(message=message, upstream_status=upstream_status) from exc

        content = response.choices[0].message.content or ""

        usage: Dict[str, Any] = {"provider": "openai"}
        if response.usage is not None:
            usage.update(
                {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            )
        return content, usage
