"""Session (record) and Sessions (persistent collection). Table: sessions.

A session is active while last_active_at is within 30 minutes; each successful
getAccountId() call refreshes last_active_at. endSession() deletes the row.
"""
import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.common import clock
from app.entity.database import DatabaseConnection

SESSION_TIMEOUT = timedelta(minutes=30)


@dataclass
class Session:
    sessionId: str
    accountId: int
    createdAt: str
    lastActiveAt: str


class Sessions:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # Starts a login session with a random ID and returns the ID.
    def createSession(self, accountId):
        session_id = secrets.token_urlsafe(32)
        stamp = clock.now_text()
        self.db.execute("INSERT INTO sessions (session_id, account_id, created_at, last_active_at) VALUES (?, ?, ?, ?)",
                        (session_id, accountId, stamp, stamp))
        return session_id

    # Returns the stored session for an ID, or None.
    def _find(self, sessionId):
        if not sessionId:
            return None
        row = self.db.query_one("SELECT * FROM sessions WHERE session_id = ?", (sessionId,))
        return Session(row["session_id"], row["account_id"], row["created_at"], row["last_active_at"]) if row else None

    # True when the session was used within the last 30 minutes.
    def isActive(self, sessionId):
        session = self._find(sessionId)
        return session is not None and clock.now() - clock.parse(session.lastActiveAt) <= SESSION_TIMEOUT

    # Returns the account for a live session and refreshes its 30-minute timer, or None.
    def getAccountId(self, sessionId):
        """Return the account id for an active session (and refresh it), or None if expired/unknown."""
        if not self.isActive(sessionId):
            return None
        self.db.execute("UPDATE sessions SET last_active_at = ? WHERE session_id = ?", (clock.now_text(), sessionId))
        return self._find(sessionId).accountId

    # Deletes the session (log out).
    def endSession(self, sessionId):
        return self.db.execute("DELETE FROM sessions WHERE session_id = ?", (sessionId,)) > 0
