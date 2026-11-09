"""9 November review of the Messages feature (US62-US64).

1  A closed conversation no longer locks the customer out: writing again reopens it.
2  A message sent from an old "first message" form is added to the existing conversation, not dropped.
9  Customers see "Waiting for Reply" / "Designer Replied" instead of the designer's "New" / "Replied".
11 Unread messages are shown on the Messages button, the designer's Messages menu link and each conversation.
(Item 3, the Messages button covering content on phones, is checked in the browser walkthrough.)
"""
import re
import sqlite3

from app import create_app
from app.entity.database import DatabaseConnection
from tests.test_consultations_and_matcher import sign_in, site, start  # noqa: F401  (site is a fixture)

CLOSED_FOR_CUSTOMER = b"This conversation was closed by the designer. Sending a message will reopen it."
CLOSED_FOR_DESIGNER = b"You closed this conversation. Sending a message will reopen it."


# Returns the number shown in the page's unread badge, or 0 when the badge is hidden.
def unread_badge(html):
    match = re.search(rb'data-unread-badge(?P<hidden> hidden)?[^>]*>\s*<span data-unread-count>(?P<n>\d+)<', html)
    assert match, "the page has no unread badge"
    return 0 if match.group("hidden") else int(match.group("n"))


# Reads a conversation's saved status.
def status_of(db, thread):
    return db.scalar("SELECT status FROM consultations WHERE consultation_id = ?", (thread,))


# Counts the messages saved in a conversation.
def message_count(db, thread):
    return db.scalar("SELECT COUNT(*) FROM consultation_messages WHERE consultation_id = ?", (thread,))


# ---------------------------------------------------------------- 1. closed conversations
class TestClosedConversation:
    # After the designer closes it, the customer still has a message box and is told it will reopen.
    def test_customer_sees_reply_form_after_close(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, url = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        page = customer.get(url).data
        assert CLOSED_FOR_CUSTOMER in page
        assert b'name="message"' in page and b"Send Reply" in page

    # Writing in a closed conversation saves the message and reopens it for the designer.
    def test_customer_message_reopens_closed_conversation(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        response = customer.post("/customer/messages", data={"threadId": thread, "message": "One more question"})
        assert response.status_code == 303
        assert status_of(db, thread) == "NEW" and message_count(db, thread) == 2
        assert b"One more question" in designer.get(f"/designer/messages?threadId={thread}").data

    # Contact Designer on the same project opens the closed conversation with a message box, not a dead end.
    def test_contact_designer_again_after_close(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        page = customer.get("/customer/messages", query_string={"projectId": project}).data
        assert CLOSED_FOR_CUSTOMER in page and b'name="message"' in page

    # The designer can also write again; the conversation reopens as Replied.
    def test_designer_can_reopen_by_writing(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        assert CLOSED_FOR_DESIGNER in designer.get(f"/designer/messages?threadId={thread}").data
        designer.post("/designer/messages", data={"threadId": thread, "message": "Following up on your kitchen"})
        assert status_of(db, thread) == "REPLIED" and message_count(db, thread) == 2

    # Closing still works and the designer no longer sees Close Conversation on a closed thread.
    def test_close_still_marks_conversation_closed(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        assert status_of(db, thread) == "CLOSED"
        assert b"Confirm Close" not in designer.get(f"/designer/messages?threadId={thread}").data


# ---------------------------------------------------------------- 2. message from an old form
class TestMessageFromOldForm:
    # A different message sent from an old first-message form is added to the existing conversation.
    def test_second_first_message_is_kept(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        thread, url = start(customer, project, "First question")
        again = customer.post("/customer/messages", data={"projectId": project, "message": "Second question"})
        assert again.status_code == 303
        assert f"threadId={thread}" in again.headers["Location"]
        assert message_count(db, thread) == 2
        page = customer.get(url).data
        assert b"Second question" in page
        assert b"Message sent." in page
        assert b"You already have a conversation for this project." not in page

    # Sending the same text twice in a row (a double click or a retry) still saves it only once.
    def test_identical_retry_is_not_duplicated(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        thread, _ = start(customer, project, "Same text")
        start(customer, project, "Same text")
        assert message_count(db, thread) == 1

    # A message from an old form reopens a closed conversation instead of being dropped.
    def test_old_form_reopens_closed_conversation(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project, "First question")
        designer.post("/designer/messages", data={"threadId": thread, "action": "close"})
        customer.post("/customer/messages", data={"projectId": project, "message": "Are you still available?"})
        assert status_of(db, thread) == "NEW" and message_count(db, thread) == 2

    # If the designer was suspended, the old form shows why the message was not sent.
    def test_old_form_on_unavailable_conversation_explains(self, site):
        app, db, designer_id, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        thread, _ = start(customer, project, "First question")
        db.execute("UPDATE user_accounts SET status = 'SUSPENDED' WHERE account_id = ?", (designer_id,))
        page = customer.post("/customer/messages", data={"projectId": project, "message": "Hello?"}).data
        assert b"Messages are unavailable for this conversation." in page
        assert message_count(db, thread) == 1


# ---------------------------------------------------------------- 9. status words for customers
class TestCustomerStatusWords:
    # Right after sending, the customer sees "Waiting for Reply", not the designer's "New".
    def test_customer_sees_waiting_for_reply(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        thread, url = start(customer, project)
        for page in (customer.get(url).data, customer.get("/customer/messages").data):
            assert b"Waiting for Reply" in page
            assert b">New<" not in page

    # After the designer answers, the customer sees "Designer Replied".
    def test_customer_sees_designer_replied(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, url = start(customer, project)
        designer.post("/designer/messages", data={"threadId": thread, "message": "Happy to help."})
        for page in (customer.get(url).data, customer.get("/customer/messages").data):
            assert b"Designer Replied" in page
            assert b">Replied<" not in page

    # The designer keeps the inbox words "New" and "Replied".
    def test_designer_keeps_new_and_replied(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        assert b">New<" in designer.get("/designer/messages").data
        designer.post("/designer/messages", data={"threadId": thread, "message": "Happy to help."})
        assert b">Replied<" in designer.get("/designer/messages").data
        assert b"Waiting for Reply" not in designer.get("/designer/messages").data


# ---------------------------------------------------------------- 11. unread messages
class TestUnreadMessages:
    # A new customer message shows "1" on the designer's Messages button and menu link until it is opened.
    def test_designer_badge_until_opened(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        assert unread_badge(designer.get("/designer/home").data) == 0
        thread, _ = start(customer, project)
        home = designer.get("/designer/home").data
        assert unread_badge(home) == 1
        assert home.count(b"data-unread-badge") == 2  # floating Messages button and the Messages menu link
        inbox = designer.get("/designer/messages").data
        assert b"1 unread message" in inbox
        designer.get(f"/designer/messages?threadId={thread}")
        assert unread_badge(designer.get("/designer/home").data) == 0
        assert b"unread message" not in designer.get("/designer/messages").data

    # The customer gets a badge when the designer replies; their own messages never count.
    def test_customer_badge_for_designer_reply_only(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, url = start(customer, project)
        assert unread_badge(customer.get("/customer/home").data) == 0
        designer.post("/designer/messages", data={"threadId": thread, "message": "Happy to help."})
        designer.post("/designer/messages", data={"threadId": thread, "message": "When can I visit?"})
        assert unread_badge(customer.get("/customer/home").data) == 1
        assert b"2 unread messages" in customer.get("/customer/messages").data
        customer.get(url)
        assert unread_badge(customer.get("/customer/home").data) == 0

    # The badge counts conversations, so two unread conversations show "2".
    def test_badge_counts_conversations(self, site):
        app, db, _, project, current, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        start(customer, project)
        start(customer, current)
        assert unread_badge(designer.get("/designer/home").data) == 2

    # The drawer gets the new count in a response header, so the button updates without a page reload.
    def test_drawer_response_carries_count(self, site):
        app, db, _, project, _, _ = site
        customer = sign_in(app, "customer", "amy@example.test")
        designer = sign_in(app, "designer", "dan@example.test")
        thread, _ = start(customer, project)
        headers = {"X-Consultation-Fragment": "1"}
        inbox = designer.get("/designer/messages", headers=headers)
        assert inbox.headers["X-Consultation-Unread"] == "1"
        opened = designer.get(f"/designer/messages?threadId={thread}", headers=headers)
        assert opened.headers["X-Consultation-Unread"] == "0"

    # Staff pages have no Messages badge.
    def test_staff_pages_have_no_badge(self, site):
        app, db, _, _, _, _ = site
        admin = app.test_client()
        page = admin.get("/admin/login").data
        assert b"data-unread-badge" not in page

    # An older database gains the two last-read columns without losing conversations.
    def test_older_database_gains_last_read_columns(self, tmp_path):
        path = tmp_path / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE consultations (
                consultation_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, project_title TEXT NOT NULL,
                customer_id INTEGER NOT NULL, designer_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('NEW', 'REPLIED', 'CLOSED')), updated_at TEXT NOT NULL,
                UNIQUE (customer_id, project_id));
            INSERT INTO consultations (project_id, project_title, customer_id, designer_id, status, updated_at)
            VALUES (1, 'Old Kitchen', 1, 2, 'NEW', '2026-11-01 10:00:00');
        """)
        conn.commit()
        conn.close()
        create_app(str(path), testing=True)
        columns = {row["name"] for row in DatabaseConnection().query("PRAGMA table_info(consultations)")}
        assert {"customer_last_read_id", "designer_last_read_id"} <= columns
        assert DatabaseConnection().scalar("SELECT project_title FROM consultations") == "Old Kitchen"
