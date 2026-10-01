"""Local accounts, explicit admin roles and user-owned credential storage."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from agentic_web_demo.dashboard.credential_store import CredentialStore, CredentialUnavailable
from agentic_web_demo.dashboard.service import DashboardService

ITERATIONS = 600_000


@dataclass
class Session:
    user_id: str
    username: str
    expires: float
    model_settings: object = field(default=None, repr=False)
    credential_notice: str = ""


class Accounts:
    def __init__(self, root, policy_path, target, *, credential_store=None):
        self.root, self.policy_path, self.target = root, policy_path, target
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / "accounts.sqlite3"
        self.lock = threading.RLock()
        self.sessions = {}
        self.services = {}
        self.gate = threading.Semaphore(1)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS accounts (user_id TEXT PRIMARY KEY, "
                "username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, digest BLOB NOT NULL)"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
            for name, definition in {
                "role": "TEXT NOT NULL DEFAULT 'user'",
                "enabled": "INTEGER NOT NULL DEFAULT 1",
                "credential_saved": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {definition}")
            db.execute(
                "CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, "
                "at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, actor TEXT NOT NULL, "
                "action TEXT NOT NULL, target TEXT NOT NULL)"
            )
        self.dummy_salt = secrets.token_bytes(16)
        self.credentials = credential_store or CredentialStore(root)

    def register(self, username, password, *, bootstrap=False):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username) or not 12 <= len(password) <= 128:
            raise ValueError("Invalid username or password length")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
        with self.lock, closing(sqlite3.connect(self.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if (
                bootstrap
                and db.execute("SELECT count(*) FROM accounts WHERE role = 'admin'").fetchone()[0]
            ):
                raise ValueError("An administrator already exists")
            if db.execute("SELECT count(*) FROM accounts").fetchone()[0] >= 100:
                raise ValueError("Local account limit reached")
            try:
                user_id = str(uuid4())
                db.execute(
                    "INSERT INTO accounts (user_id, username, salt, digest, role) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, username.casefold(), salt, digest, "admin" if bootstrap else "user"),
                )
                self._audit(db, user_id, "bootstrap_admin" if bootstrap else "register", user_id)
            except sqlite3.IntegrityError:
                raise ValueError("Account cannot be created") from None
        return user_id

    def authenticate(self, username, password):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute(
                "SELECT user_id, salt, digest, enabled FROM accounts WHERE username = ?",
                (username.casefold(),),
            ).fetchone()
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), row[1] if row else self.dummy_salt, ITERATIONS
        )
        if not row or not hmac.compare_digest(actual, row[2]) or not row[3]:
            return None
        return row[0]

    def prune(self):
        with self.lock:
            for sid, session in list(self.sessions.items()):
                if session.expires <= time.monotonic():
                    self.sessions.pop(sid)

    def get(self, sid):
        with self.lock:
            self.prune()
            session = self.sessions.get(sid)
            if session and not self.profile(session.user_id)["enabled"]:
                self.sessions.pop(sid, None)
                return None
            return session

    def sign_in(self, user_id, username):
        with self.lock:
            self.prune()
            profile = self.profile(user_id)
            if not profile["enabled"]:
                raise ValueError("Account disabled")
            if len(self.sessions) >= 100:
                raise ValueError("Session limit reached")
            sid = secrets.token_urlsafe(32)
            self.sessions[sid] = Session(user_id, username.casefold(), time.monotonic() + 3600)
            if profile["credential_saved"]:
                try:
                    self.sessions[sid].model_settings = self.credentials.load(user_id)
                except CredentialUnavailable as exc:
                    self.sessions[sid].credential_notice = str(exc)
            return sid

    @staticmethod
    def _audit(db, actor, action, target):
        db.execute(
            "INSERT INTO audit(actor, action, target) VALUES (?, ?, ?)", (actor, action, target)
        )

    def profile(self, user_id):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT user_id, username, role, enabled, credential_saved "
                "FROM accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Account unavailable")
            return dict(row)

    def list_users(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in db.execute(
                    "SELECT user_id, username, role, enabled FROM accounts ORDER BY username"
                )
            ]

    def audit_history(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row) for row in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")
            ]

    def manage(self, actor, target, action):
        target = str(UUID(target))
        if action not in {"enable", "disable", "promote", "demote", "revoke_sessions"}:
            raise ValueError("Unsupported action")
        with self.lock, closing(sqlite3.connect(self.database)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            admin = db.execute(
                "SELECT role, enabled FROM accounts WHERE user_id = ?", (actor,)
            ).fetchone()
            if admin != ("admin", 1):
                raise PermissionError("Administrator access required")
            row = db.execute(
                "SELECT role, enabled FROM accounts WHERE user_id = ?", (target,)
            ).fetchone()
            if row is None:
                raise ValueError("Account unavailable")
            if actor == target and action in {"disable", "demote"}:
                raise ValueError("Ask another administrator to change your access")
            if row == ("admin", 1) and action in {"disable", "demote"}:
                count = db.execute(
                    "SELECT count(*) FROM accounts WHERE role = 'admin' AND enabled = 1"
                ).fetchone()[0]
                if count <= 1:
                    raise ValueError("Cannot remove the last active administrator")
            if action in {"enable", "disable"}:
                db.execute(
                    "UPDATE accounts SET enabled = ? WHERE user_id = ?",
                    (int(action == "enable"), target),
                )
            if action in {"promote", "demote"}:
                db.execute(
                    "UPDATE accounts SET role = ? WHERE user_id = ?",
                    ("admin" if action == "promote" else "user", target),
                )
            self._audit(db, actor, action, target)
            for sid, session in list(self.sessions.items()):
                if session.user_id == target:
                    self.sessions.pop(sid)

    def save_credential(self, sid, settings, remember):
        with self.lock:
            session = self.get(sid)
            if session is None:
                raise ValueError("Session expired")
            if remember:
                self.credentials.save(session.user_id, settings)
                with closing(sqlite3.connect(self.database)) as db, db:
                    db.execute(
                        "UPDATE accounts SET credential_saved = 1 WHERE user_id = ?",
                        (session.user_id,),
                    )
                    self._audit(db, session.user_id, "credential_saved", session.user_id)
                # Replace older in-memory keys in this user's other sessions only.
                for other in self.sessions.values():
                    if other.user_id == session.user_id:
                        other.model_settings = None
            session.model_settings = settings
            session.credential_notice = ""

    def forget_credential(self, sid):
        with self.lock:
            session = self.get(sid)
            if session is None:
                raise ValueError("Session expired")
            if self.profile(session.user_id)["credential_saved"]:
                self.credentials.forget(session.user_id)
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute(
                    "UPDATE accounts SET credential_saved = 0 WHERE user_id = ?", (session.user_id,)
                )
                self._audit(db, session.user_id, "credential_forgotten", session.user_id)
            for other in self.sessions.values():
                if other.user_id == session.user_id:
                    other.model_settings = None
                    other.credential_notice = ""

    def sign_out(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def configure(self, sid, settings):
        with self.lock:
            session = self.get(sid)
            if session is None:
                raise ValueError("Session expired")
            session.model_settings = settings

    def service_for(self, user_id):
        user_id = str(UUID(user_id))
        with self.lock:
            if user_id not in self.services:
                self.services[user_id] = DashboardService(
                    self.root / "users" / user_id,
                    self.policy_path,
                    self.target,
                    gate=self.gate,
                    broker_stream="USER_" + UUID(user_id).hex.upper(),
                )
            return self.services[user_id]

    def close(self):
        with self.lock:
            self.sessions.clear()
        for service in self.services.values():
            service.close()
