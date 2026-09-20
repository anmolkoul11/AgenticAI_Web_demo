"""Explicit framework selection; no fallback between implementations."""


def get_runner(framework):
    if framework == "langgraph":
        from agentic_web_demo.agents.langgraph_workflow import run_workflow
    elif framework == "crewai":
        from agentic_web_demo.agents.crewai_workflow import run_workflow
    else:
        raise ValueError("Unsupported framework")
    return run_workflow
