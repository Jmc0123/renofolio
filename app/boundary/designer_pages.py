"""Boundary classes for US23-US31 and US34-US41 (Interior Designer pages).

Class and method names follow the US23-US41 B-C-E diagrams. Each boundary builds the request object,
calls only its Controller(s) and displays the Result. Photo files (US26/US29) are saved here, in the
Boundary, and only the resulting /static/uploads/... address is passed to the Controller.
"""
import logging
import os
import uuid
from io import BytesIO

from flask import redirect, url_for, flash
from PIL import Image

from app.boundary.ui import render, current_session_id, handle_expired
from app.common.request_types import (CompanyInfoRequest, UpdateCompanyInfoRequest, ViewCompanyInfoRequest,
                                      CreateIDPRequest, UpdateIDPRequest, ViewMyIDPsRequest, FilterMyIDPsRequest,
                                      DeleteIDPRequest, SearchMyIDPsRequest, MyIDPsFiltersRequest, ProjectStatRequest,
                                      InterestSummaryRequest, PeriodStatRequest, PortfolioTotalsRequest)
from app.common.result import Result
from app.control.designer_controllers import (CreateCompanyInfoController, ViewCompanyInfoController,
                                              UpdateCompanyInfoController, CreateIDPController, ViewMyIDPsController,
                                              FilterMyIDPsController, UpdateIDPController, DeleteIDPController,
                                              SearchMyIDPsController, SearchAndFilterMyIDPsController)
from app.control.interest_controllers import (ViewProjectViewCountController, ViewShortlistCountController,
                                              ViewInterestSummaryController, SortByViewCountController,
                                              SortByShortlistCountController, ViewPeriodViewsController,
                                              ViewPeriodSavesController, ViewPortfolioTotalsController)
from app.control.platform_controllers import ViewCategoriesController
from app.entity.database import INTERIOR_DESIGNER as ROLE

COMPANY_FIELDS = ("companyName", "description", "address", "contactEmail", "contactNumber", "website")
IDP_FIELDS = ("title", "description", "categoryId", "projectStatus", "budget")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "uploads", "idp")
MAX_PHOTO_BYTES = 5 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


# Sends the designer to the login page if the controller reports an ended session.
def _expired(result):
    return handle_expired(result, ROLE)


# Returns the logged-in designer's session ID.
def _sid():
    return current_session_id()


# Saves an uploaded project photo (JPG, PNG or WebP up to 5 MB) and returns its address or an error.
def save_photo(file_storage):
    """Store an uploaded JPG/PNG/WebP (max 5 MB) and return (photoUrl, error message)."""
    if file_storage is None or not file_storage.filename:
        return "", None
    data = file_storage.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        return "", "The photo must be 5 MB or smaller."
    try:
        # Opening an image only reads its header. Load the pixel data before publishing it.
        with Image.open(BytesIO(data), formats=tuple(IMAGE_FORMATS)) as image:
            image.load()
            ext = IMAGE_FORMATS[image.format]
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return "", "Please choose a valid JPG, PNG or WebP image."
    name = f"{uuid.uuid4().hex}.{ext}"
    url = f"/static/uploads/idp/{name}"
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(os.path.join(UPLOAD_DIR, name), "wb") as out:
            out.write(data)
    except OSError:
        remove_uploaded_photo(url)
        return "", "The photo could not be saved. Please try again."
    return url, None


# Deletes an uploaded photo file that is no longer needed (shared sample photos are kept).
def remove_uploaded_photo(photo_url):
    """Removes a staged or unreferenced upload. Shared sample photos are kept."""
    prefix = "/static/uploads/idp/"
    if not photo_url or not photo_url.startswith(prefix):
        return
    name = photo_url.removeprefix(prefix)
    if not name or name != os.path.basename(name) or name in (".", ".."):
        return
    try:
        os.remove(os.path.join(UPLOAD_DIR, name))
    except FileNotFoundError:
        pass
    except OSError:
        logging.getLogger(__name__).warning("Could not remove unreferenced upload %s", name, exc_info=True)


# ================================================================== home
class DesignerDashboard:
    """Interior Designer home: Company Information, My Interior Design Projects, Portfolio Statistics."""

    # Shows the Interior Designer Home page with shortcuts and portfolio totals.
    def show(self):
        totals = ViewPortfolioTotalsController().execute(PortfolioTotalsRequest(_sid()))
        expired = _expired(totals)
        if expired:
            return expired
        company = ViewCompanyInfoController().execute(ViewCompanyInfoRequest(_sid()))
        return render("designer/home.html", totals=totals.data, hasCompany=company.ok)


# ================================================================== US23-US25 company information
class CompanyInfoPage:
    """US24 View Company Information."""

    # Sets up the page with the controller that reads the designer's company information.
    def __init__(self):
        self.controller = ViewCompanyInfoController()

    # US24: asks for the designer's own company information.
    def requestCompanyInfo(self, request):
        return self.displayResult(self.controller.execute(request))

    # Shows the Company Information page (or the prompt to create it).
    def displayResult(self, result):
        return _expired(result) or render("designer/company.html", result=result)


class CreateCompanyInfoPage:
    """US23 Create Company Information."""

    # Sets up the page with the controller that creates company information.
    def __init__(self):
        self.controller = CreateCompanyInfoController()

    # US23: shows the create form, or sends the designer to the existing record if one exists.
    def show(self, form=None):
        current = ViewCompanyInfoController().execute(ViewCompanyInfoRequest(_sid()))
        if current.ok and form is None:
            flash("Company information already exists. Use Edit instead.", "info")
            return redirect(url_for("designer_company"))
        return render("designer/company_form.html", heading="Create Company Information", form=form or {},
                      submit_label="Save Company Information", creating=True)

    # US23: saves the new company information and shows the outcome.
    def submitCompanyInfo(self, request):
        result = self.controller.execute(request)
        expired = _expired(result)
        if expired:
            return expired
        if result.ok:
            return self.displaySuccessMessage(result.message)
        return self.displayErrorMessage(result.message, request)

    # Shows the success message on the Company Information page.
    def displaySuccessMessage(self, message):
        flash(message, "success")
        return redirect(url_for("designer_company"))

    # Shows the error and the form again with the entered values.
    def displayErrorMessage(self, message, request):
        flash(message, "error")  # the entered values are kept
        return render("designer/company_form.html", heading="Create Company Information", form=vars(request),
                      submit_label="Save Company Information", creating=True)


class UpdateCompanyInfoPage:
    """US25 Update Company Information."""

    # Sets up the page with the controller that updates company information.
    def __init__(self):
        self.controller = UpdateCompanyInfoController()

    # US25: shows the edit form filled with the current company information.
    def show(self):
        current = ViewCompanyInfoController().execute(ViewCompanyInfoRequest(_sid()))
        expired = _expired(current)
        if expired:
            return expired
        if not current.ok:
            flash("You have not added company information yet. Please create it first.", "info")
            return redirect(url_for("designer_company_create"))
        return render("designer/company_form.html", heading="Edit Company Information", form=current.data,
                      submit_label="Save", creating=False)

    # US25: saves the changed company information and shows the outcome.
    def submitUpdatedInfo(self, request):
        result = self.controller.execute(request)
        expired = _expired(result)
        if expired:
            return expired
        if result.ok:
            return self.displaySuccessMessage(result.message)
        return self.displayErrorMessage(result.message, request)

    # Shows the success message on the Company Information page.
    def displaySuccessMessage(self, message):
        flash(message, "success")
        return redirect(url_for("designer_company"))

    # Shows the error and the edit form again with the entered values.
    def displayErrorMessage(self, message, request):
        flash(message, "error")
        return render("designer/company_form.html", heading="Edit Company Information", form=vars(request),
                      submit_label="Save", creating=False)


# Builds a company request from the submitted form fields and the session.
def company_request(form, cls=CompanyInfoRequest):
    return cls(_sid(), **{k: form.get(k, "") for k in COMPANY_FIELDS})


# ================================================================== US26-US31 portfolio
# Returns every category, for the project form's category list.
def _categories():
    return ViewCategoriesController().execute().data or []


# Keeps a new upload only when the project is saved and explains when to choose it again.
def _submit_project_with_photo(controller, request, photo_file, retry_message):
    photo_url, photo_error = save_photo(photo_file)
    if photo_error:
        return Result.fail("INVALID_INPUT", photo_error)
    request.photoUrl = photo_url
    result = None
    try:
        result = controller.execute(request)
    finally:
        if photo_url and (result is None or not result.ok):
            remove_uploaded_photo(photo_url)
            request.photoUrl = None
    if photo_url and result.code == "INVALID_INPUT":
        result.message += f" {retry_message}"
    return result


class CreateIDPPage:
    """US26 Create IDP."""

    # Sets up the page with the controller that creates projects.
    def __init__(self):
        self.controller = CreateIDPController()

    # Opens the create form, or sends a designer without company information to add it first.
    def open(self):
        company = ViewCompanyInfoController().execute(ViewCompanyInfoRequest(_sid()))
        expired = _expired(company)
        if expired:
            return expired
        if company.code == "NO_COMPANY":
            return self.displayNoCompany()
        return self.show()

    # US26: shows the Create Interior Design Project form.
    def show(self, form=None):
        return render("designer/project_form.html", heading="Create Interior Design Project", form=form or
                      {"projectStatus": "CURRENT"}, idpId=None, current_project=None,
                      categories=_categories(), submit_label="Create Project")

    # US26: saves the photo and the new project, then shows the outcome.
    def submitIDP(self, request, photo_file=None):
        result = _submit_project_with_photo(self.controller, request, photo_file, "Please choose the photo again.")
        expired = _expired(result)
        if expired:
            return expired
        if result.ok:
            return self.displaySuccessMessage(result)
        if result.code == "NO_COMPANY":
            return self.displayNoCompany()
        return self.displayErrorMessage(result.message, request)

    # Asks the designer to add company information first and opens that form.
    def displayNoCompany(self):
        flash("Please add your company information before creating a project.", "error")
        return redirect(url_for("designer_company_create"))

    # Opens the new project with the success message.
    def displaySuccessMessage(self, result):
        flash(result.message, "success")
        return redirect(url_for("designer_project_detail", idp_id=result.data["idpId"]))

    # Shows the error and the form again with the entered values.
    def displayErrorMessage(self, message, request):
        flash(message, "error")
        return self.show(vars(request))


class UpdateIDPPage:
    """US29 Update IDP (including Current -> Past)."""

    # Sets up the page with the controller that updates projects.
    def __init__(self):
        self.controller = UpdateIDPController()

    # US29: shows the edit form filled with the project's current details.
    def show(self, idpId, form=None):
        current = ViewMyIDPsController().execute(ViewMyIDPsRequest(_sid(), idpId))
        expired = _expired(current)
        if expired:
            return expired
        if form is None:
            if not current.ok:
                flash("This project is no longer available.", "error")
                return redirect(url_for("designer_projects"))
            form = current.data
        # The preview uses saved project data even when the submitted fields are invalid.
        return render("designer/project_form.html", heading="Edit Project", form=form, idpId=idpId,
                      current_project=current.data, categories=_categories(), submit_label="Save")

    # US29: saves the changed project (and a new photo if chosen), then shows the outcome.
    def submitUpdatedIDP(self, request, photo_file=None):
        result = _submit_project_with_photo(self.controller, request, photo_file, "Please choose the new photo again.")
        expired = _expired(result)
        if expired:
            return expired
        if result.ok:
            remove_uploaded_photo((result.data or {}).get("unusedPhotoUrl"))
            return self.displaySuccessMessage(result.message, request.idpId)
        if result.code == "NOT_OWNER":
            flash(result.message, "error")
            return redirect(url_for("designer_projects"))
        return self.displayErrorMessage(result.message, request)

    # Opens the project with the success message.
    def displaySuccessMessage(self, message, idpId):
        flash(message, "success")
        return redirect(url_for("designer_project_detail", idp_id=idpId))

    # Shows the error and the edit form again with the entered values.
    def displayErrorMessage(self, message, request):
        flash(message, "error")
        return self.show(request.idpId, vars(request))


class MyIDPsPanel:
    """US27 View My IDPs: the list of cards, and one project's details."""

    # Sets up the panel with the controller that lists the designer's projects.
    def __init__(self):
        self.controller = ViewMyIDPsController()

    # US27: asks for the designer's projects, or one project when an ID is given.
    def requestMyIDPs(self, request, back=None):
        return self.displayResult(self.controller.execute(request), request, back=back or {})

    # Shows My Interior Design Projects or one project's page.
    def displayResult(self, result, request, status="", keyword="", back=None):
        expired = _expired(result)
        if expired:
            return expired
        if request.idpId not in (None, ""):
            if not result.ok:
                flash(result.message, "error")
                return redirect(url_for("designer_projects", **(back or {})))
            return render("designer/project_detail.html", project=result.data, back=back or {})
        if not result.ok:
            flash(result.message, "error")
        return render("designer/projects.html", result=result, status=status, keyword=keyword)


class FilterMyIDPsPanel:
    """US28 Filter My IDPs by Current or Past Status (All clears the filter)."""

    # Sets up the panel with the controller that filters by status.
    def __init__(self):
        self.controller = FilterMyIDPsController()

    # US28: shows the designer's Current or Past projects.
    def submitFilter(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the filtered list with its message.
    def displayResult(self, result, request):
        expired = _expired(result)
        if expired:
            return expired
        if not result.ok:
            flash(result.message, "error")
        return render("designer/projects.html", result=result, status=request.status, keyword="", filtered=True)


class SearchMyIDPsPanel:
    """US31 Search My IDPs; with a status chosen too, the keyword and status apply together."""

    # Sets up the panel with the keyword and keyword-plus-status controllers.
    def __init__(self):
        self.controller = SearchMyIDPsController()
        self.combinedController = SearchAndFilterMyIDPsController()

    # US31: shows the designer's projects matching a keyword.
    def submitSearch(self, request, status=""):
        return self.displayResult(self.controller.execute(request), request.keyword, status)

    # US28 + US31: shows projects matching both the keyword and the status.
    def submitSearchAndFilter(self, request):
        return self.displayResult(self.combinedController.execute(request), request.keyword, request.status)

    # Shows the search results with their message and the filters kept.
    def displayResult(self, result, keyword, status=""):
        expired = _expired(result)
        if expired:
            return expired
        if not result.ok:
            flash(result.message, "error")
        return render("designer/projects.html", result=result, status=status, keyword=keyword)


class DeleteIDPDialog:
    """US30 Delete IDP with a confirmation step that warns about views and favourites."""

    # Sets up the dialog with the controller that deletes projects.
    def __init__(self):
        self.controller = DeleteIDPController()

    # US30: warns that views and favourites go too and asks to confirm.
    def askConfirmation(self, idpId):
        current = ViewMyIDPsController().execute(ViewMyIDPsRequest(_sid(), idpId))
        expired = _expired(current)
        if expired:
            return expired
        if not current.ok:
            flash("This project is no longer available.", "error")
            return redirect(url_for("designer_projects"))
        return render("shared/confirm.html", heading="Delete Project?",
                      message=f"Delete '{current.data['title']}'? Its views and favourites are deleted too. "
                              "This cannot be undone.",
                      confirm_label="Delete", action=url_for("designer_project_delete", idp_id=idpId),
                      cancel=url_for("designer_project_detail", idp_id=idpId), danger=True)

    # US30: deletes the project and its uploaded photo after the designer confirms.
    def confirmDelete(self, request):
        result = self.controller.execute(request)
        if result.ok:
            remove_uploaded_photo((result.data or {}).get("unusedPhotoUrl"))
        return self.displayResult(result)

    # Returns to My Projects with the outcome message.
    def displayResult(self, result):
        expired = _expired(result)
        if expired:
            return expired
        flash(result.message, "success" if result.ok else "error")
        return redirect(url_for("designer_projects"))


# ================================================================== US34-US41 statistics
# Returns the designer's projects, for the Project Statistics drop-down.
def _my_projects():
    result = ViewMyIDPsController().execute(ViewMyIDPsRequest(_sid()))
    return result.data if result.ok else []


class ProjectStatisticsPanel:
    """US34 View Count and US35 Shortlist Count for one chosen project."""

    # Sets up the panel with the view-count and shortlist-count controllers.
    def __init__(self):
        self.viewCountController = ViewProjectViewCountController()
        self.shortlistController = ViewShortlistCountController()

    # Shows the Project Statistics page before a count is chosen.
    def show(self, idpId=""):
        return self.displayResult(None, idpId, "")

    # US34: shows how many times the project was viewed.
    def requestViewCount(self, request):
        return self.displayResult(self.viewCountController.execute(request), request.idpId, "views")

    # US35: shows how many customers currently have the project saved.
    def requestShortlistCount(self, request):
        return self.displayResult(self.shortlistController.execute(request), request.idpId, "shortlists")

    # Shows the chosen count, or the error, on the Project Statistics page.
    def displayResult(self, result, idpId, shown):
        if result is not None:
            expired = _expired(result)
            if expired:
                return expired
            if not result.ok:
                flash(result.message, "error")
        return render("designer/statistics_project.html", result=result, shown=shown, idpId=str(idpId or ""),
                      projects=_my_projects(), tab="project")


class InterestSummaryPanel:
    """US36 Project Interest Summary, US37 Sort by Views, US38 Sort by Shortlists."""

    # Sets up the panel with the summary and the two sorting controllers.
    def __init__(self):
        self.summaryController = ViewInterestSummaryController()
        self.viewSortController = SortByViewCountController()
        self.shortlistSortController = SortByShortlistCountController()

    # US36: shows views and shortlists for every project.
    def requestSummary(self, request):
        return self.displayResult(self.summaryController.execute(request), "")

    # US37: shows the summary sorted by views, highest first.
    def requestSortByViews(self, request):
        return self.displayResult(self.viewSortController.execute(request), "views")

    # US38: shows the summary sorted by shortlists, highest first.
    def requestSortByShortlists(self, request):
        return self.displayResult(self.shortlistSortController.execute(request), "shortlists")

    # Shows the Project Interest Summary page.
    def displayResult(self, result, sort):
        expired = _expired(result)
        if expired:
            return expired
        return render("designer/statistics.html", result=result, sort=sort, tab="summary")


class PeriodStatisticsPanel:
    """US39 Views and US40 New Shortlists for a selected day, week or month."""

    # Sets up the panel with the period views and period saves controllers.
    def __init__(self):
        self.viewsController = ViewPeriodViewsController()
        self.savesController = ViewPeriodSavesController()

    # Shows the Statistics for a Period page before a period is chosen.
    def show(self, period="WEEK", date=""):
        return self.displayResult(None, period, date, "")

    # US39: shows views per project for the chosen day, week or month.
    def requestPeriodViews(self, request):
        return self.displayResult(self.viewsController.execute(request), request.period, request.date, "views")

    # US40: shows new saves per project for the chosen day, week or month.
    def requestPeriodSaves(self, request):
        return self.displayResult(self.savesController.execute(request), request.period, request.date, "saves")

    # Shows the period figures, or the error, on the page.
    def displayResult(self, result, period, date, shown):
        if result is not None:
            expired = _expired(result)
            if expired:
                return expired
            if not result.ok:
                flash(result.message, "error")
                result = None
        return render("designer/statistics_period.html", result=result, period=(period or "WEEK").upper(),
                      date=date, shown=shown, tab="period")


class PortfolioTotalsPanel:
    """US41 Portfolio Totals."""

    # Sets up the panel with the controller that totals the portfolio.
    def __init__(self):
        self.controller = ViewPortfolioTotalsController()

    # US41: asks for total views and current shortlists across all projects.
    def requestTotals(self, request):
        return self.displayResult(self.controller.execute(request))

    # Shows the Portfolio Totals page.
    def displayResult(self, result):
        return _expired(result) or render("designer/statistics_totals.html", totals=result.data, tab="totals")
