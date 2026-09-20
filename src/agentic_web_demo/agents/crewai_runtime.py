"""Initialize the local demo's CrewAI runtime without external telemetry."""

import os


def configure():
    # Set before importing CrewAI; do not inherit a user's tracing opt-in here.
    os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
    os.environ["CREWAI_DISABLE_TRACKING"] = "true"
    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"


configure()
