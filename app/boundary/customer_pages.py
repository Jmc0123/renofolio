"""Boundary classes for US13-US22 and US32-US33 (Customer side)."""
from dataclasses import replace

from flask import redirect, url_for, flash, jsonify

from app.boundary.ui import (render, current_session_id, handle_expired, show_result, end_login_session,
                             list_position, CUSTOMER_LIST_KEYS)
from app.common.request_types import (BrowseIDPsRequest, SearchIDPsRequest, FilterByCategoryRequest,
                                      FilterByStatusRequest, FilterByBudgetRequest, IDPIdRequest, FavouriteRequest,
                                      SessionRequest, SearchFavouritesRequest, DesignerIdRequest)
from app.common.request_types import ProjectFiltersRequest
from app.control.browse_controllers import (BrowseIDPsController, SearchIDPsController, FilterIDPsByCategoryController,
                                            FilterIDPsByStatusController, FilterIDPsByBudgetController,
                                            ViewIDPDetailsController)
from app.control.browse_controllers import SearchAndFilterIDPsController
from app.control.designer_controllers import ViewDesignerPortfolioController, ViewDesignerCompanyInfoController
from app.control.favourite_controllers import (SaveFavouriteController, ViewFavouritesController,
                                               SearchFavouritesController, RemoveFavouriteController)
from app.control.platform_controllers import ViewCategoriesController
from app.entity.database import CUSTOMER


class ProjectFiltersPanel:
    """Shared customer list Boundary for all optional filters and legacy list URLs."""

    # Sets up the project list with the controller that combines search and filters.
    def __init__(self):
        self.controller = SearchAndFilterIDPsController()

    # US13-US17: shows one page of projects matching every filled-in filter, with page links.
    def requestList(self, request):
        # Keep raw values for form redisplay, including zero and invalid input.
        fields = ("keyword", "categoryId", "status", "minBudget", "maxBudget")
        filters = {key: getattr(request, key) if getattr(request, key) is not None else "" for key in fields}
        result = self.controller.execute(request)
        if result.code == "CATEGORY_NOT_FOUND":
            flash(result.message, "error")
            filters["categoryId"] = ""
            request = replace(request, categoryId=None, page=1, mode="browse")
            result = self.controller.execute(request)
        if not result.ok:
            flash(result.message, "error")
        categories = ViewCategoriesController().execute().data or []
        # Filters in use (blanks dropped) for page links, and the list position for project links.
        active = list_position(filters, CUSTOMER_LIST_KEYS)
        position = dict(active)
        if result.ok and result.data and result.data.get("page", 1) > 1:
            position["page"] = str(result.data["page"])
        return render("customer/projects.html", result=result, filters=filters, categories=categories,
                      active_filters=active, position=position)


class _ProjectListPanel:
    """All five list panels share one page (projects.html) with the search bar and filters."""
    controller_class = None
    mode = "browse"

    # Sets up a single-filter list panel with its own controller.
    def __init__(self):
        self.controller = self.controller_class()

    # Shows the project list page for a single-filter result, with any error.
    def displayResult(self, result, filters):
        if not result.ok:
            flash(result.message, "error")
        categories = ViewCategoriesController().execute().data or []
        return render("customer/projects.html", result=result, mode=self.mode, filters=filters,
                      categories=categories)


class BrowseIDPsPanel(_ProjectListPanel):
    controller_class, mode = BrowseIDPsController, "browse"

    # US13: shows one page of all projects, newest first.
    def requestList(self, page):
        return self.displayResult(self.controller.execute(BrowseIDPsRequest(page)), {"page": page})


class SearchIDPsPanel(_ProjectListPanel):
    controller_class, mode = SearchIDPsController, "search"

    # US14: shows projects whose title or description contains the keyword.
    def submitSearch(self, keyword, page):
        return self.displayResult(self.controller.execute(SearchIDPsRequest(keyword, page)),
                                  {"keyword": keyword, "page": page})


class FilterIDPsByCategoryPanel(_ProjectListPanel):
    controller_class, mode = FilterIDPsByCategoryController, "category"

    # US15: shows projects in the chosen category.
    def applyFilter(self, categoryId, page):
        result = self.controller.execute(FilterByCategoryRequest(categoryId, page))
        if result.code == "CATEGORY_NOT_FOUND":
            # UC15 A1: retain the full list when a category has disappeared.
            flash(result.message, "error")
            self.mode = "browse"
            return self.displayResult(BrowseIDPsController().execute(BrowseIDPsRequest(1)), {"page": 1})
        return self.displayResult(result, {"categoryId": categoryId, "page": page})


class FilterIDPsByStatusPanel(_ProjectListPanel):
    controller_class, mode = FilterIDPsByStatusController, "status"

    # US16: shows Current or Past projects.
    def applyFilter(self, status, page):
        return self.displayResult(self.controller.execute(FilterByStatusRequest(status, page)),
                                  {"status": status, "page": page})


class FilterIDPsByBudgetPanel(_ProjectListPanel):
    controller_class, mode = FilterIDPsByBudgetController, "budget"

    # US17: shows projects whose budget is inside the range.
    def applyFilter(self, minBudget, maxBudget, page):
        return self.displayResult(self.controller.execute(FilterByBudgetRequest(minBudget, maxBudget, page)),
                                  {"minBudget": minBudget, "maxBudget": maxBudget, "page": page})


class ViewIDPDetailsPanel:
    """US18 details page, also hosts the Save to Favourites action (US19)."""

    # Sets up the project page with the details and save-to-favourites controllers.
    def __init__(self):
        self.controller = ViewIDPDetailsController()
        self.saveController = SaveFavouriteController()

    # Builds the Back link from the safe browse or matcher query parameters.
    def _backUrl(self, back):
        if "fromBrief" in back:
            answers = {key: value for key, value in back.items() if key != "fromBrief"}
            return url_for("customer_renovation_brief", _anchor="matches", **answers)
        return url_for("customer_projects", **back)

    # US18: shows one project's details and records the view.
    def requestDetails(self, idpId, back=None):
        """back: the browse filters or questionnaire answers the Customer came from."""
        back = back or {}
        result = self.controller.execute(IDPIdRequest(idpId, current_session_id()))
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        if not result.ok:
            flash(result.message, "error")
            return redirect(self._backUrl(back))
        return render("customer/project_detail.html", project=result.data, back=back, back_url=self._backUrl(back))

    # US19: saves the project to favourites and keeps the Customer on the same page.
    def saveToFavourites(self, idpId, background=False, back=None):
        """US19: the Customer stays on the project page and sees the message there.

        The page's script sends the save in the background (background=True) and shows the returned
        message in place, so the details page is not reloaded and no extra view is recorded (US18).
        Without JavaScript the form posts normally and the browser is sent back to the same project.
        """
        result = self.saveController.execute(FavouriteRequest(current_session_id(), idpId))
        if background:
            return self.displaySaveResult(result)
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        flash(result.message, "success" if result.ok else ("info" if result.code == "ALREADY_SAVED" else "error"))
        back = back or {}
        if result.ok or result.code == "ALREADY_SAVED":
            return redirect(url_for("customer_project_detail", idp_id=idpId, **back))
        return redirect(self._backUrl(back))

    # Returns the save outcome as JSON for the in-page message.
    def displaySaveResult(self, result):
        """Message for the in-page banner; isSaved tells the page to show 'In your favourites'."""
        body = {"ok": result.ok, "code": result.code, "message": result.message,
                "isSaved": result.ok or result.code == "ALREADY_SAVED",
                "favouritesUrl": url_for("customer_favourites")}
        if result.code in ("SESSION_EXPIRED", "SUSPENDED", "FORBIDDEN"):
            end_login_session()
            flash(result.message, "error")
            body["loginUrl"] = url_for("customer_login")
            return jsonify(body), 401
        return jsonify(body)


class ViewFavouritesPanel:
    # Sets up the panel with the controller that lists favourites.
    def __init__(self):
        self.controller = ViewFavouritesController()

    # US20: shows the Customer's saved projects.
    def requestFavourites(self):
        result = self.controller.execute(SessionRequest(current_session_id()))
        return handle_expired(result, CUSTOMER) or render("customer/favourites.html", result=result, keyword="")


class SearchFavouritesPanel:
    # Sets up the panel with the controller that searches favourites.
    def __init__(self):
        self.controller = SearchFavouritesController()

    # US21: shows saved projects whose title or description contains the keyword.
    def submitSearch(self, keyword):
        result = self.controller.execute(SearchFavouritesRequest(current_session_id(), keyword))
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        if not result.ok:
            flash(result.message, "error")
            return redirect(url_for("customer_favourites"))
        return render("customer/favourites.html", result=result, keyword=keyword)


class RemoveFavouriteDialog:
    # Sets up the dialog with the controller that removes favourites.
    def __init__(self):
        self.controller = RemoveFavouriteController()

    # US22: asks the Customer to confirm removing the project from favourites.
    def askConfirmation(self, idpId, title):
        return render("shared/confirm.html", heading="Remove from Favourites?",
                      message=f"'{title}' will be removed from My Favourites.", confirm_label="Remove",
                      action=url_for("customer_favourite_remove", idp_id=idpId),
                      cancel=url_for("customer_favourites"), danger=True)

    # US22: removes the favourite after the Customer confirms and shows the outcome.
    def confirmRemove(self, idpId):
        result = self.controller.execute(FavouriteRequest(current_session_id(), idpId, confirmed=True))
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        show_result(result)
        return redirect(url_for("customer_favourites"))


class DesignerPortfolioPanel:
    """US32 View Designer Portfolio: current and past projects, with a Company Information button."""

    # Sets up the panel with the controller that reads a designer's portfolio.
    def __init__(self):
        self.controller = ViewDesignerPortfolioController()

    # US32: asks for a designer's current and past projects.
    def requestPortfolio(self, request):
        return self.displayResult(self.controller.execute(request))

    # Shows the portfolio page, or returns to the project list if the designer is unavailable.
    def displayResult(self, result):
        if not result.ok:
            flash(result.message, "error")
            return redirect(url_for("customer_projects"))
        return render("customer/designer.html", result=result, portfolio=result.data)


class DesignerCompanyInfoPanel:
    """US33 View Designer Company Information, with Back to Portfolio."""

    # Sets up the panel with the controller that reads a designer's company information.
    def __init__(self):
        self.controller = ViewDesignerCompanyInfoController()

    # US33: asks for a designer's company information.
    def requestCompanyInfo(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the company page (or its 'not added yet' message), or returns to the list on a bad ID.
    def displayResult(self, result, request):
        if result.code == "INVALID_INPUT":
            flash(result.message, "error")
            return redirect(url_for("customer_projects"))
        return render("customer/designer_company.html", result=result, designerId=request.designerId)
