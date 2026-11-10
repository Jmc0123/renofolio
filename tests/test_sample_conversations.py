"""10 November: the sample data needs 100+ conversations and 100+ messages (US62-US64).

The project specification asks for about 100 records for each kind of data. The generator made none for
the two Messages tables, so these checks were written first and failed before the generator was changed.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app import create_app
from tests.conftest import PASSWORD

ROOT = Path(__file__).resolve().parents[1]
# Totals of the older tables, which adding conversations must not change.
OLDER_TOTALS = {"user_profiles": 100, "user_accounts": 282, "companies": 110, "project_categories": 120,
                "interior_design_projects": 320, "project_views": 1093, "favourites": 576}


# Runs the generator once and returns the database path and what the script printed.
@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    path = tmp_path_factory.mktemp("sample") / "demo.db"
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_test_data.py"), "--db", str(path)],
                         check=True, capture_output=True, text=True)
    return str(path), run.stdout


# Opens the generated database with rows that can be read by column name.
@pytest.fixture
def rows(generated):
    conn = sqlite3.connect(generated[0])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# Returns the account ID for an email address.
def account_id(rows, email):
    return rows.execute("SELECT account_id FROM user_accounts WHERE email = ?", (email,)).fetchone()[0]


# Returns the number shown in the page's unread badge, or 0 when the badge is hidden.
def badge(client, url):
    import re
    match = re.search(rb'data-unread-badge(?P<hidden> hidden)?[^>]*>\s*<span data-unread-count>(?P<n>\d+)<',
                      client.get(url).data)
    return 0 if match.group("hidden") else int(match.group("n"))


class TestSampleConversations:
    # There are at least 100 conversations and 100 messages, and the script reports both totals.
    def test_at_least_100_of_each(self, generated, rows):
        assert rows.execute("SELECT COUNT(*) FROM consultations").fetchone()[0] >= 100
        assert rows.execute("SELECT COUNT(*) FROM consultation_messages").fetchone()[0] >= 100
        assert "consultations" in generated[1] and "consultation_messages" in generated[1]

    # The older tables keep exactly the same totals as before.
    def test_older_totals_are_unchanged(self, rows):
        for table, total in OLDER_TOTALS.items():
            assert rows.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == total, table

    # Every conversation joins an active customer to the designer who owns the project, with the project's title.
    def test_conversations_match_their_project(self, rows):
        wrong = rows.execute(
            "SELECT COUNT(*) FROM consultations t "
            "JOIN interior_design_projects p ON p.idp_id = t.project_id "
            "JOIN user_accounts c ON c.account_id = t.customer_id JOIN user_profiles cp ON cp.profile_id = c.profile_id "
            "JOIN user_accounts d ON d.account_id = t.designer_id "
            "WHERE p.designer_id <> t.designer_id OR p.title <> t.project_title OR cp.role_code <> 'CUSTOMER' "
            "OR c.status <> 'ACTIVE' OR d.status <> 'ACTIVE'").fetchone()[0]
        assert wrong == 0
        assert rows.execute("SELECT COUNT(*) FROM consultations WHERE project_id IS NULL").fetchone()[0] == 0

    # Every conversation starts with the customer, and only its two participants write in it.
    def test_messages_belong_to_the_two_participants(self, rows):
        strangers = rows.execute(
            "SELECT COUNT(*) FROM consultation_messages m JOIN consultations t ON t.consultation_id = m.consultation_id "
            "WHERE m.sender_id NOT IN (t.customer_id, t.designer_id)").fetchone()[0]
        assert strangers == 0
        not_customer_first = rows.execute(
            "SELECT COUNT(*) FROM consultations t JOIN consultation_messages m ON m.message_id = "
            "(SELECT MIN(message_id) FROM consultation_messages WHERE consultation_id = t.consultation_id) "
            "WHERE m.sender_id <> t.customer_id").fetchone()[0]
        assert not_customer_first == 0
        assert rows.execute("SELECT COUNT(*) FROM consultations t WHERE NOT EXISTS "
                            "(SELECT 1 FROM consultation_messages m WHERE m.consultation_id = t.consultation_id)"
                            ).fetchone()[0] == 0

    # New means the customer wrote last, Replied means the designer wrote last, and all three statuses appear.
    def test_status_matches_the_last_message(self, rows):
        threads = rows.execute(
            "SELECT t.status, t.customer_id, t.designer_id, m.sender_id FROM consultations t "
            "JOIN consultation_messages m ON m.message_id = "
            "(SELECT MAX(message_id) FROM consultation_messages WHERE consultation_id = t.consultation_id)").fetchall()
        assert {t["status"] for t in threads} == {"NEW", "REPLIED", "CLOSED"}
        for t in threads:
            if t["status"] == "NEW":
                assert t["sender_id"] == t["customer_id"]
            elif t["status"] == "REPLIED":
                assert t["sender_id"] == t["designer_id"]

    # Messages are saved in time order, none is in the future, and the conversation time is its latest activity.
    def test_times_are_in_order(self, rows):
        now = rows.execute("SELECT strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime', '+1 minute')").fetchone()[0]
        assert rows.execute("SELECT MAX(created_at) FROM consultation_messages").fetchone()[0] <= now
        out_of_order = rows.execute(
            "SELECT COUNT(*) FROM consultation_messages a JOIN consultation_messages b "
            "ON b.consultation_id = a.consultation_id AND b.message_id > a.message_id "
            "WHERE b.created_at < a.created_at").fetchone()[0]
        assert out_of_order == 0
        stale = rows.execute(
            "SELECT COUNT(*) FROM consultations t WHERE t.updated_at < "
            "(SELECT MAX(created_at) FROM consultation_messages WHERE consultation_id = t.consultation_id)"
        ).fetchone()[0]
        assert stale == 0

    # The last-read markers point at real messages, and some conversations are unread on each side.
    def test_some_conversations_are_unread(self, rows):
        beyond = rows.execute(
            "SELECT COUNT(*) FROM consultations t WHERE MAX(t.customer_last_read_id, t.designer_last_read_id) > "
            "(SELECT MAX(message_id) FROM consultation_messages WHERE consultation_id = t.consultation_id)"
        ).fetchone()[0]
        assert beyond == 0
        for member, marker in (("customer_id", "customer_last_read_id"), ("designer_id", "designer_last_read_id")):
            unread = rows.execute(
                f"SELECT COUNT(*) FROM consultations t WHERE EXISTS (SELECT 1 FROM consultation_messages m "
                f"WHERE m.consultation_id = t.consultation_id AND m.sender_id <> t.{member} "
                f"AND m.message_id > t.{marker})").fetchone()[0]
            total = rows.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
            assert 0 < unread < total, member

    # The demo designer and demo customer both have conversations to show, including one with each other.
    def test_demo_accounts_have_conversations(self, rows):
        customer, designer = account_id(rows, "customer@demo.com"), account_id(rows, "designer@demo.com")
        inbox = rows.execute("SELECT status FROM consultations WHERE designer_id = ?", (designer,)).fetchall()
        assert len(inbox) >= 6 and {t["status"] for t in inbox} == {"NEW", "REPLIED", "CLOSED"}
        history = rows.execute("SELECT status FROM consultations WHERE customer_id = ?", (customer,)).fetchall()
        assert len(history) >= 3 and {t["status"] for t in history} == {"NEW", "REPLIED", "CLOSED"}
        assert rows.execute("SELECT COUNT(*) FROM consultations WHERE customer_id = ? AND designer_id = ?",
                            (customer, designer)).fetchone()[0] == 1

    # Logging in as either demo account shows an unread number and a filled Messages page.
    def test_demo_logins_show_unread_badges(self, generated):
        app = create_app(generated[0], testing=True)
        for role, home in (("customer", "/customer/home"), ("designer", "/designer/home")):
            client = app.test_client()
            assert client.post(f"/{role}/login", data={"email": f"{role}@demo.com", "password": PASSWORD}
                               ).status_code == 302
            assert badge(client, home) >= 1
            page = client.get(f"/{role}/messages").data
            assert b"unread message" in page and b"consultation-inbox" in page

    # The same seed gives the same conversations, so every teammate's database matches.
    def test_same_seed_gives_same_conversations(self, generated, tmp_path):
        again = tmp_path / "again.db"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_test_data.py"), "--db", str(again)],
                       check=True, capture_output=True)
        query = ("SELECT t.customer_id, t.project_id, t.status, m.sender_id, m.body FROM consultations t "
                 "JOIN consultation_messages m ON m.consultation_id = t.consultation_id ORDER BY m.message_id")
        first = sqlite3.connect(generated[0]).execute(query).fetchall()
        second = sqlite3.connect(str(again)).execute(query).fetchall()
        assert first == second and len(first) >= 100
