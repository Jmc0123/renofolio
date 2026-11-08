"""US02, US05, US07-US12 - log in / log out for the four roles, plus the shared access guard."""
from app.common.result import Result
from app.common.validators import is_blank
from app.control.base import Controller
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER, USER_ADMIN, PLATFORM_MANAGER
from app.entity.sessions import Sessions
from app.entity.user_accounts import UserAccounts
from app.entity.user_profiles import UserProfiles


class _LoginController(Controller):
    role = None

    # Sets up the controller with accounts, profiles and sessions.
    def __init__(self):
        self.accounts = UserAccounts()
        self.profiles = UserProfiles()
        self.sessions = Sessions()

    # Logs a user in: checks email, password, status and role, then starts a session.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        account = self.accounts.findByEmail(request.email)
        if account is None:
            return self.loginFailedResult()
        profile = self.profiles.findById(account.profileId)
        ok = self.verifyPassword(account, request.password)
        result = self.checkAccountStatus(ok, account, profile, self.role)
        if result.ok:
            session_id = self.sessions.createSession(account.accountId)
            # roleCode is the role whose pages the user gets; for a custom staff profile that is its base role.
            result.data = {"sessionId": session_id, "accountId": account.accountId,
                           "name": account.name, "roleCode": profile.baseRole, "roleName": profile.roleName}
        return result

    # Checks both email and password were entered.
    def validateRequest(self, request):
        if is_blank(request.email) or is_blank(request.password):
            return self.reject("Please enter both your email and password.")
        return True

    # Compares the password with the stored salted hash.
    def verifyPassword(self, account, password):
        return account.checkPassword(password)

    # Rejects a wrong password, a suspended account or profile, or the wrong login page.
    def checkAccountStatus(self, ok, account, profile, role):
        if not ok:
            return self.loginFailedResult()
        if account.status != "ACTIVE" or profile is None or profile.status != "ACTIVE":
            return Result.fail("SUSPENDED", "Your account is suspended. Please contact the administrator.")
        if profile.baseRole != role:
            return Result.fail("WRONG_ROLE", "Please use the login page for your account type.")
        return Result.succeed("LOGGED_IN", f"Welcome back, {account.name}.")

    # The same failure for an unknown email or a wrong password.
    def loginFailedResult(self):
        # Same message for unknown email and wrong password, so accounts are not revealed.
        return Result.fail("LOGIN_FAILED", "Invalid email or password")


class CustomerLoginController(_LoginController):
    """US02"""
    role = CUSTOMER


class DesignerLoginController(_LoginController):
    """US07"""
    role = INTERIOR_DESIGNER


class UserAdminLoginController(_LoginController):
    """US09"""
    role = USER_ADMIN


class PlatformManagerLoginController(_LoginController):
    """US11"""
    role = PLATFORM_MANAGER


class _LogoutController(Controller):
    # Sets up the controller with the sessions.
    def __init__(self):
        self.sessions = Sessions()

    # Ends the session and confirms the logout.
    def execute(self, request):
        # Deleting an expired/unknown ID is safe and ensures no server row is left behind.
        self.sessions.endSession(request.sessionId)
        return Result.succeed("LOGGED_OUT", "You have been logged out.")


class CustomerLogoutController(_LogoutController):
    """US05"""


class DesignerLogoutController(_LogoutController):
    """US08"""


class UserAdminLogoutController(_LogoutController):
    """US10"""


class PlatformManagerLogoutController(_LogoutController):
    """US12"""


class AccessGuardController(Controller):
    """Shared Member 1 access guard: every protected page checks the session and role first."""

    # Sets up the guard with sessions and accounts.
    def __init__(self):
        self.sessions = Sessions()
        self.accounts = UserAccounts()

    # Checks the session is live, the account and profile are active and the role is right.
    def execute(self, request, role):
        account_id = self.sessions.getAccountId(request.sessionId)
        if account_id is None:
            # Bug 2 (8 November): suspending an account or profile deletes its sessions, so a missing session
            # may mean "suspended" rather than "expired". The signed cookie remembers whose session it was.
            hint = getattr(request, "accountId", None)  # only SessionRequest carries it; other requests do not
            if hint is not None and self.isSuspended(self.accounts.getById(hint)):
                return self.suspendedResult()
            return self.sessionExpiredResult()
        account = self.accounts.getById(account_id)
        if account is None or self.isSuspended(account):
            self.sessions.endSession(request.sessionId)
            return self.suspendedResult()
        if account.baseRole != role:
            return Result.fail("FORBIDDEN", "You do not have access to that page.")
        return Result.succeed("ALLOWED", "", {"accountId": account.accountId, "name": account.name,
                                              "roleCode": account.baseRole, "roleName": account.roleName})

    # True when the account or its profile is not active.
    def isSuspended(self, account):
        return account is None or account.status != "ACTIVE" or account.profileStatus != "ACTIVE"

    # The failure for a suspended account, worded like the login page.
    def suspendedResult(self):
        return Result.fail("SUSPENDED", "Your account is suspended. Please contact the administrator.")
