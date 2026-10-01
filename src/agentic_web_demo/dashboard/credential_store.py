"""OS credential storage only; never fall back to a file or plaintext backend."""

import hashlib
import json
import sys
from uuid import UUID


class CredentialUnavailable(Exception):
    """Safe public error; never forward backend exceptions containing secrets."""


class CredentialStore:
    def __init__(self, root):
        self.service = (
            "agentic-demo:" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]
        )
        self.backend = None
        self.label = "Unavailable; session-only storage is available"
        try:
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring

                backend = WinVaultKeyring()
                label = "Windows Credential Manager"
            elif sys.platform == "darwin":
                from keyring.backends.macOS import Keyring

                backend = Keyring()
                label = "macOS Keychain"
            elif sys.platform.startswith("linux"):
                from keyring.backends.SecretService import Keyring

                backend = Keyring()
                label = "Linux Secret Service"
            else:
                return
            if backend.priority > 0:
                self.backend, self.label = backend, label
        except Exception:
            # No auto-discovery/chainer, environment-selected or plaintext backend.
            pass

    @property
    def available(self):
        return self.backend is not None

    def _call(self, operation, user_id, *args):
        if not self.available:
            raise CredentialUnavailable("Secure storage unavailable. Use session-only storage.")
        try:
            return getattr(self.backend, operation)(self.service, str(UUID(user_id)), *args)
        except Exception:
            raise CredentialUnavailable(
                "Secure storage is unavailable or locked. Unlock the OS keyring and retry."
            ) from None

    def save(self, user_id, settings):
        self._call(
            "set_password",
            user_id,
            json.dumps({"api_key": settings.api_key, "model": settings.model}),
        )

    def load(self, user_id):
        from agentic_web_demo.agents.openai_planner import ModelSettings

        raw = self._call("get_password", user_id)
        if raw is None:
            raise CredentialUnavailable("Saved credential not found. Replace or forget it.")
        try:
            values = json.loads(raw)
            return ModelSettings(values["model"], values["api_key"], 60, 0)
        except Exception:
            raise CredentialUnavailable(
                "Saved credential could not be loaded. Replace it."
            ) from None

    def forget(self, user_id):
        if self._call("get_password", user_id) is not None:
            self._call("delete_password", user_id)
