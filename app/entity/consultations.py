"""Persistent project consultations and participant-scoped message history."""
from app.common import clock
from app.common.result import Result
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER, DatabaseConnection
from app.entity.interior_design_projects import PUBLIC_WHERE


MEMBER_COLUMN = {CUSTOMER: "customer_id", INTERIOR_DESIGNER: "designer_id"}
# 9 November: the newest message each participant has opened, so unread messages can be counted.
LAST_READ_COLUMN = {CUSTOMER: "customer_last_read_id", INTERIOR_DESIGNER: "designer_last_read_id"}
THREAD_COLUMNS = (
    "t.*, c.name AS customer_name, d.name AS designer_name, "
    "(p.idp_id IS NOT NULL AND p.removed_at IS NULL AND p.designer_id = t.designer_id AND c.status = 'ACTIVE' "
    "AND cp.status = 'ACTIVE' AND d.status = 'ACTIVE' AND dp.status = 'ACTIVE') AS available "
)
THREAD_FROM = (
    "FROM consultations t JOIN user_accounts c ON c.account_id = t.customer_id "
    "JOIN user_profiles cp ON cp.profile_id = c.profile_id "
    "JOIN user_accounts d ON d.account_id = t.designer_id "
    "JOIN user_profiles dp ON dp.profile_id = d.profile_id "
    "LEFT JOIN interior_design_projects p ON p.idp_id = t.project_id "
)
THREAD_SELECT = "SELECT " + THREAD_COLUMNS + THREAD_FROM


# Builds the SQL that counts messages from the other participant that this role has not opened yet.
def unread_sql(role):
    return (f"(SELECT COUNT(*) FROM consultation_messages m WHERE m.consultation_id = t.consultation_id "
            f"AND m.sender_id <> t.{MEMBER_COLUMN[role]} AND m.message_id > t.{LAST_READ_COLUMN[role]})")


class Consultations:
    # Connects the collection to SQLite.
    def __init__(self):
        self.db = DatabaseConnection()

    # Returns only the caller's conversations, with the most recent activity first.
    def listFor(self, accountId, role):
        column = MEMBER_COLUMN[role]
        rows = self.db.query("SELECT " + THREAD_COLUMNS + f", {unread_sql(role)} AS unread " + THREAD_FROM
                             + f"WHERE t.{column} = ? ORDER BY t.updated_at DESC, t.consultation_id DESC",
                             (accountId,))
        return Result.succeed("INBOX", data={"threads": rows})

    # 9 November: counts the caller's conversations that have at least one message they have not opened.
    def countUnread(self, accountId, role):
        count = self.db.scalar(f"SELECT COUNT(*) FROM consultations t WHERE t.{MEMBER_COLUMN[role]} = ? "
                               f"AND {unread_sql(role)} > 0", (accountId,))
        return Result.succeed("UNREAD", data={"count": count or 0})

    # Finds the customer's existing thread for a project, including a closed thread.
    def findForProject(self, customerId, projectId):
        return self.db.scalar("SELECT consultation_id FROM consultations WHERE customer_id = ? AND project_id = ?",
                              (customerId, projectId))

    # Reads the selected thread and its messages after checking membership.
    def viewThread(self, threadId, accountId, role):
        query = THREAD_SELECT + f"WHERE t.consultation_id = ? AND t.{MEMBER_COLUMN[role]} = ?"
        with self.db.transaction() as conn:
            conn.execute("BEGIN")
            thread = conn.execute(query, (threadId, accountId)).fetchone()
            if thread is None:
                return self.unavailableResult()
            messages = conn.execute(
                "SELECT m.*, a.name AS sender_name FROM consultation_messages m "
                "JOIN user_accounts a ON a.account_id = m.sender_id WHERE m.consultation_id = ? ORDER BY m.message_id",
                (threadId,),
            ).fetchall()
            # 9 November: opening a conversation marks every message in it as read for this participant.
            if messages:
                conn.execute(f"UPDATE consultations SET {LAST_READ_COLUMN[role]} = ? WHERE consultation_id = ?",
                             (messages[-1]["message_id"], threadId))
        return Result.succeed("THREAD", data={"thread": dict(thread), "messages": [dict(row) for row in messages]})

    # Creates the thread and its first message together, with one thread per customer and project.
    # 9 November: if the customer already has a thread for the project (an old form or a second tab),
    # the message is added to it instead of being dropped; an identical retry is saved only once.
    def start(self, customerId, projectId, message):
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(THREAD_SELECT + "WHERE t.customer_id = ? AND t.project_id = ?",
                                    (customerId, projectId)).fetchone()
            if existing:
                if self._isRepeat(conn, existing["consultation_id"], customerId, message):
                    return Result.succeed("SENT", "Message sent.", {"threadId": existing["consultation_id"]})
                return self._continue(conn, existing, customerId, CUSTOMER, message)
            project = conn.execute(
                "SELECT p.title, p.designer_id FROM interior_design_projects p "
                "JOIN user_accounts a ON a.account_id = p.designer_id" + PUBLIC_WHERE
                + " AND p.idp_id = ? AND EXISTS (SELECT 1 FROM user_accounts c "
                "JOIN user_profiles cp ON cp.profile_id = c.profile_id "
                "WHERE c.account_id = ? AND c.status = 'ACTIVE' AND cp.status = 'ACTIVE')",
                (projectId, customerId),
            ).fetchone()
            if project is None:
                return Result.fail("PROJECT_UNAVAILABLE", "This project is no longer available.")
            stamp = clock.now_text()
            thread_id = conn.execute(
                "INSERT INTO consultations (project_id, project_title, customer_id, designer_id, status, updated_at) "
                "VALUES (?, ?, ?, ?, 'NEW', ?)",
                (projectId, project["title"], customerId, project["designer_id"], stamp),
            ).lastrowid
            self._addMessage(conn, thread_id, customerId, message, stamp)
        return Result.succeed("SENT", "Message sent.", {"threadId": thread_id})

    # Appends a reply and updates the state in one transaction.
    def reply(self, threadId, accountId, role, message):
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            query = THREAD_SELECT + f"WHERE t.consultation_id = ? AND t.{MEMBER_COLUMN[role]} = ?"
            thread = conn.execute(query, (threadId, accountId)).fetchone()
            if thread is None:
                return self.unavailableResult()
            return self._continue(conn, thread, accountId, role, message)

    # Adds a message to an existing thread; a closed thread is reopened (9 November) so no one is locked out.
    def _continue(self, conn, thread, accountId, role, message):
        if not thread["available"]:
            return Result.fail("UNAVAILABLE", "Messages are unavailable for this conversation.")
        threadId = thread["consultation_id"]
        stamp = clock.now_text()
        self._addMessage(conn, threadId, accountId, message, stamp)
        status = "REPLIED" if role == INTERIOR_DESIGNER else "NEW"
        conn.execute("UPDATE consultations SET status = ?, updated_at = ? WHERE consultation_id = ?",
                     (status, stamp, threadId))
        return Result.succeed("SENT", "Message sent.", {"threadId": threadId})

    # True when the thread's latest message is the same text from the same sender (a double click or retry).
    def _isRepeat(self, conn, threadId, senderId, message):
        last = conn.execute("SELECT sender_id, body FROM consultation_messages WHERE consultation_id = ? "
                            "ORDER BY message_id DESC LIMIT 1", (threadId,)).fetchone()
        return last is not None and last["sender_id"] == senderId and last["body"] == message

    # Closes the designer's thread while keeping its history (either participant can reopen it by writing).
    def close(self, threadId, designerId):
        changed = self.db.execute(
            "UPDATE consultations SET status = 'CLOSED', updated_at = ? "
            "WHERE consultation_id = ? AND designer_id = ? AND status <> 'CLOSED'",
            (clock.now_text(), threadId, designerId),
        )
        if not changed and not self.db.scalar(
            "SELECT 1 FROM consultations WHERE consultation_id = ? AND designer_id = ?", (threadId, designerId),
        ):
            return self.unavailableResult()
        return Result.succeed("CLOSED", "Conversation closed.", {"threadId": threadId})

    # Gives the same response for a missing thread and another participant's thread.
    def unavailableResult(self):
        return Result.fail("NOT_FOUND", "This conversation is unavailable.")

    # Inserts one message into the caller's transaction.
    def _addMessage(self, conn, threadId, senderId, message, stamp):
        conn.execute(
            "INSERT INTO consultation_messages (consultation_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
            (threadId, senderId, message, stamp),
        )
