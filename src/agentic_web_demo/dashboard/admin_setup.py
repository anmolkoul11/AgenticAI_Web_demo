"""Offline first-admin setup. Run with the dashboard stopped; no default credentials."""

import getpass
import sys
from pathlib import Path

from agentic_web_demo.config import Settings
from agentic_web_demo.dashboard.accounts import Accounts


def main():
    if not sys.stdin.isatty():
        print("Run interactively in your terminal. Do not pass passwords as arguments.")
        return 2
    print("First administrator setup. Stop the dashboard before continuing.")
    username = input("New administrator username: ").strip()
    password = getpass.getpass("New administrator password (12–128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords did not match. No account created.")
        return 2
    accounts = Accounts(
        Settings.from_env().data_dir, Path("config/rules.yaml"), "http://127.0.0.1:8110"
    )
    try:
        accounts.register(username, password, bootstrap=True)
        print("Administrator created. Start the dashboard and sign in. No API key was stored.")
        return 0
    except ValueError:
        print(
            "Setup rejected. Use a new valid username/password; setup only works before "
            "an administrator exists. Existing users are never silently promoted."
        )
        return 2
    finally:
        accounts.close()


if __name__ == "__main__":
    raise SystemExit(main())
