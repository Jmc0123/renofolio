"""Customer and Designer workflows for private project consultations."""
from app.common.request_types import IDPIdRequest
from app.common.result import Result
from app.common.validators import is_blank, to_positive_int
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.consultations import Consultations
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER
from app.entity.interior_design_projects import InteriorDesignProjects


class ConsultationController:
    # Reuses the existing login guard and project visibility rules.
    def __init__(self):
        self.accessGuard = AccessGuardController()
        self.model = Consultations()
        self.projects = InteriorDesignProjects()

    # Checks that the session belongs to a role that can participate in consultations.
    def _authorize(self, request, role):
        if role not in (CUSTOMER, INTERIOR_DESIGNER):
            return Result.fail("FORBIDDEN", "You do not have access to consultations.")
        return self.accessGuard.execute(request, role)

    # Opens the caller's inbox, an owned thread, or a draft for a visible project.
    def execute(self, request, role):
        access = self._authorize(request, role)
        if not access.ok:
            return access
        account_id = access.data["accountId"]
        if not is_blank(request.threadId):
            thread_id = to_positive_int(request.threadId)
            return self.model.viewThread(thread_id, account_id, role) if thread_id else self.model.unavailableResult()
        if role == CUSTOMER and not is_blank(request.projectId):
            project_id = to_positive_int(request.projectId)
            if project_id is None:
                return Result.fail("INVALID_PROJECT", "This project is no longer available.")
            thread_id = self.model.findForProject(account_id, project_id)
            if thread_id is not None:
                return self.model.viewThread(thread_id, account_id, role)
            project = self.projects.find(IDPIdRequest(project_id))
            return Result.succeed("DRAFT", data={"project": project.data}) if project.ok else project
        return self.model.listFor(account_id, role)

    # Validates the message and starts or continues an owned conversation.
    def send(self, request, role):
        access = self._authorize(request, role)
        if not access.ok:
            return access
        message = (request.message or "").strip()
        if not 1 <= len(message) <= 2000 or "\x00" in message:
            return Result.fail("INVALID_MESSAGE", "Enter a message of 1 to 2,000 characters.")
        account_id = access.data["accountId"]
        if not is_blank(request.threadId):
            thread_id = to_positive_int(request.threadId)
            return self.model.reply(thread_id, account_id, role, message) if thread_id else self.model.unavailableResult()
        project_id = to_positive_int(request.projectId)
        if role != CUSTOMER or project_id is None:
            return Result.fail("INVALID_PROJECT", "This project is no longer available.")
        return self.model.start(account_id, project_id, message)

    # Lets the owning designer close the thread.
    def close(self, request, role):
        access = self._authorize(request, role)
        if not access.ok:
            return access
        if role != INTERIOR_DESIGNER:
            return Result.fail("NOT_DESIGNER", "Only the designer can close this conversation.")
        thread_id = to_positive_int(request.threadId)
        if thread_id is None:
            return self.model.unavailableResult()
        return self.model.close(thread_id, access.data["accountId"])


class CountUnreadMessagesController(Controller):
    """US63/US64 (9 November): how many of the caller's conversations have messages they have not opened."""

    # Sets up the controller with the consultations.
    def __init__(self):
        self.model = Consultations()

    # Returns the number of conversations with unread messages for the Messages badge.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.countUnread(request.accountId, request.role)

    # Checks the account ID is a whole number and the role is one that has messages.
    def validateRequest(self, request):
        if to_positive_int(request.accountId) is None:
            return self.reject("Invalid account ID.")
        if request.role not in (CUSTOMER, INTERIOR_DESIGNER):
            return self.reject("Only customers and interior designers have messages.")
        request.accountId = int(request.accountId)
        return True
