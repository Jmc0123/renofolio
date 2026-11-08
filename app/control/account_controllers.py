"""US01, US03, US04, US06 - registration and personal details."""
from app.common.result import Result
from app.common.validators import is_blank, valid_email, valid_contact, MIN_PASSWORD_LENGTH
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER
from app.entity.user_accounts import UserAccounts


class _RegistrationController(Controller):
    role = None

    # Sets up the controller with the user accounts it creates.
    def __init__(self):
        self.model = UserAccounts()

    # US01/US06: checks the details and email, then creates the account for this role.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        if self.model.isEmailRegistered(request.email):
            return self.emailTakenResult()
        result = self.model.create(request, self.role)
        if result.ok:
            result.message = "Account created. You can now log in."
        return result

    # Checks every sign-up field is filled in and correctly formatted.
    def validateRequest(self, request):
        if any(is_blank(v) for v in (request.name, request.email, request.password, request.contactNumber)):
            return self.reject("Please fill in every field.")
        if len(request.name.strip()) > 100:
            return self.reject("Name must be 100 characters or fewer.")
        if not valid_email(request.email):
            return self.reject("Please enter a valid email address.")
        if len(request.password) < MIN_PASSWORD_LENGTH:
            return self.reject(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if not valid_contact(request.contactNumber):
            return self.reject("Contact number must be 8-15 digits (an optional + is allowed).")
        return True

    # The 'This email is already registered' failure.
    def emailTakenResult(self):
        return Result.fail("EMAIL_TAKEN", "This email is already registered")


class CreateCustomerAccountController(_RegistrationController):
    """US01 Create Customer Account."""
    role = CUSTOMER


class CreateDesignerAccountController(_RegistrationController):
    """US06 Create Interior Designer Account."""
    role = INTERIOR_DESIGNER


class ViewPersonalDetailsController(Controller):
    """US03 View Personal Details. The account comes from the session, never from the page."""

    # Sets up the controller with the accounts and the access guard.
    def __init__(self):
        self.model = UserAccounts()
        self.accessGuard = AccessGuardController()

    # US03: returns the logged-in Customer's own details.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        return self.model.findById(access.data["accountId"])

    # Checks a request was given.
    def validateRequest(self, request):
        return True if request is not None else self.reject("Invalid request.")


class UpdatePersonalDetailsController(Controller):
    """US04 Update Personal Details (name and contact number; email is read-only)."""

    # Sets up the controller with the accounts and the access guard.
    def __init__(self):
        self.model = UserAccounts()
        self.accessGuard = AccessGuardController()

    # US04: saves the logged-in Customer's new name and contact number.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        return self.model.updateDetails(access.data["accountId"], request.name, request.contactNumber)

    # Checks the name is filled in and short enough and the contact number is valid.
    def validateRequest(self, request):
        if is_blank(request.name):
            return self.reject("Name cannot be empty.")
        if len(request.name.strip()) > 100:
            return self.reject("Name must be 100 characters or fewer.")
        if not valid_contact(request.contactNumber):
            return self.reject("Contact number must be 8-15 digits (an optional + is allowed).")
        return True
