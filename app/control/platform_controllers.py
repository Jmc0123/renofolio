"""US52-US59 - Platform Manager manages IDP categories and generates reports."""
from app.common import clock
from app.common.result import Result
from app.common.text import plural
from app.common.validators import is_blank, to_positive_int
from app.control.base import Controller
from app.entity.platform_reports import PlatformReports
from app.entity.project_categories import ProjectCategories


# ------------------------------------------------------------------ categories
class _CategoryController(Controller):
    # Sets up the controller with the categories collection.
    def __init__(self):
        self.model = ProjectCategories()

    # Checks the category name is filled in and at most 50 characters.
    def validateName(self, request):
        name = (request.name or "").strip()
        if is_blank(name):
            return self.reject("Category name is required.")
        if len(name) > 50:
            return self.reject("Category name must be 50 characters or fewer.")
        return True

    # Checks the category ID is a whole number.
    def validateId(self, request):
        if to_positive_int(request.categoryId) is None:
            return self.reject("Invalid category ID.")
        request.categoryId = int(request.categoryId)
        return True


class ViewCategoriesController(_CategoryController):
    """US52 View Project Categories (with how many projects use each)."""

    # US52: returns every category with its visible project count, by name.
    def execute(self, request=None):
        items = self.model.listAll()
        if not items:
            return Result.succeed("EMPTY", "No categories yet. Create the first one.", [])
        return Result.succeed("FOUND", plural(len(items), "category"), items)


class CreateCategoryController(_CategoryController):
    """US53 Create a category with a non-empty, case-insensitively unique name."""

    # US53: creates a category with a new name.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.create(request.name)

    # Checks the name.
    def validateRequest(self, request):
        return self.validateName(request)


class UpdateCategoryController(_CategoryController):
    """US54 Update Project Category (rename; must stay unique)."""

    # US54: renames a category.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.update(request.categoryId, request.name)

    # Checks the category ID and the new name.
    def validateRequest(self, request):
        return self.validateId(request) and self.validateName(request)


class RemoveCategoryController(_CategoryController):
    """US55 Remove Project Category (only when no project uses it)."""

    # US55: removes a category that no project uses.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.remove(request.categoryId)

    # Checks the category ID.
    def validateRequest(self, request):
        return self.validateId(request)


class SearchCategoriesController(_CategoryController):
    """US56 Search Project Categories by name."""

    # US56: returns categories whose name contains the keyword.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        return self.model.search(request.keyword)

    # Checks a keyword was entered.
    def validateRequest(self, request):
        if is_blank(request.keyword):
            return self.reject("Please enter a keyword.")
        return True


# ------------------------------------------------------------------ reports
class _ReportController(Controller):
    periodType = None
    title = ""
    selection = ""

    # Sets up the controller with the platform reports entity.
    def __init__(self):
        self.model = PlatformReports()

    # US57-US59: counts the platform activity for the chosen day, week or month.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        start, end, label = self.bounds
        data = self.model.generate(start, end)
        data.update({"title": f"{self.title} - {label}", "periodType": self.periodType,
                     "periodValue": request.periodValue, "generatedAt": clock.now_text()})
        return Result.succeed("GENERATED", "", data)

    # Checks a date, week or month was chosen and is valid.
    def validateRequest(self, request):
        if is_blank(request.periodValue):
            return self.reject(f"Please select a {self.selection}.")
        bounds = clock.period_bounds(self.periodType, request.periodValue)
        if bounds is None:
            return self.reject(f"Please select a valid {self.selection}.")
        self.bounds = bounds
        return True


class GenerateDailyReportController(_ReportController):
    """US57"""
    periodType, title, selection = "DAY", "Daily Report", "date"


class GenerateWeeklyReportController(_ReportController):
    """US58"""
    periodType, title, selection = "WEEK", "Weekly Report", "week"


class GenerateMonthlyReportController(_ReportController):
    """US59"""
    periodType, title, selection = "MONTH", "Monthly Report", "month"
