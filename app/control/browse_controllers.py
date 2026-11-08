"""US13-US18 - Customer browses, searches, filters and views Interior Design Projects."""
from app.common.validators import (is_blank, to_positive_int, to_non_negative_number, round_budget,
                                   PROJECT_STATUSES, MAX_BUDGET, BUDGET_RANGE_MESSAGE)
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.database import CUSTOMER
from app.entity.favourites import Favourites
from app.entity.interior_design_projects import InteriorDesignProjects
from app.entity.project_views import ProjectViews


class _ProjectListController(Controller):
    # Sets up the controller with the projects collection.
    def __init__(self):
        self.model = InteriorDesignProjects()

    # Checks the page number is a whole number of 1 or more (blank means 1).
    def validatePage(self, request):
        page = to_positive_int(request.page if request.page not in (None, "") else 1)
        if page is None:
            return self.reject("Invalid page number.")
        request.page = page
        return True


class SearchAndFilterIDPsController(_ProjectListController):
    """US13-US17 together: blank criteria are optional; provided criteria intersect."""

    # US13-US17: returns one page of projects matching every filled-in filter.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.searchAndFilter(request)

    # Checks the keyword, category, status, budget range and page together.
    def validateRequest(self, request):
        request.keyword = (request.keyword or "").strip()
        if request.mode == "search" and not request.keyword:
            return self.reject("Please enter a keyword.")
        if len(request.keyword) > 100:
            return self.reject("Keyword must be 100 characters or fewer.")
        if not is_blank(request.categoryId):
            request.categoryId = to_positive_int(request.categoryId)
            if request.categoryId is None or request.categoryId > 9223372036854775807:
                return self.reject("Please choose a valid category.")
        elif request.mode == "category":
            return self.reject("Please choose a category.")
        else:
            request.categoryId = None
        request.status = (request.status or "").strip().upper()
        if (request.status or request.mode == "status") and request.status not in PROJECT_STATUSES:
            return self.reject("Status must be Current or Past.")
        has_budget = not is_blank(request.minBudget) or not is_blank(request.maxBudget)
        if has_budget or request.mode == "budget":
            low = to_non_negative_number(request.minBudget)
            high = to_non_negative_number(request.maxBudget)
            if low is None or high is None:
                return self.reject("Please enter a minimum and maximum budget of 0 or more.")
            if high > MAX_BUDGET:
                return self.reject(BUDGET_RANGE_MESSAGE)
            if low > high:
                return self.reject("Minimum budget cannot be higher than maximum.")
            request.minBudget, request.maxBudget = round_budget(low), round_budget(high)
        else:
            request.minBudget = request.maxBudget = None
        if not self.validatePage(request):
            return False
        if request.page > 2147483647:
            return self.reject("Invalid page number.")
        return True


class BrowseIDPsController(_ProjectListController):
    """US13 Browse IDPs using the customer project page size."""

    # US13: returns one page of all visible projects, newest first.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.browse(request)

    # Checks the page number.
    def validateRequest(self, request):
        return self.validatePage(request)


class SearchIDPsController(_ProjectListController):
    """US14 Search IDPs by keyword (title or description, case-insensitive)."""

    # US14: returns projects whose title or description contains the keyword.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.search(request)

    # Checks a keyword of up to 100 characters and the page number.
    def validateRequest(self, request):
        if is_blank(request.keyword):
            return self.reject("Please enter a keyword.")
        if len(request.keyword.strip()) > 100:
            return self.reject("Keyword must be 100 characters or fewer.")
        return self.validatePage(request)


class FilterIDPsByCategoryController(_ProjectListController):
    """US15 Filter IDPs by category."""

    # US15: returns projects in one category.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.filterByCategory(request)

    # Checks the category exists and the page number.
    def validateRequest(self, request):
        category_id = to_positive_int(request.categoryId)
        if category_id is None:
            return self.reject("Please choose a category.")
        request.categoryId = category_id
        return self.validatePage(request)


class FilterIDPsByStatusController(_ProjectListController):
    """US16 Filter IDPs by Current or Past status."""

    # US16: returns Current or Past projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.filterByStatus(request)

    # Checks the status is Current or Past and the page number.
    def validateRequest(self, request):
        if (request.status or "").strip().upper() not in PROJECT_STATUSES:
            return self.reject("Status must be Current or Past.")
        request.status = request.status.strip().upper()
        return self.validatePage(request)


class FilterIDPsByBudgetController(_ProjectListController):
    """US17 Filter IDPs by budget range (S$)."""

    # US17: returns projects with a budget inside the range.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.filterByBudget(request)

    # Checks both budget bounds (S$0 to S$10,000,000, minimum not above maximum).
    def validateRequest(self, request):
        low, high = to_non_negative_number(request.minBudget), to_non_negative_number(request.maxBudget)
        if low is None or high is None:
            return self.reject("Please enter a minimum and maximum budget of 0 or more.")
        if high > MAX_BUDGET:
            return self.reject(BUDGET_RANGE_MESSAGE)
        if low > high:
            return self.reject("Minimum budget cannot be higher than maximum.")
        request.minBudget, request.maxBudget = round_budget(low), round_budget(high)
        return self.validatePage(request)


class ViewIDPDetailsController(Controller):
    """US18 View IDP details. Each successful opening records exactly one view."""

    # Sets up the controller with projects, project views and the access guard.
    def __init__(self):
        self.model = InteriorDesignProjects()
        self.views = ProjectViews()
        self.accessGuard = AccessGuardController()
        self.favourites = Favourites()

    # US18: returns one visible project and records that the Customer viewed it.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        result = self.model.find(request)
        if not result.ok:
            return result
        customer_id = access.data["accountId"]
        self.views.recordView(request.idpId, customer_id)
        result.data["isSaved"] = self.favourites.isSaved(customer_id, request.idpId)
        return result

    # Checks the project ID is a whole number.
    def validateRequest(self, request):
        idp_id = to_positive_int(request.idpId)
        if idp_id is None:
            return self.reject("Invalid project ID.")
        request.idpId = idp_id
        return True
