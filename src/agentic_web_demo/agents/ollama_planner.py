"""Local-only Ollama planning. No keys, downloads, cloud fallback or automatic retries."""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import httpx
from pydantic import ValidationError

from agentic_web_demo.agents.model_contract import INSTRUCTIONS, PROMPT_VERSION, ModelDecision
from agentic_web_demo.agents.planning import PlanningError

LOCAL_MODELS = {"qwen3:8b", "qwen3:4b"}
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


@dataclass(frozen=True)
class OllamaSettings:
    model: str = "qwen3:8b"
    timeout_seconds: float = 120

    def __post_init__(self):
        if self.model not in LOCAL_MODELS or not 1 <= self.timeout_seconds <= 300:
            raise ValueError("Choose qwen3:8b or qwen3:4b and a local timeout of 1-300 seconds.")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None):
        env = os.environ if env is None else env
        try:
            return cls(
                model=env.get("AGENTIC_MODEL_NAME", "qwen3:8b").strip(),
                timeout_seconds=float(env.get("AGENTIC_OLLAMA_TIMEOUT_SECONDS", "120")),
            )
        except (ValueError, TypeError):
            raise ValueError("Invalid Ollama settings. See OLLAMA_GUIDE.md.") from None


class OllamaPlanner:
    mode = "live"
    provider = "ollama"

    def __init__(self, settings: OllamaSettings, *, client=None):
        self.settings = settings
        self.client = client
        self.metadata = {}

    def plan(self, request: str, today: date) -> dict:
        return self._plan(request, today)

    def plan_messages(self, messages: list[dict], today: date) -> dict:
        """Bounded CrewAI conversation through the same local-only transport."""
        if (
            not messages
            or len(json.dumps(messages)) > 16000
            or any(
                item.get("role") not in {"system", "user", "assistant"}
                or not isinstance(item.get("content"), str)
                for item in messages
            )
        ):
            raise PlanningError("request_invalid")
        return self._plan("CrewAI hotel planning task", today, messages=messages)

    def _plan(self, request: str, today: date, *, messages=None) -> dict:
        self.metadata = {
            "provider": self.provider,
            "model": self.settings.model,
            "prompt_version": PROMPT_VERSION,
            "api_attempted": False,
            "response_received": False,
            "local_inference": True,
        }
        if not request.strip() or len(request) > 2000:
            raise PlanningError("request_invalid")
        schema = ModelDecision.model_json_schema()
        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": INSTRUCTIONS
                    + "\nLocal reference date: "
                    + today.isoformat()
                    + "\nReturn JSON matching this schema: "
                    + json.dumps(schema),
                },
                {"role": "user", "content": request},
            ],
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1200},
        }
        client = self.client
        if messages is not None:
            payload["messages"] = [payload["messages"][0], *messages]
            payload["options"]["num_ctx"] = 8192
        owned = client is None
        try:
            if owned:
                client = httpx.Client(
                    timeout=self.settings.timeout_seconds, trust_env=False, follow_redirects=False
                )
            self.metadata["api_attempted"] = True
            response = client.post(OLLAMA_URL, json=payload)
            if response.status_code == 404:
                raise PlanningError("local_model_missing")
            if response.status_code != 200:
                raise PlanningError("local_service_error")
            body = response.json()
            if not isinstance(body, dict):
                raise PlanningError("invalid_response")
            self.metadata["response_received"] = True
            if body.get("error"):
                raise PlanningError("local_service_error")
            if body.get("done") is not True or body.get("done_reason") != "stop":
                raise PlanningError("incomplete")
            message = body.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise PlanningError("invalid_response")
            if message.get("tool_calls") or not isinstance(message.get("content"), str):
                raise PlanningError("invalid_response")
            decision = ModelDecision.model_validate_json(message["content"])
            counts = (body.get("prompt_eval_count"), body.get("eval_count"))
            if all(type(value) is int and value >= 0 for value in counts):
                self.metadata["usage"] = {
                    "input_tokens": counts[0],
                    "output_tokens": counts[1],
                    "total_tokens": sum(counts),
                }
            return decision.model_dump()
        except httpx.TimeoutException:
            raise PlanningError("timeout") from None
        except httpx.TransportError:
            raise PlanningError("local_connection") from None
        except (ValidationError, ValueError, TypeError):
            raise PlanningError("invalid_response") from None
        finally:
            if owned and client is not None:
                client.close()
