def pytest_addoption(parser):
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
