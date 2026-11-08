"""DatabaseConnection: the ``db`` attribute held by every Entity collection class.

One SQLite file. Each call opens a short-lived connection with foreign keys ON;
``transaction()`` gives all-or-nothing writes (design NFR: failed writes roll back).
"""
import os
import sqlite3
from contextlib import contextmanager

DEFAULT_PATH = os.environ.get("IDP_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "idp_platform.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    role_code    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role_name    TEXT NOT NULL,
    description  TEXT,
    base_role    TEXT NOT NULL DEFAULT 'PLATFORM_MANAGER'
                 CHECK (base_role IN ('CUSTOMER', 'INTERIOR_DESIGNER', 'USER_ADMIN', 'PLATFORM_MANAGER')),
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_accounts (
    account_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT UNIQUE COLLATE NOCASE,
    name           TEXT NOT NULL,
    email          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    contact_number TEXT NOT NULL DEFAULT '',
    profile_id     INTEGER NOT NULL REFERENCES user_profiles(profile_id),
    status         TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES user_accounts(account_id),
    created_at     TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS companies (
    company_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    designer_id    INTEGER NOT NULL UNIQUE REFERENCES user_accounts(account_id),
    company_name   TEXT NOT NULL,
    description    TEXT,
    address        TEXT,
    contact_email  TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    website        TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interior_design_projects (
    idp_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    designer_id    INTEGER NOT NULL REFERENCES user_accounts(account_id),
    title          TEXT NOT NULL,
    description    TEXT,
    category_id    INTEGER NOT NULL REFERENCES project_categories(category_id),
    project_status TEXT NOT NULL CHECK (project_status IN ('CURRENT', 'PAST')),
    budget         REAL CHECK (budget >= 0),
    photo_url      TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    removed_at     TEXT NULL
);

CREATE TABLE IF NOT EXISTS project_views (
    view_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    idp_id      INTEGER NOT NULL REFERENCES interior_design_projects(idp_id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES user_accounts(account_id),
    viewed_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favourites (
    favourite_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES user_accounts(account_id),
    idp_id       INTEGER NOT NULL REFERENCES interior_design_projects(idp_id) ON DELETE CASCADE,
    saved_at     TEXT NOT NULL,
    removed_at   TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_favourites_current
    ON favourites(customer_id, idp_id) WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_favourites_customer ON favourites(customer_id);
CREATE INDEX IF NOT EXISTS ix_views_idp_time ON project_views(idp_id, viewed_at);
CREATE INDEX IF NOT EXISTS ix_idp_designer ON interior_design_projects(designer_id);
CREATE INDEX IF NOT EXISTS ix_idp_designer_status ON interior_design_projects(designer_id, project_status);
CREATE INDEX IF NOT EXISTS ix_favourites_idp_saved ON favourites(idp_id, saved_at);

CREATE TABLE IF NOT EXISTS consultations (
    consultation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES interior_design_projects(idp_id) ON DELETE SET NULL,
    project_title   TEXT NOT NULL,
    customer_id     INTEGER NOT NULL REFERENCES user_accounts(account_id),
    designer_id     INTEGER NOT NULL REFERENCES user_accounts(account_id),
    status          TEXT NOT NULL CHECK (status IN ('NEW', 'REPLIED', 'CLOSED')),
    updated_at      TEXT NOT NULL,
    UNIQUE (customer_id, project_id)
);

CREATE TABLE IF NOT EXISTS consultation_messages (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id INTEGER NOT NULL REFERENCES consultations(consultation_id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES user_accounts(account_id),
    body            TEXT NOT NULL CHECK (length(trim(body)) BETWEEN 1 AND 2000),
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_consultations_designer ON consultations(designer_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_consultation_messages_thread ON consultation_messages(consultation_id, message_id);
"""

# The four built-in roles. role_code is what login pages check.
CUSTOMER = "CUSTOMER"
INTERIOR_DESIGNER = "INTERIOR_DESIGNER"
USER_ADMIN = "USER_ADMIN"
PLATFORM_MANAGER = "PLATFORM_MANAGER"
STAFF_ROLES = (USER_ADMIN, PLATFORM_MANAGER)
BUILT_IN_ROLES = (CUSTOMER, INTERIOR_DESIGNER, USER_ADMIN, PLATFORM_MANAGER)
DEFAULT_PROFILES = [
    (CUSTOMER, "Customer", "Renovation customers who browse and save projects."),
    (INTERIOR_DESIGNER, "Interior Designer", "Designers who publish company information and projects."),
    (USER_ADMIN, "User Admin", "Staff who manage user accounts and profiles."),
    (PLATFORM_MANAGER, "Platform Manager", "Staff who manage categories and view reports."),
]


class DatabaseConnection:
    path = DEFAULT_PATH

    # Points every collection at a database file (tests use their own file).
    @classmethod
    def configure(cls, path):
        cls.path = path

    # Opens a connection with foreign keys switched on and rows readable by name.
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Runs a SELECT and returns every row as a dictionary.
    def query(self, sql, params=()):
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    # Runs a SELECT and returns the first row, or None.
    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # Runs a SELECT and returns the single value in the first row.
    def scalar(self, sql, params=()):
        conn = self.connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    # Gives a connection where all writes are saved together or rolled back together.
    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Runs one write in its own transaction; returns the new row ID or the rows changed.
    def execute(self, sql, params=()):
        """Run one write in its own transaction; returns lastrowid / rowcount."""
        with self.transaction() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid if sql.lstrip().upper().startswith("INSERT") else cursor.rowcount


CHILD_TABLES = {
    # Rebuilt once in databases created before 6 November so deleting a project cascades (US30).
    "project_views": ("view_id, idp_id, customer_id, viewed_at",
                      SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS project_views"):
                             SCHEMA.index("CREATE TABLE IF NOT EXISTS favourites")]),
    "favourites": ("favourite_id, customer_id, idp_id, saved_at, removed_at",
                   SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS favourites"):
                          SCHEMA.index("CREATE UNIQUE INDEX")]),
}


# Upgrades an older database file in place without losing any rows.
def migrate(path):
    """Upgrade an older database in place, keeping every row (idempotent).

    1. company_information (phone/email) -> companies (contact_number/contact_email), as in the US23-US41 model.
    2. project_views / favourites get ON DELETE CASCADE on idp_id.
    3. user_profiles gets base_role (8 November): built-in profiles are based on themselves and older custom
       profiles on Platform Manager, the staff role with fewer permissions.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        if "company_information" in tables:
            conn.execute(SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS companies"):
                                      SCHEMA.index("CREATE TABLE IF NOT EXISTS interior_design_projects")])
            conn.execute(
                "INSERT OR IGNORE INTO companies (company_id, designer_id, company_name, description, address, "
                "contact_email, contact_number, website, created_at, updated_at) "
                "SELECT company_id, designer_id, company_name, description, address, COALESCE(email, ''), "
                "COALESCE(phone, ''), website, created_at, updated_at FROM company_information")
            conn.execute("DROP TABLE company_information")
        for table, (columns, ddl) in CHILD_TABLES.items():
            if table not in tables:
                continue
            keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            if any(k[3] == "idp_id" and k[6] == "CASCADE" for k in keys):
                continue
            conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
            conn.execute(ddl)
            conn.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {table}_old")
            conn.execute(f"DROP TABLE {table}_old")
        if "user_profiles" in tables:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(user_profiles)")}
            if "base_role" not in columns:
                conn.execute("ALTER TABLE user_profiles ADD COLUMN base_role TEXT NOT NULL DEFAULT 'PLATFORM_MANAGER'")
                conn.execute("UPDATE user_profiles SET base_role = role_code WHERE role_code IN (?, ?, ?, ?)",
                             BUILT_IN_ROLES)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


# Creates the tables and the four built-in profiles, after upgrading an older file.
def init_db(path=None):
    """Create tables and the four default user profiles (idempotent); upgrade older databases first."""
    from app.common import clock
    if path:
        DatabaseConnection.configure(path)
    db = DatabaseConnection()
    if os.path.exists(DatabaseConnection.path):
        migrate(DatabaseConnection.path)
    with db.transaction() as conn:
        conn.executescript(SCHEMA)
        # Bring any legacy fractional-cent budgets in line with the amount shown and filtered.
        conn.execute("UPDATE interior_design_projects SET budget = ROUND(budget, 2) "
                     "WHERE budget <> ROUND(budget, 2)")
        stamp = clock.now_text()
        for code, name, description in DEFAULT_PROFILES:
            conn.execute(
                "INSERT OR IGNORE INTO user_profiles (role_code, role_name, description, base_role, status, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)", (code, name, description, code, stamp, stamp))
    return db
