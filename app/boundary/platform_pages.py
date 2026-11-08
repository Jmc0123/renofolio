"""Boundary classes for US52-US59 (Platform Manager: categories and reports)."""
from flask import redirect, url_for, flash

from app.boundary.ui import render, show_result, paginate
from app.common.request_types import CategoryRequest, SearchCategoriesRequest, ReportRequest
from app.control.platform_controllers import (ViewCategoriesController, CreateCategoryController,
                                              UpdateCategoryController, RemoveCategoryController,
                                              SearchCategoriesController, GenerateDailyReportController,
                                              GenerateWeeklyReportController, GenerateMonthlyReportController)


class CategoryManagementPanel:
    """US52 category list and US56 search."""

    # Sets up the panel with the controllers that list and search categories.
    def __init__(self):
        self.controller = ViewCategoriesController()
        self.searchController = SearchCategoriesController()

    # US52/US56: shows all categories or the search results, 20 per page.
    def requestCategories(self, keyword=None, page=None):
        if keyword is not None:
            result = self.searchController.execute(SearchCategoriesRequest(keyword))
            if not result.ok:
                flash(result.message, "error")
        else:
            result = self.controller.execute()
        rows, pager, error = paginate(result.data or [], page)
        if error:
            flash(error, "error")
        params = {"keyword": keyword} if keyword else {}
        return render("pm/categories.html", result=result, rows=rows, pager=pager, params=params,
                      keyword=keyword or "")


class CreateCategoryForm:
    """US53 create a category using the same name field as the edit form."""

    # US53: shows the Create Category form.
    def show(self, name=""):
        return render("pm/category_form.html", name=name, creating=True)

    # US53: creates the category and returns to the list, or shows the form again with the error.
    def submit(self, name):
        result = CreateCategoryController().execute(CategoryRequest(name=name))
        show_result(result)
        return redirect(url_for("pm_categories")) if result.ok else self.show(name)


class UpdateCategoryForm:
    """US54"""

    # Sets up the form with the controller that renames categories.
    def __init__(self):
        self.controller = UpdateCategoryController()

    # US54: shows the edit form with the category's current name.
    def show(self, categoryId, name=None):
        current = next((c for c in ViewCategoriesController().execute().data or [] if c.categoryId == categoryId), None)
        if current is None:
            flash("This category no longer exists.", "error")
            return redirect(url_for("pm_categories"))
        return render("pm/category_form.html", creating=False, name=name if name is not None else current.name)

    # US54: saves the new name and returns to the list, or shows the form again with the error.
    def submit(self, categoryId, name):
        result = self.controller.execute(CategoryRequest(categoryId, name))
        if result.ok:
            flash(result.message, "success")
            return redirect(url_for("pm_categories"))
        flash(result.message, "error")
        return self.show(categoryId, name)


class RemoveCategoryDialog:
    """US55"""

    # Sets up the dialog with the controller that removes categories.
    def __init__(self):
        self.controller = RemoveCategoryController()

    # US55: asks the Platform Manager to confirm removing the category.
    def askConfirmation(self, categoryId):
        current = next((c for c in ViewCategoriesController().execute().data or [] if c.categoryId == categoryId), None)
        if current is None:
            flash("This category no longer exists.", "error")
            return redirect(url_for("pm_categories"))
        return render("shared/confirm.html", heading="Remove This Category?",
                      message=f"Remove '{current.name}'? A category can only be removed when no project uses it.",
                      confirm_label="Remove", action=url_for("pm_category_remove", category_id=categoryId),
                      cancel=url_for("pm_categories"), danger=True)

    # US55: removes the category if no project uses it, then shows the outcome.
    def confirm(self, categoryId):
        show_result(self.controller.execute(CategoryRequest(categoryId=categoryId)))
        return redirect(url_for("pm_categories"))


class ReportPanel:
    """US57 daily, US58 weekly, US59 monthly report."""
    controllers = {"DAY": GenerateDailyReportController, "WEEK": GenerateWeeklyReportController,
                   "MONTH": GenerateMonthlyReportController}

    # US57-US59: shows the report page and, after Generate Report, the four activity counts.
    def requestReport(self, periodType, periodValue):
        periodType = (periodType or "DAY").strip().upper()
        report = None
        if periodType not in self.controllers:
            flash("Choose Daily, Weekly or Monthly.", "error")
            periodType = "DAY"
        elif periodValue is not None:
            # Loading a tab leaves the form empty. An empty Generate submission shows the use case error.
            controller = self.controllers[periodType]()
            result = controller.execute(ReportRequest(periodValue))
            if result.ok:
                report = result.data
            else:
                flash(result.message, "error")
        return render("pm/reports.html", report=report, periodType=periodType, periodValue=periodValue or "")
