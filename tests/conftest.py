import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-model",
        action="store_true",
        default=False,
        help="Live model evaluations: local Ollama or explicitly approved paid OpenAI",
    )
    parser.addoption(
        "--run-nats",
        action="store_true",
        default=False,
        help="Run integration tests against local NATS JetStream",
    )
    parser.addoption(
        "--run-browser",
        action="store_true",
        default=False,
        help="Run real Chromium tests; requires playwright install chromium",
    )


@pytest.fixture
def live_planner(request):
    if not request.config.getoption("--run-model"):
        pytest.skip("Use --run-model after configuring the chosen model provider")
    provider = os.environ.get("AGENTIC_MODEL_PROVIDER", "openai")
    if provider == "ollama":
        from agentic_web_demo.agents.ollama_planner import OllamaPlanner, OllamaSettings

        try:
            return OllamaPlanner(OllamaSettings.from_env())
        except ValueError:
            pytest.fail("Configure local Ollama settings as documented in OLLAMA_GUIDE.md")
    if provider != "openai":
        pytest.fail("Unsupported model provider; no fallback is used")
    if os.environ.get("AGENTIC_ALLOW_MODEL_API") != "1":
        pytest.fail("Set AGENTIC_ALLOW_MODEL_API=1 only after approval for paid synthetic tests")
    from agentic_web_demo.agents.openai_planner import ModelSettings, OpenAIPlanner

    try:
        settings = ModelSettings.from_env()
    except ValueError:
        pytest.fail("Configure approved model access locally; never paste a key into test output")
    return OpenAIPlanner(settings)
