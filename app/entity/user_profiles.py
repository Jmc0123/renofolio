"""UserProfile (record) and UserProfiles (persistent collection). Table: user_profiles."""
import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from app.common import clock
from app.common.result import Result
from app.common.text import matches
from app.common.validators import contains_pattern
from app.entity.database import DatabaseConnection, BUILT_IN_ROLES

# Labels for the roles a profile can be based on (US47, 8 November "Based on" option).
ROLE_LABELS = {"CUSTOMER": "Customer", "INTERIOR_DESIGNER": "Interior Designer", "USER_ADMIN": "User Admin",
               "PLATFORM_MANAGER": "Platform Manager"}


@dataclass
class UserProfile:
    profileId: int
    roleCode: str
    roleName: str
    description: str
    status: str
    createdAt: str
    baseRole: str = ""

    # The role name (the Member 5 diagrams call it displayName).
    @property
    def displayName(self):  # Member 5 diagrams call the role name "displayName"
        return self.roleName

    # True when the profile is active.
    @property
    def isActive(self):
        return self.status == "ACTIVE"

    # True for the four built-in profiles, which cannot be suspended.
    @property
    def isBuiltIn(self):
        return self.roleCode in BUILT_IN_ROLES

    # The readable name of the role this profile is based on.
    @property
    def baseRoleLabel(self):
        return ROLE_LABELS.get(self.baseRole, self.baseRole)

    # Builds a profile record from a database row.
    @classmethod
    def from_row(cls, row):
        return cls(row["profile_id"], row["role_code"], row["role_name"], row["description"] or "",
                   row["status"], row["created_at"], row.get("base_role") or row["role_code"])


class UserProfiles:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # ----- used by login (Member 1) -----
    # Returns the profile with this ID, or None.
    def findById(self, profileId):
        row = self.db.query_one("SELECT * FROM user_profiles WHERE profile_id = ?", (profileId,))
        return UserProfile.from_row(row) if row else None

    # Returns the profile with this internal role code, or None.
    def findByRoleCode(self, roleCode):
        row = self.db.query_one("SELECT * FROM user_profiles WHERE role_code = ?", (roleCode,))
        return UserProfile.from_row(row) if row else None

    # Every profile, oldest first.
    def listAll(self):
        return [UserProfile.from_row(r) for r in self.db.query("SELECT * FROM user_profiles ORDER BY profile_id")]

    # ----- US47-US51 (Member 5) -----
    # US47: saves a new profile with a unique role name and its Based on role.
    def create(self, request):
        stamp = clock.now_text()
        name = request.displayName.strip()
        # US47: role names are entered by admins. Internal role codes keep the built-in login roles stable.
        code = f"CUSTOM_{uuid4().hex.upper()}"
        with self.db.transaction() as conn:
            # Checking the role name inside the INSERT also covers two simultaneous submissions.
            cursor = conn.execute(
                "INSERT INTO user_profiles (role_code, role_name, description, base_role, status, created_at, "
                "updated_at) SELECT ?, ?, ?, ?, 'ACTIVE', ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM user_profiles WHERE role_name = ? COLLATE NOCASE)",
                (code, name, (request.description or "").strip(), request.basedOn, stamp, stamp, name),
            )
            if not cursor.rowcount:
                return Result.fail("DUPLICATE", "This role name already exists.")
            new_id = cursor.lastrowid
        return Result.succeed("CREATED", "Profile created.", self.findById(new_id))

    # US48: returns a profile and how many accounts use it.
    def find(self, request):
        profile = self.findById(request.profileId)
        if profile is None:
            return Result.fail("NOT_FOUND", "This profile no longer exists.")
        count = self.db.scalar("SELECT COUNT(*) FROM user_accounts WHERE profile_id = ?", (profile.profileId,))
        return Result.succeed("FOUND", "", {"profile": profile, "accountCount": count})

    # US49: saves a profile's new description.
    def update(self, request):
        # US49: only the description is editable, including for built-in profiles.
        changed = self.db.execute(
            "UPDATE user_profiles SET description = ?, updated_at = ? WHERE profile_id = ?",
            (request.description.strip(), clock.now_text(), request.profileId))
        if changed == 0:
            return Result.fail("NOT_FOUND", "This profile no longer exists.")
        return Result.succeed("UPDATED", "Profile updated.", self.findById(request.profileId))

    # US50: suspends a custom profile and ends its accounts' sessions in one transaction.
    def suspend(self, request):
        try:
            with self.db.transaction() as conn:
                profile = conn.execute("SELECT role_code, status FROM user_profiles WHERE profile_id = ?",
                                       (request.profileId,)).fetchone()
                if profile is None:
                    return Result.fail("NOT_FOUND", "This profile no longer exists.")
                # US50 A2 (8 November): no built-in profile can be suspended, so a whole user type is never
                # blocked by one click. Single people are blocked by suspending their account (US45).
                if profile["role_code"] in BUILT_IN_ROLES:
                    return Result.fail("BUILT_IN_PROFILE", "Built-in profiles cannot be suspended.")
                own = conn.execute("SELECT 1 FROM user_accounts WHERE account_id = ? AND profile_id = ?",
                                   (request.actorAccountId, request.profileId)).fetchone()
                if own:
                    return Result.fail("OWN_PROFILE", "You cannot suspend your own profile.")
                changed = conn.execute(
                    "UPDATE user_profiles SET status = 'SUSPENDED', updated_at = ? "
                    "WHERE profile_id = ? AND status = 'ACTIVE'", (clock.now_text(), request.profileId)).rowcount
                if not changed:
                    return Result.fail("ALREADY_SUSPENDED", "This profile is already suspended.")
                # US50: expire the role's sessions in the same transaction, without rewriting its accounts.
                conn.execute(
                    "DELETE FROM sessions WHERE account_id IN "
                    "(SELECT account_id FROM user_accounts WHERE profile_id = ?)", (request.profileId,),
                )
        except sqlite3.DatabaseError:
            return Result.fail("SUSPEND_FAILED", "The profile could not be suspended. Please try again.")
        return Result.succeed("SUSPENDED", "Profile suspended.")

    # US61: makes a suspended profile active again.
    def reactivate(self, request):
        changed = self.db.execute(
            "UPDATE user_profiles SET status = 'ACTIVE', updated_at = ? WHERE profile_id = ? AND status = 'SUSPENDED'",
            (clock.now_text(), request.profileId))
        if changed:
            return Result.succeed("REACTIVATED", "Profile reactivated.")
        if self.findById(request.profileId) is None:
            return Result.fail("NOT_FOUND", "This profile no longer exists.")
        return Result.fail("ALREADY_ACTIVE", "This profile is already active.")

    # US51: profiles whose role name or description contains the keyword.
    def search(self, request):
        like = contains_pattern(request.keyword)
        rows = self.db.query(
            "SELECT * FROM user_profiles WHERE role_name LIKE ? ESCAPE '!' OR description LIKE ? ESCAPE '!' "
            "ORDER BY profile_id", (like, like),
        )
        profiles = [UserProfile.from_row(r) for r in rows]
        if not profiles:
            return Result.succeed("EMPTY", f"No profiles match '{request.keyword.strip()}'.", [])
        return Result.succeed("FOUND", matches(len(profiles), "profile", request.keyword), profiles)
