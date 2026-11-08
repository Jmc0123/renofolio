"""US42-US51 - User Admin manages user accounts and user (role) profiles.

The shared role guard validates the session before the Boundary calls these Controllers.
Controllers validate the fields and enforce the admin rules, then delegate persistence to Entities.
"""
from app.common.result import Result
from app.common.text import plural
from app.common.validators import is_blank, valid_email, valid_contact, to_positive_int, MIN_PASSWORD_LENGTH
from app.control.base import Controller
from app.entity.user_accounts import UserAccounts
from app.entity.database import STAFF_ROLES
from app.entity.user_profiles import UserProfiles


# ------------------------------------------------------------------ accounts
class CreateUserAccountController(Controller):
    """US42 Create User Account (platform staff: User Admins and Platform Managers)."""

    # Sets up the controller with the user accounts.
    def __init__(self):
        self.model = UserAccounts()

    # US42: creates a staff account with an allowed staff profile.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.create(request)

    # Checks name, email, password, contact number and profile.
    def validateRequest(self, request):
        if any(is_blank(v) for v in (request.displayName, request.email, request.password, request.contactNumber)):
            return self.reject("Full name, email, password and contact number are required.")
        if not valid_email(request.email):
            return self.reject("Please enter a valid email address.")
        if len(request.password) < MIN_PASSWORD_LENGTH:
            return self.reject(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if not valid_contact(request.contactNumber):
            return self.reject("Contact number must be 8-15 digits.")
        if to_positive_int(request.profileId) is None:
            return self.reject("Please choose a profile.")
        request.profileId = int(request.profileId)
        return True


class ViewUserAccountController(Controller):
    """US43 View User Account."""

    # Sets up the controller with the user accounts.
    def __init__(self):
        self.model = UserAccounts()

    # US43: returns one account's details (never the password hash).
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.find(request)

    # Checks the account ID is a whole number.
    def validateRequest(self, request):
        if to_positive_int(request.accountId) is None:
            return self.reject("Invalid account ID.")
        request.accountId = int(request.accountId)
        return True


class UpdateUserAccountController(Controller):
    """US44 Update User Account."""

    # Sets up the controller with the user accounts.
    def __init__(self):
        self.model = UserAccounts()

    # US44: saves an account's new name, email and contact number.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.update(request)

    # Checks the account ID, name, email and contact number.
    def validateRequest(self, request):
        if to_positive_int(request.accountId) is None:
            return self.reject("Invalid account ID.")
        if is_blank(request.displayName):
            return self.reject("Full name is required.")
        if not valid_email(request.email):
            return self.reject("Please enter a valid email address.")
        if not valid_contact(request.contactNumber):
            return self.reject("Contact number must be 8-15 digits.")
        request.accountId = int(request.accountId)
        return True


class SuspendUserAccountController(ViewUserAccountController):
    """US45 Suspend User Account (the user can no longer log in; open sessions are ended)."""

    # US45: suspends an account, but never the User Admin's own.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        # US45: the acting account ID comes from the validated session.
        if to_positive_int(request.actorAccountId) is None:
            return self.sessionExpiredResult()
        if request.accountId == request.actorAccountId:
            return Result.fail("OWN_ACCOUNT", "You cannot suspend your own account.")
        return self.model.suspend(request)


class ReactivateUserAccountController(ViewUserAccountController):
    """US60 Reactivate User Account (8 November): a suspended account can log in again."""

    # US60: makes a suspended account active again.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.reactivate(request)


class SearchUserAccountController(Controller):
    """US46 Search User Accounts by name, email or profile."""

    # Sets up the controller with the user accounts.
    def __init__(self):
        self.model = UserAccounts()

    # US46: lists all accounts, or those matching a name/email and profile.
    def execute(self, request=None):
        if request is None:
            return self.model.listAll()
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.search(request)

    # Checks a keyword or a profile was given and is valid.
    def validateRequest(self, request):
        if is_blank(request.keyword) and request.profileId in (None, "", "ALL"):
            return self.reject("Please enter a name, email or profile.")
        if len(request.keyword or "") > 100:
            return self.reject("Search text must be 100 characters or fewer.")
        if request.profileId not in (None, "", "ALL") and to_positive_int(request.profileId) is None:
            return self.reject("Invalid profile.")
        return True


# ------------------------------------------------------------------ profiles
class CreateUserProfileController(Controller):
    """US47 Create User Profile."""

    # Sets up the controller with the user profiles.
    def __init__(self):
        self.model = UserProfiles()

    # US47: creates a profile based on User Admin or Platform Manager.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.create(request)

    # Checks the role name, description length and Based on role.
    def validateRequest(self, request):
        if is_blank(request.displayName):
            return self.reject("Please enter a role name.")
        if len(request.description or "") > 500:
            return self.reject("Description must be 500 characters or fewer.")
        # 8 November: a new profile is based on one staff role, whose pages its accounts will use.
        request.basedOn = (request.basedOn or "").strip().upper()
        if request.basedOn not in STAFF_ROLES:
            return self.reject("Please choose User Admin or Platform Manager.")
        return True


class ViewUserProfileController(Controller):
    """US48 View User Profile."""

    # Sets up the controller with the user profiles.
    def __init__(self):
        self.model = UserProfiles()

    # US48: returns one profile and how many accounts use it.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.find(request)

    # Checks the profile ID is a whole number.
    def validateRequest(self, request):
        if to_positive_int(request.profileId) is None:
            return self.reject("Invalid profile ID.")
        request.profileId = int(request.profileId)
        return True


class UpdateUserProfileController(Controller):
    """US49 Update the description while retaining the profile's role identity."""

    # Sets up the controller with the user profiles.
    def __init__(self):
        self.model = UserProfiles()

    # US49: saves a profile's new description (the role name stays).
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.update(request)

    # Checks the profile ID and that the description is filled in.
    def validateRequest(self, request):
        if to_positive_int(request.profileId) is None:
            return self.reject("Invalid profile ID.")
        if is_blank(request.description):
            return self.reject("Please enter a description.")
        if len(request.description or "") > 500:
            return self.reject("Description must be 500 characters or fewer.")
        request.profileId = int(request.profileId)
        return True


class SuspendUserProfileController(ViewUserProfileController):
    """US50 Suspend User Profile (all accounts under the role are blocked from logging in)."""

    # US50: suspends a custom profile (not built-in ones or the admin's own).
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        # US50: the acting account ID comes from the validated session, to protect the admin's own profile.
        if to_positive_int(request.actorAccountId) is None:
            return self.sessionExpiredResult()
        return self.model.suspend(request)


class ReactivateUserProfileController(ViewUserProfileController):
    """US61 Reactivate User Profile (8 November): accounts with the profile can log in again."""

    # US61: makes a suspended profile active again.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.reactivate(request)


class SearchUserProfileController(Controller):
    """US51 Search User Profiles."""

    # Sets up the controller with the user profiles.
    def __init__(self):
        self.model = UserProfiles()

    # US51: lists all profiles, or those whose name or description matches.
    def execute(self, request=None):
        if request is None:
            profiles = self.model.listAll()
            return Result.succeed("FOUND", plural(len(profiles), "profile"), profiles)
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.search(request)

    # Checks a keyword was entered.
    def validateRequest(self, request):
        if is_blank(request.keyword):
            return self.reject("Please enter a keyword.")
        return True
