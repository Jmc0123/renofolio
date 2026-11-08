"""US23-US33 - Interior Designer company information and portfolio, and the Customer's view of them.

Names and steps follow the US23-US33 B-C-E and sequence diagrams (SoftwareAss.docx, 6 November).
Designer controllers find the designer from the session through the shared access guard, which also
checks the account/profile status and the Interior Designer role, so a Customer session cannot use
them even when a controller is called directly. Every read or change is limited to the designer's
own records (ownership). US32/US33 are Customer pages and take a designerId instead.
"""
import re

from app.common.result import Result
from app.common.validators import (is_blank, valid_email, valid_contact, to_positive_int,
                                   to_non_negative_number, round_budget, PROJECT_STATUSES, MAX_BUDGET,
                                   BUDGET_RANGE_MESSAGE)
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.companies import Companies
from app.entity.database import INTERIOR_DESIGNER
from app.entity.interior_design_projects import InteriorDesignProjects
from app.entity.project_categories import ProjectCategories
from app.entity.user_accounts import UserAccounts

WEBSITE_RE = re.compile(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", re.IGNORECASE)
LOCAL_PHOTO_PREFIXES = ("/static/uploads/", "/static/sample-projects/")


class _DesignerController(Controller):
    """Shared session step: 'The system identifies the Interior Designer from the session.'"""

    # Sets up the shared access guard for designer controllers.
    def __init__(self):
        self.sessions = AccessGuardController()

    # Returns the logged-in designer's ID, or the failure if the session ended or the role is wrong.
    def designerFromSession(self, request):
        """Returns (designerId, None) or (None, failed Result such as SESSION_EXPIRED)."""
        access = self.sessions.execute(request, INTERIOR_DESIGNER)
        if not access.ok:
            return None, access
        return access.data["accountId"], None


# ================================================================== company information (US23-US25)
class _CompanyFormController(_DesignerController):
    # Sets up the controller with the companies collection.
    def __init__(self):
        super().__init__()
        self.companies = Companies()

    # Checks company name, contact email and contact number are filled in and valid.
    def validateRequest(self, request):
        """US23/US25 step 3: company name, contact email and contact number are filled in and well formed."""
        if any(is_blank(v) for v in (request.companyName, request.contactEmail, request.contactNumber)):
            return self.reject("Please enter the company name, contact email and contact number.")
        if len(request.companyName.strip()) > 120:
            return self.reject("Company name must be 120 characters or fewer.")
        if not valid_email(request.contactEmail):
            return self.reject("Please enter a valid contact email.")
        if not valid_contact(request.contactNumber):
            return self.reject("Please enter a valid contact number (8-15 digits, an optional + is allowed).")
        if len(request.description or "") > 2000 or len(request.address or "") > 200:
            return self.reject("Description must be 2000 characters or fewer, and address 200 or fewer.")
        if not is_blank(request.website) and not WEBSITE_RE.match(request.website.strip()):
            return self.reject("Please enter a valid website, for example studiolim.sg.")
        return True


class CreateCompanyInfoController(_CompanyFormController):
    """US23 Create Company Information."""

    # US23: saves the designer's company information (only one record per designer).
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        if self.companies.hasCompany(designer_id):
            return self.companyExistsResult()
        return self.companies.create(designer_id, request)

    # The failure when the designer already has company information.
    def companyExistsResult(self):
        return Result.fail("COMPANY_EXISTS", "Company information already exists. Use Edit instead.")


class ViewCompanyInfoController(_DesignerController):
    """US24 View Company Information."""

    # Sets up the controller with the companies collection.
    def __init__(self):
        super().__init__()
        self.companies = Companies()

    # US24: returns the logged-in designer's company information.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        result = self.companies.findByDesigner(designer_id)
        if not result.ok:
            return Result.fail("NO_COMPANY", "You have not added company information yet.")
        return result

    # Checks a request was given.
    def validateRequest(self, request):
        return True if request is not None else self.reject("Invalid request.")


class UpdateCompanyInfoController(_CompanyFormController):
    """US25 Update Company Information."""

    # US25: saves the changed company information.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        return self.companies.update(designer_id, request)


# ================================================================== portfolio (US26-US31)
class _ProjectController(_DesignerController):
    # Sets up the controller with the projects collection.
    def __init__(self):
        super().__init__()
        self.projects = InteriorDesignProjects()

    # The failure when the project is not one of the designer's own.
    def notOwnerResult(self):
        return Result.fail("NOT_OWNER", "This project is no longer available.")

    # Checks the project ID is a whole number.
    def validateIdpId(self, request):
        idp_id = to_positive_int(request.idpId)
        if idp_id is None:
            return self.reject("Invalid project ID.")
        request.idpId = idp_id
        return True


class _ProjectFormController(_ProjectController):
    # Sets up the controller with projects, categories and companies.
    def __init__(self):
        super().__init__()
        self.categories = ProjectCategories()
        self.companies = Companies()

    # Checks title, description, category, status, budget (S$0-10,000,000) and photo.
    def validateRequest(self, request):
        """Validate Project Details: title, category and status given; budget a number from 0 to 10,000,000."""
        if is_blank(request.title):
            return self.reject("Please enter a title.")
        if len(request.title.strip()) > 120:
            return self.reject("Title must be 120 characters or fewer.")
        if len(request.description or "") > 2000:
            return self.reject("Description must be 2000 characters or fewer.")
        category_id = to_positive_int(request.categoryId)
        if category_id is None or not self.categories.exists(category_id):
            return self.reject("Please choose a category.")
        if (request.projectStatus or "").strip().upper() not in PROJECT_STATUSES:
            return self.reject("Please choose Current or Past.")
        # Bugs 6 and 7 (8 November): a blank budget asks for one; otherwise it must be S$0 to S$10,000,000.
        if is_blank(request.budget):
            return self.reject("Please enter a budget.")
        budget = to_non_negative_number(request.budget)
        if budget is None or budget > MAX_BUDGET:
            return self.reject(BUDGET_RANGE_MESSAGE)
        photo = (request.photoUrl or "").strip()
        if photo and not (photo.lower().startswith(("http://", "https://")) or photo.startswith(LOCAL_PHOTO_PREFIXES)):
            return self.reject("The photo could not be used. Please choose a JPG, PNG or WebP image.")
        request.categoryId, request.budget = category_id, round_budget(budget)
        request.projectStatus = request.projectStatus.strip().upper()
        return True


class CreateIDPController(_ProjectFormController):
    """US26 Create IDP."""

    # US26: creates a project for a designer who has company information.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        # Bug 5 (8 November): every project needs a company behind it, so customers can see who made it (US33).
        if not self.companies.hasCompany(designer_id):
            return self.noCompanyResult()
        return self.projects.create(designer_id, request)

    # The failure asking the designer to add company information first.
    def noCompanyResult(self):
        return Result.fail("NO_COMPANY", "Please add your company information before creating a project.")


class ViewMyIDPsController(_ProjectController):
    """US27 View My IDPs. Without idpId: the designer's projects; with idpId: that project's details."""

    # US27: returns the designer's projects, or one of them when an ID is given.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        if request.idpId is not None:
            return self.projects.findOwned(designer_id, request.idpId)  # A2: "This project is not available."
        result = self.projects.findByDesigner(designer_id)
        count = len(result.data)
        if count == 0:
            return Result.succeed("EMPTY", "You have not created any projects yet.", [])
        return Result.succeed("FOUND", f"{count} project{'s' if count != 1 else ''}", result.data)

    # Allows no project ID (the list) or checks the given one.
    def validateRequest(self, request):
        if request.idpId in (None, ""):
            request.idpId = None
            return True
        return self.validateIdpId(request)


class FilterMyIDPsController(_ProjectController):
    """US28 Filter My IDPs by Current or Past Status."""

    # US28: returns the designer's Current or Past projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        items = self.projects.filterMineByStatus(designer_id, request.status).data
        word = request.status.lower()
        if not items:
            return Result.succeed("EMPTY", f"You have no {word} projects yet.", [])
        return Result.succeed("FOUND", f"{len(items)} {word} project{'s' if len(items) != 1 else ''}", items)

    # Checks the status is Current or Past.
    def validateRequest(self, request):
        status = (request.status or "").strip().upper()
        if status not in PROJECT_STATUSES:
            return self.reject("Please choose Current or Past.")
        request.status = status
        return True


class UpdateIDPController(_ProjectFormController):
    """US29 Update IDP (including Current -> Past). Only the owner can update."""

    # US29: saves changes to one of the designer's own projects.
    def execute(self, request):
        if not (self.validateIdpId(request) and self.validateRequest(request)):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        if not self.projects.isOwner(designer_id, request.idpId):
            return self.notOwnerResult()
        return self.projects.update(request)


class DeleteIDPController(_ProjectController):
    """US30 Delete IDP: the project, its views and its favourites are deleted together."""

    # US30: deletes one of the designer's projects after confirmation.
    def execute(self, request):
        if not request.confirmed:  # A1: the designer cancels; nothing changes
            return Result.fail("CANCELLED", "Nothing was deleted.")
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        if not self.projects.isOwner(designer_id, request.idpId):
            return self.notOwnerResult()
        return self.projects.delete(request.idpId)

    # Checks the project ID.
    def validateRequest(self, request):
        return self.validateIdpId(request)


class SearchMyIDPsController(_ProjectController):
    """US31 Search My IDPs by keyword (title or description, ignoring case)."""

    # US31: returns the designer's projects matching a keyword.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        keyword = request.keyword.strip()
        items = self.projects.searchMine(designer_id, keyword).data
        if not items:
            return Result.succeed("EMPTY", f"None of your projects match '{keyword}'.", [])
        noun = "project matches" if len(items) == 1 else "projects match"
        return Result.succeed("FOUND", f"{len(items)} {noun} '{keyword}'", items)

    # Checks a keyword of up to 100 characters.
    def validateRequest(self, request):
        if is_blank(request.keyword):
            return self.reject("Please enter a keyword.")
        if len(request.keyword.strip()) > 100:
            return self.reject("Keyword must be 100 characters or fewer.")
        return True


class SearchAndFilterMyIDPsController(_ProjectController):
    """US28 + US31 used together on My Interior Design Projects: keyword AND Current/Past status.

    The single-criterion stories keep their own controllers (FilterMyIDPsController,
    SearchMyIDPsController); this one is used only when both a keyword and a status are given.
    """

    # US28 + US31: returns the designer's projects matching both a keyword and a status.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        items = self.projects.searchAndFilterMine(designer_id, request.keyword, request.status).data
        word = request.status.lower()
        if not items:
            return Result.succeed("EMPTY", f"None of your {word} projects match '{request.keyword}'.", [])
        noun = f"{word} project matches" if len(items) == 1 else f"{word} projects match"
        return Result.succeed("FOUND", f"{len(items)} {noun} '{request.keyword}'", items)

    # Checks both the keyword and the status.
    def validateRequest(self, request):
        keyword, status = (request.keyword or "").strip(), (request.status or "").strip().upper()
        if not keyword:
            return self.reject("Please enter a keyword.")
        if len(keyword) > 100:
            return self.reject("Keyword must be 100 characters or fewer.")
        if status not in PROJECT_STATUSES:
            return self.reject("Please choose Current or Past.")
        request.keyword, request.status = keyword, status
        return True


# ================================================================== Customer views a designer (US32, US33)
class _PublicDesignerController(Controller):
    # Sets up the controller with the user accounts.
    def __init__(self):
        self.accounts = UserAccounts()

    # Checks the designer ID is a whole number.
    def validateRequest(self, request):
        designer_id = to_positive_int(request.designerId)
        if designer_id is None:
            return self.reject("Invalid designer ID.")
        request.designerId = designer_id
        return True

    # Returns the designer's account if it is an active Interior Designer, otherwise None.
    def activeDesigner(self, designerId):
        account = self.accounts.getById(designerId)
        if (account is None or account.roleCode != INTERIOR_DESIGNER or account.status != "ACTIVE"
                or account.profileStatus != "ACTIVE"):
            return None
        return account

    # The failure when the designer cannot be shown.
    def unavailableResult(self):
        return Result.fail("INVALID_INPUT", "This designer is not available.")


class ViewDesignerPortfolioController(_PublicDesignerController):
    """US32 View Designer Portfolio. Nothing is recorded; views count only in US18."""

    # Sets up the controller with the projects collection.
    def __init__(self):
        super().__init__()
        self.projects = InteriorDesignProjects()

    # US32: returns a designer's current and past projects for Customers.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer = self.activeDesigner(request.designerId)
        if designer is None:
            return self.unavailableResult()
        projects = self.projects.findByDesigner(designer.accountId).data
        data = {"designer": {"accountId": designer.accountId, "name": designer.name,
                             "companyName": next((p["companyName"] for p in projects if p["companyName"]), "")},
                "current": [p for p in projects if p["projectStatus"] == "CURRENT"],
                "past": [p for p in projects if p["projectStatus"] == "PAST"]}
        if not projects:
            return Result.succeed("EMPTY", "This designer has no projects yet.", data)
        return Result.succeed("FOUND", "", data)


class ViewDesignerCompanyInfoController(_PublicDesignerController):
    """US33 View Designer Company Information."""

    # Sets up the controller with the companies collection.
    def __init__(self):
        super().__init__()
        self.companies = Companies()

    # US33: returns a designer's company information for Customers.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer = self.activeDesigner(request.designerId)
        if designer is None:
            return self.unavailableResult()
        result = self.companies.findByDesigner(designer.accountId)
        if not result.ok:
            return Result.fail("NO_COMPANY", "This designer has not added company information yet.",
                               {"designerId": designer.accountId, "designerName": designer.name})
        return result
