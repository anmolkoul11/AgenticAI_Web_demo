"""Frozen desktop entry point; normal browser tabs remain the dashboard surface."""

from multiprocessing import freeze_support

from agentic_web_demo.desktop import main


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
