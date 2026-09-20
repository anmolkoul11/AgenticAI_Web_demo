import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--model-framework",
        choices=["langgraph", "crewai"],
        default="langgraph",
        help="Framework used for opt-in live semantic evaluations",
    )
    parser.addoption(
        "--run-model",
        action="store_true",
        default=False,
        help="Live model evaluations: explicitly approved paid OpenAI",
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
    if provider != "openai":
        pytest.fail("Unsupported model provider; no fallback is used")
    if os.environ.get("AGENTIC_ALLOW_MODEL_API") != "1":
        pytest.fail("Set AGENTIC_ALLOW_MODEL_API=1 only after approval for paid synthetic tests")
    from agentic_web_demo.agents.openai_planner import ModelSettings, OpenAIPlanner

    try:
        settings = ModelSettings.from_env()
    except ValueError:
        pytest.fail("Configure approved model access locally; never paste a key into test output")
    planner = OpenAIPlanner(settings)
    if request.config.getoption("--model-framework") == "crewai":
        from agentic_web_demo.agents.crewai_planner import CrewAIPlanner

        return CrewAIPlanner(planner)
    return planner


@pytest.fixture
def model_workflow(request):
    from agentic_web_demo.agents.runners import get_runner

    return get_runner(request.config.getoption("--model-framework"))
