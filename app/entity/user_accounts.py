"""UserAccount (record) and UserAccounts (persistent collection). Table: user_accounts.

Shared by Member 1 (registration, login, personal details) and Member 5 (User Admin management).
Passwords are stored only as a salted hash (werkzeug PBKDF2), never as plain text.
"""
import sqlite3
from dataclasses import dataclass

from werkzeug.security import generate_password_hash, check_password_hash

from app.common import clock
from app.common.result import Result
from app.common.text import plural, matches
from app.common.validators import contains_pattern
from app.entity.database import DatabaseConnection, STAFF_ROLES

ACCOUNT_SELECT = (
    "SELECT a.*, p.role_code, p.role_name, p.base_role, p.status AS profile_status "
    "FROM user_accounts a JOIN user_profiles p ON p.profile_id = a.profile_id"
)


@dataclass
class UserAccount:
    accountId: int
    username: str
    name: str
    email: str
    passwordHash: str
    contactNumber: str
    profileId: int
    status: str
    createdAt: str
    roleCode: str = ""
    roleName: str = ""
    profileStatus: str = ""
    baseRole: str = ""

    # The account's name (the Member 5 diagrams call it displayName).
    @property
    def displayName(self):  # Member 5 diagrams call the name "displayName"
        return self.name

    # True when the password matches the stored salted hash.
    def checkPassword(self, password):
        return check_password_hash(self.passwordHash, password or "")

    # The account's details without the password hash, safe to show on pages.
    def safe(self):
        """Data that may leave the Entity layer (no password hash)."""
        return {
            "accountId": self.accountId, "username": self.username or "", "name": self.name,
            "email": self.email, "contactNumber": self.contactNumber, "profileId": self.profileId,
            "roleCode": self.roleCode, "roleName": self.roleName, "status": self.status,
            "profileStatus": self.profileStatus, "createdAt": self.createdAt, "baseRole": self.baseRole,
        }

    # Builds an account record (with its profile and base role) from a database row.
    @classmethod
    def from_row(cls, row):
        return cls(row["account_id"], row["username"], row["name"], row["email"], row["password_hash"],
                   row["contact_number"], row["profile_id"], row["status"], row["created_at"],
                   row.get("role_code", ""), row.get("role_name", ""), row.get("profile_status", ""),
                   row.get("base_role") or row.get("role_code", ""))


class UserAccounts:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # ----- Member 1 -----
    # True when an account already uses this email (any case).
    def isEmailRegistered(self, email):
        return self.db.scalar("SELECT COUNT(*) FROM user_accounts WHERE email = ?", ((email or "").strip(),)) > 0

    # US01/US06/US42: creates an account with a salted password hash and the right profile.
    def create(self, request, role=None):
        """US01/US06: create(request: RegistrationRequest, role) and US42: create(request: CreateAccountRequest)."""
        if role is not None:
            name = request.name.strip()
            # Older databases may still contain a built-in profile suspended by a previous version.
            profile_filter, profile_params = "role_code = ? AND status = 'ACTIVE'", (role,)
            profile_error = "Registration is unavailable because this role is inactive. Please contact the administrator."
        else:
            name = request.displayName.strip()
            # US42: staff accounts may use any active profile based on User Admin or Platform Manager,
            # including custom profiles (8 November "Based on" option).
            profile_filter = "profile_id = ? AND status = 'ACTIVE' AND base_role IN (?, ?)"
            profile_params = (request.profileId, *STAFF_ROLES)
            profile_error = "Choose an active User Admin or Platform Manager profile."
        stamp = clock.now_text()
        fields = (name, request.email.strip().lower(), generate_password_hash(request.password),
                  (request.contactNumber or "").strip(), stamp, stamp)
        try:
            with self.db.transaction() as conn:
                # Check the profile and insert in one statement so a concurrent suspension cannot slip between them.
                cursor = conn.execute(
                    "INSERT INTO user_accounts (name, email, password_hash, contact_number, profile_id, "
                    "status, created_at, updated_at) "
                    "SELECT ?, ?, ?, ?, profile_id, 'ACTIVE', ?, ? FROM user_profiles WHERE " + profile_filter,
                    fields + profile_params,
                )
                if not cursor.rowcount:
                    return Result.fail("INVALID_PROFILE", profile_error)
                new_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return Result.fail("DUPLICATE", "This email is already registered.")
        return Result.succeed("CREATED", "Account created.", {"accountId": new_id})

    # Returns the account with this email (any case), or None.
    def findByEmail(self, email):
        row = self.db.query_one(ACCOUNT_SELECT + " WHERE a.email = ?", ((email or "").strip(),))
        return UserAccount.from_row(row) if row else None

    # Returns the account with this ID, or None.
    def getById(self, accountId):
        row = self.db.query_one(ACCOUNT_SELECT + " WHERE a.account_id = ?", (accountId,))
        return UserAccount.from_row(row) if row else None

    # US03: returns the account's safe details, or a not-found failure.
    def findById(self, accountId):
        account = self.getById(accountId)
        if account is None:
            return Result.fail("NOT_FOUND", "Account not found.")
        return Result.succeed("FOUND", "", account.safe())

    # US04: saves a Customer's new name and contact number.
    def updateDetails(self, accountId, name, contactNumber):
        changed = self.db.execute(
            "UPDATE user_accounts SET name = ?, contact_number = ?, updated_at = ? WHERE account_id = ?",
            (name.strip(), contactNumber.strip(), clock.now_text(), accountId))
        if changed == 0:
            return Result.fail("NOT_FOUND", "Account not found.")
        return Result.succeed("UPDATED", "Your details have been updated.")

    # ----- Member 5 (US42-US46) -----
    # US43: returns an account's safe details, or a 'no longer exists' failure.
    def find(self, request):
        account = self.getById(request.accountId)
        if account is None:
            return Result.fail("NOT_FOUND", "This account no longer exists.")
        return Result.succeed("FOUND", "", account.safe())

    # US44: saves an account's new name, email and contact number together.
    def update(self, request):
        # US44: the three editable fields are saved together; the profile and credentials stay attached.
        try:
            changed = self.db.execute(
                "UPDATE user_accounts SET name = ?, email = ?, contact_number = ?, updated_at = ? "
                "WHERE account_id = ?",
                (request.displayName.strip(), request.email.strip().lower(), request.contactNumber.strip(),
                 clock.now_text(), request.accountId))
        except sqlite3.IntegrityError:
            return Result.fail("DUPLICATE", "This email is already used by another account.")
        if not changed:
            return Result.fail("NOT_FOUND", "This account no longer exists.")
        return Result.succeed("UPDATED", "Account updated.", self.getById(request.accountId).safe())

    # US45: suspends the account and ends its sessions in one transaction.
    def suspend(self, request):
        try:
            with self.db.transaction() as conn:
                # US45: revoke all sessions in the same transaction as the status change.
                changed = conn.execute(
                    "UPDATE user_accounts SET status = 'SUSPENDED', updated_at = ? "
                    "WHERE account_id = ? AND status = 'ACTIVE'", (clock.now_text(), request.accountId),
                ).rowcount
                if not changed:
                    exists = conn.execute("SELECT 1 FROM user_accounts WHERE account_id = ?",
                                          (request.accountId,)).fetchone()
                    if not exists:
                        return Result.fail("NOT_FOUND", "This account no longer exists.")
                    return Result.fail("ALREADY_SUSPENDED", "This account is already suspended.")
                conn.execute("DELETE FROM sessions WHERE account_id = ?", (request.accountId,))
        except sqlite3.DatabaseError:
            return Result.fail("SUSPEND_FAILED", "The account could not be suspended. Please try again.")
        return Result.succeed("SUSPENDED", "Account suspended.")

    # US60: makes a suspended account active again, noting a still-suspended profile.
    def reactivate(self, request):
        changed = self.db.execute(
            "UPDATE user_accounts SET status = 'ACTIVE', updated_at = ? WHERE account_id = ? AND status = 'SUSPENDED'",
            (clock.now_text(), request.accountId))
        account = self.getById(request.accountId)
        if account is None:
            return Result.fail("NOT_FOUND", "This account no longer exists.")
        if not changed:
            return Result.fail("ALREADY_ACTIVE", "This account is already active.")
        message = "Account reactivated."
        if account.profileStatus != "ACTIVE":
            # US60 A3: the account is active again, but its suspended profile still blocks the login.
            message += (f" Their {account.roleName} profile is still suspended, so they cannot log in "
                        "until the profile is reactivated.")
        return Result.succeed("REACTIVATED", message)

    # US46: every account, oldest first.
    def listAll(self):
        return self._listResult()

    # US46: accounts whose name or email contains the keyword, optionally for one profile.
    def search(self, request):
        keyword = (request.keyword or "").strip()
        where = " WHERE 1 = 1"
        params = []
        if keyword:
            like = contains_pattern(keyword)
            where += " AND (a.name LIKE ? ESCAPE '!' OR a.email LIKE ? ESCAPE '!')"
            params += [like, like]
        if request.profileId not in (None, "", "ALL"):
            where += " AND a.profile_id = ?"
            params.append(int(request.profileId))
        empty = f"No accounts match '{keyword}'." if keyword else "No accounts match the selected profile."
        found = (lambda n: matches(n, "account", keyword)) if keyword else \
            (lambda n: f"{plural(n, 'account')} with the selected profile")
        return self._listResult(where, params, empty, found)

    # Runs an account list query and words the count message.
    def _listResult(self, where="", params=(), empty="No accounts yet.", found=None):
        # US46/US48: count every match so a profile's account total agrees with its filtered account list.
        rows = self.db.query(ACCOUNT_SELECT + where + " ORDER BY a.account_id", params)
        accounts = [UserAccount.from_row(r).safe() for r in rows]
        if not accounts:
            return Result.succeed("EMPTY", empty, [])
        message = found(len(accounts)) if found else plural(len(accounts), "account")
        return Result.succeed("FOUND", message, accounts)
