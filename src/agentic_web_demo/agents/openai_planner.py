"""Explicit OpenAI adapter; no credentials or provider SDK objects enter graph state."""

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from agentic_web_demo.agents.model_contract import INSTRUCTIONS, PROMPT_VERSION, ModelDecision
from agentic_web_demo.agents.planning import PlanningError


@dataclass(frozen=True)
class ModelSettings:
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 30
    max_retries: int = 1
    max_output_tokens: int = 1200

    def __post_init__(self):
        if not self.model.strip() or len(self.model) > 200 or not self.api_key.strip():
            raise ValueError("Set AGENTIC_MODEL_NAME and OPENAI_API_KEY locally.")
        if not 1 <= self.timeout_seconds <= 60 or not 0 <= self.max_retries <= 2:
            raise ValueError("Model timeout must be 1-60 seconds and retries 0-2.")
        if not 256 <= self.max_output_tokens <= 4096:
            raise ValueError("Model output limit must be 256-4096 tokens.")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None):
        env = os.environ if env is None else env
        if env.get("AGENTIC_MODEL_PROVIDER", "openai") != "openai":
            raise ValueError("Only the openai live adapter is implemented; no fallback is used.")
        try:
            return cls(
                model=env.get("AGENTIC_MODEL_NAME", "").strip(),
                api_key=env.get("OPENAI_API_KEY", "").strip(),
                timeout_seconds=float(env.get("AGENTIC_MODEL_TIMEOUT_SECONDS", "30")),
                max_retries=int(env.get("AGENTIC_MODEL_MAX_RETRIES", "1")),
                max_output_tokens=int(env.get("AGENTIC_MODEL_MAX_OUTPUT_TOKENS", "1200")),
            )
        except (ValueError, TypeError):
            raise ValueError("Invalid model configuration. See LANGGRAPH_GUIDE.md.") from None


class OpenAIPlanner:
    mode = "live"
    provider = "openai"

    def __init__(self, settings: ModelSettings, *, client=None):
        self.settings = settings
        self.client = (
            client  # Test injection. The CLI never accepts a client or arbitrary endpoint.
        )
        self.metadata = {}

    def plan(self, request: str, today: date) -> dict:
        self._reset_metadata()
        if not request.strip() or len(request) > 2000:
            raise PlanningError("request_invalid")
        return self._plan([{"role": "user", "content": request}], today)

    def plan_messages(self, messages: list[dict], today: date) -> dict:
        """Forward bounded real CrewAI task messages through the same API contract."""
        self._reset_metadata()
        if (
            not isinstance(messages, list)
            or not messages
            or any(
                not isinstance(message, dict)
                or set(message) != {"role", "content"}
                or message["role"] not in {"system", "user", "assistant"}
                or not isinstance(message["content"], str)
                for message in messages
            )
            or len(json.dumps(messages)) > 16000
        ):
            raise PlanningError("request_invalid")
        return self._plan(messages, today)

    def _reset_metadata(self):
        self.metadata = {
            "provider": self.provider,
            "model": self.settings.model,
            "prompt_version": PROMPT_VERSION,
            "api_attempted": False,
            "response_received": False,
        }

    def _plan(self, messages: list[dict], today: date) -> dict:
        # Prevent SDK debug logging (including inherited OPENAI_LOG) from emitting payloads.
        for name in ("openai", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        client = self.client
        owned = client is None
        try:
            if owned:
                client = OpenAI(
                    api_key=self.settings.api_key,
                    base_url="https://api.openai.com/v1",
                    organization=None,
                    project=None,
                    timeout=self.settings.timeout_seconds,
                    max_retries=self.settings.max_retries,
                    http_client=httpx.Client(
                        timeout=self.settings.timeout_seconds,
                        follow_redirects=False,
                    ),
                )
            self.metadata["api_attempted"] = True
            response = client.responses.parse(
                model=self.settings.model,
                input=[
                    {
                        "role": "system",
                        "content": INSTRUCTIONS + "\nLocal reference date: " + today.isoformat(),
                    },
                    *messages,
                ],
                text_format=ModelDecision,
                store=False,
                max_output_tokens=self.settings.max_output_tokens,
            )
            self.metadata["response_received"] = True
            if response.usage:
                self.metadata["usage"] = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            if response.status != "completed":
                raise PlanningError("incomplete")
            if any(
                part.type == "refusal"
                for item in response.output
                if item.type == "message"
                for part in item.content
            ):
                raise PlanningError("refusal")
            if response.output_parsed is None:
                raise PlanningError("invalid_response")
            return ModelDecision.model_validate(response.output_parsed).model_dump()
        except (AuthenticationError, PermissionDeniedError):
            raise PlanningError("authentication") from None
        except RateLimitError:
            raise PlanningError("rate_limit") from None
        except APITimeoutError:
            raise PlanningError("timeout") from None
        except APIConnectionError:
            raise PlanningError("connection") from None
        except ValidationError:
            raise PlanningError("invalid_response") from None
        except (APIStatusError, APIError):
            raise PlanningError("provider_error") from None
        finally:
            if owned and client is not None:
                client.close()
