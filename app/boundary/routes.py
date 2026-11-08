"""URL map: each route creates the Boundary object for the page and calls one of its methods.

Routes contain no business logic; they only read form/query values and hand them to the boundary.
"""
from flask import request, redirect, url_for, session, g

from app.boundary.admin_pages import (SearchUserAccountsPanel, CreateUserAccountForm, ViewUserAccountPanel,
                                      UpdateUserAccountForm, SuspendUserAccountDialog, SearchUserProfilesPanel,
                                      CreateUserProfileForm, ViewUserProfilePanel, UpdateUserProfileForm,
                                      SuspendUserProfileDialog, ReactivateUserAccountDialog,
                                      ReactivateUserProfileDialog)
from app.boundary.auth_pages import (CustomerRegistrationPage, DesignerRegistrationPage, CustomerLoginPage,
                                     DesignerLoginPage, UserAdminLoginPage, PlatformManagerLoginPage, CustomerHomePage,
                                     DesignerHomePage, UserAdminHomePage, PlatformManagerHomePage, PersonalDetailsPage,
                                     UpdatePersonalDetailsPage, LandingPage)
from app.boundary.consultation_pages import ConsultationPanel
from app.boundary.customer_pages import (ViewIDPDetailsPanel,
                                         ViewFavouritesPanel, SearchFavouritesPanel, RemoveFavouriteDialog,
                                         DesignerPortfolioPanel, DesignerCompanyInfoPanel)
from app.boundary.customer_pages import ProjectFiltersPanel
from app.boundary.designer_pages import (DesignerDashboard, CompanyInfoPage, CreateCompanyInfoPage,
                                         UpdateCompanyInfoPage, CreateIDPPage, UpdateIDPPage, MyIDPsPanel,
                                         FilterMyIDPsPanel, SearchMyIDPsPanel, DeleteIDPDialog, ProjectStatisticsPanel,
                                         InterestSummaryPanel, PeriodStatisticsPanel, PortfolioTotalsPanel,
                                         company_request, IDP_FIELDS)
from app.boundary.platform_pages import (CategoryManagementPanel, CreateCategoryForm, UpdateCategoryForm,
                                         RemoveCategoryDialog, ReportPanel)
from app.boundary.renovation_brief_page import BRIEF_ANSWER_KEYS, RenovationBriefPage
from app.boundary.ui import (render, requires_role, ROLE_AREAS, current_session_id, list_position,
                             CUSTOMER_LIST_KEYS, DESIGNER_LIST_KEYS)
from app.common.request_types import (CreateAccountRequest, AccountIdRequest, UpdateAccountRequest,
                                      SearchAccountsRequest, CreateProfileRequest, ProfileIdRequest,
                                      UpdateProfileRequest, SearchProfilesRequest)
from app.common.request_types import ProjectFiltersRequest
from app.common.request_types import (DesignerIdRequest, ViewCompanyInfoRequest, UpdateCompanyInfoRequest,
                                      CreateIDPRequest, UpdateIDPRequest, ViewMyIDPsRequest, FilterMyIDPsRequest,
                                      SearchMyIDPsRequest, MyIDPsFiltersRequest, DeleteIDPRequest, ProjectStatRequest,
                                      InterestSummaryRequest, PeriodStatRequest, PortfolioTotalsRequest)
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER, USER_ADMIN, PLATFORM_MANAGER

F = lambda name: request.form.get(name, "")
Q = lambda name, default="": request.args.get(name, default)


# Carries either the questionnaire answers or the ordinary browse filters into project details.
def project_return_args():
    keys = ("fromBrief", *BRIEF_ANSWER_KEYS, "shown") if Q("fromBrief") == "1" else CUSTOMER_LIST_KEYS
    return list_position(request.args, keys)


# Connects every web address to the Boundary class and method that handles it.
def register_routes(app):
    route = app.route

    # ------------------------------------------------------------ landing
    # Public first page; logged-in users go straight to their own home page.
    @route("/")
    def index():
        role = session.get("role")
        if role:
            return redirect(url_for({CUSTOMER: "customer_home", INTERIOR_DESIGNER: "designer_home",
                                     USER_ADMIN: "admin_accounts", PLATFORM_MANAGER: "pm_categories"}[role]))
        return LandingPage().show()

    # ------------------------------------------------------------ registration and login (US01-US12)
    # Adds the login, logout and (for Customer and Designer) sign-up addresses for one role.
    def auth_routes(prefix, login_cls, home_cls, register_cls=None):
        # Shows the role's login page, or checks the submitted email and password.
        def login():
            page = login_cls()
            if request.method == "POST":
                return page.submitLogin(F("email"), F("password"))
            return page.show()
        app.add_url_rule(f"/{prefix}/login", f"{prefix}_login", login, methods=["GET", "POST"])

        # Logs the user out of this role.
        def logout():
            return home_cls().logout()
        app.add_url_rule(f"/{prefix}/logout", f"{prefix}_logout", logout, methods=["POST"])

        if register_cls:
            # Shows the role's sign-up page, or creates the account from the submitted form.
            def register():
                page = register_cls()
                if request.method == "POST":
                    return page.submitRegistration(F("name"), F("email"), F("password"), F("contactNumber"))
                return page.show()
            app.add_url_rule(f"/{prefix}/register", f"{prefix}_register", register, methods=["GET", "POST"])

    auth_routes("customer", CustomerLoginPage, CustomerHomePage, CustomerRegistrationPage)
    auth_routes("designer", DesignerLoginPage, DesignerHomePage, DesignerRegistrationPage)
    auth_routes("admin", UserAdminLoginPage, UserAdminHomePage)
    auth_routes("pm", PlatformManagerLoginPage, PlatformManagerHomePage)

    # ------------------------------------------------------------ customer (US03-US04, US13-US22, US32-US33)
    # Shows the combined project list; mode keeps the older single-filter addresses working.
    def project_list(mode="browse"):
        return ProjectFiltersPanel().requestList(ProjectFiltersRequest(
            keyword=Q("keyword"), categoryId=Q("categoryId"), status=Q("status"),
            minBudget=Q("minBudget"), maxBudget=Q("maxBudget"), page=Q("page", "1"), mode=mode))

    # Customer home page.
    @route("/customer/home")
    @requires_role(CUSTOMER)
    def customer_home():
        return CustomerHomePage().show()

    # US03: Customer's Personal Details page.
    @route("/customer/details")
    @requires_role(CUSTOMER)
    def customer_details():
        return PersonalDetailsPage().requestDetails()

    # US04: shows or saves the Update Personal Details form.
    @route("/customer/details/edit", methods=["GET", "POST"])
    @requires_role(CUSTOMER)
    def customer_details_edit():
        page = UpdatePersonalDetailsPage()
        if request.method == "POST":
            return page.submitUpdate(F("name"), F("contactNumber"))
        return page.show()

    # US13-US17: Interior Design Projects list with all filters.
    @route("/customer/projects")
    @requires_role(CUSTOMER)
    def customer_projects():
        return project_list()

    # Shows and submits the Customer's renovation questionnaire.
    @route("/customer/find-my-style")
    @requires_role(CUSTOMER)
    def customer_renovation_brief():
        answers = {name: Q(name) for name in BRIEF_ANSWER_KEYS}
        return RenovationBriefPage().show(answers, any(name in request.args for name in answers), Q("shown"))

    # Dispatches the shared inbox page and supports drawer fragments for both roles.
    def consultation_page(role, endpoint):
        panel = ConsultationPanel(role, endpoint)
        fragment = request.headers.get("X-Consultation-Fragment") == "1"
        if request.method == "POST":
            return panel.submit(F("threadId"), F("projectId"), F("message"), F("action"), fragment)
        return panel.show(Q("threadId"), Q("projectId"), fragment)

    # Opens the Customer's private message history or a project consultation.
    @route("/customer/messages", methods=["GET", "POST"])
    @requires_role(CUSTOMER)
    def customer_messages():
        return consultation_page(CUSTOMER, "customer_messages")

    # Opens the Interior Designer's consultation inbox.
    @route("/designer/messages", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_messages():
        return consultation_page(INTERIOR_DESIGNER, "designer_messages")

    # US14: older search address; it now uses the combined list.
    @route("/customer/projects/search")
    @requires_role(CUSTOMER)
    def customer_projects_search():
        return project_list("search")

    # US15: older category filter address; it now uses the combined list.
    @route("/customer/projects/category")
    @requires_role(CUSTOMER)
    def customer_projects_category():
        return project_list("category")

    # US16: older status filter address; it now uses the combined list.
    @route("/customer/projects/status")
    @requires_role(CUSTOMER)
    def customer_projects_status():
        return project_list("status")

    # US17: older budget filter address; it now uses the combined list.
    @route("/customer/projects/budget")
    @requires_role(CUSTOMER)
    def customer_projects_budget():
        return project_list("budget")

    # US18: one project's page, remembering the browse position or renovation brief for Back.
    @route("/customer/projects/<idp_id>")
    @requires_role(CUSTOMER)
    def customer_project_detail(idp_id):
        return ViewIDPDetailsPanel().requestDetails(idp_id, project_return_args())

    # US19: saves the project to favourites (in the background when JavaScript is on).
    @route("/customer/projects/<idp_id>/save", methods=["POST"])
    @requires_role(CUSTOMER)
    def customer_project_save(idp_id):
        background = request.headers.get("X-Requested-With") == "fetch"
        return ViewIDPDetailsPanel().saveToFavourites(idp_id, background, project_return_args())

    # US20: My Favourites page.
    @route("/customer/favourites")
    @requires_role(CUSTOMER)
    def customer_favourites():
        return ViewFavouritesPanel().requestFavourites()

    # US21: searches My Favourites.
    @route("/customer/favourites/search")
    @requires_role(CUSTOMER)
    def customer_favourites_search():
        return SearchFavouritesPanel().submitSearch(Q("keyword"))

    # US22: asks to confirm, then removes a project from favourites.
    @route("/customer/favourites/<idp_id>/remove", methods=["GET", "POST"])
    @requires_role(CUSTOMER)
    def customer_favourite_remove(idp_id):
        dialog = RemoveFavouriteDialog()
        if request.method == "POST":
            return dialog.confirmRemove(idp_id)
        return dialog.askConfirmation(idp_id, Q("title", "this project"))

    # US32: a designer's portfolio, as a Customer sees it.
    @route("/customer/designers/<designer_id>")
    @requires_role(CUSTOMER)
    def customer_designer(designer_id):
        return DesignerPortfolioPanel().requestPortfolio(DesignerIdRequest(designer_id))

    # US33: a designer's company information, as a Customer sees it.
    @route("/customer/designers/<designer_id>/company")
    @requires_role(CUSTOMER)
    def customer_designer_company(designer_id):
        return DesignerCompanyInfoPanel().requestCompanyInfo(DesignerIdRequest(designer_id))

    # ------------------------------------------------------------ interior designer (US23-US31, US34-US41)
    sid = current_session_id

    # Interior Designer Home page.
    @route("/designer/home")
    @requires_role(INTERIOR_DESIGNER)
    def designer_home():
        return DesignerDashboard().show()

    # US24: the designer's own Company Information page.
    @route("/designer/company")
    @requires_role(INTERIOR_DESIGNER)
    def designer_company():
        return CompanyInfoPage().requestCompanyInfo(ViewCompanyInfoRequest(sid()))

    # US23: shows or saves the Create Company Information form.
    @route("/designer/company/new", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_company_create():
        page = CreateCompanyInfoPage()
        return page.submitCompanyInfo(company_request(request.form)) if request.method == "POST" else page.show()

    # US25: shows or saves the Edit Company Information form.
    @route("/designer/company/edit", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_company_edit():
        page = UpdateCompanyInfoPage()
        if request.method == "POST":
            return page.submitUpdatedInfo(company_request(request.form, UpdateCompanyInfoRequest))
        return page.show()

    # US27/US28/US31: My Interior Design Projects with keyword and status filters.
    @route("/designer/projects")
    @requires_role(INTERIOR_DESIGNER)
    def designer_projects():
        """One filter form (Keyword, Status, Apply filters): each works alone or both together."""
        status = Q("status").strip().upper()
        status = "" if status == "ALL" else status
        keyword = Q("q").strip()
        if keyword and status:                                # US28 + US31 together
            return SearchMyIDPsPanel().submitSearchAndFilter(MyIDPsFiltersRequest(sid(), keyword, status))
        if keyword:                                           # US31
            return SearchMyIDPsPanel().submitSearch(SearchMyIDPsRequest(sid(), keyword))
        if status:                                            # US28
            return FilterMyIDPsPanel().submitFilter(FilterMyIDPsRequest(sid(), status))
        return MyIDPsPanel().requestMyIDPs(ViewMyIDPsRequest(sid()))  # US27 (and Clear all)

    # Older status filter address; redirects to My Projects with the status kept.
    @route("/designer/projects/filter")
    @requires_role(INTERIOR_DESIGNER)
    def designer_projects_filter():
        return redirect(url_for("designer_projects", status=Q("status")))

    # Older search address; redirects to My Projects with the keyword kept.
    @route("/designer/projects/search")
    @requires_role(INTERIOR_DESIGNER)
    def designer_projects_search():
        return redirect(url_for("designer_projects", q=Q("keyword")))

    # Collects the project fields from the submitted form.
    def idp_form():
        return {k: F(k) for k in IDP_FIELDS}

    # US26: shows or saves the Create Interior Design Project form.
    @route("/designer/projects/new", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_project_new():
        page = CreateIDPPage()
        if request.method == "POST":
            return page.submitIDP(CreateIDPRequest(sid(), **idp_form()), request.files.get("photo"))
        return page.open()

    # US27: one of the designer's projects, remembering the list position for Back.
    @route("/designer/projects/<idp_id>")
    @requires_role(INTERIOR_DESIGNER)
    def designer_project_detail(idp_id):
        return MyIDPsPanel().requestMyIDPs(ViewMyIDPsRequest(sid(), idp_id),
                                           list_position(request.args, DESIGNER_LIST_KEYS))

    # US29: shows or saves the Edit Project form.
    @route("/designer/projects/<idp_id>/edit", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_project_edit(idp_id):
        page = UpdateIDPPage()
        if request.method == "POST":
            return page.submitUpdatedIDP(UpdateIDPRequest(sid(), idp_id, **idp_form()), request.files.get("photo"))
        return page.show(idp_id)

    # US30: asks to confirm, then deletes the project.
    @route("/designer/projects/<idp_id>/delete", methods=["GET", "POST"])
    @requires_role(INTERIOR_DESIGNER)
    def designer_project_delete(idp_id):
        dialog = DeleteIDPDialog()
        if request.method == "POST":
            return dialog.confirmDelete(DeleteIDPRequest(sid(), idp_id))
        return dialog.askConfirmation(idp_id)

    # US36-US38: Project Interest Summary, optionally sorted by views or shortlists.
    @route("/designer/statistics")
    @requires_role(INTERIOR_DESIGNER)
    def designer_statistics():
        panel, req = InterestSummaryPanel(), InterestSummaryRequest(sid())
        sort = Q("sort")
        if sort == "views":
            return panel.requestSortByViews(req)
        if sort == "shortlists":
            return panel.requestSortByShortlists(req)
        return panel.requestSummary(req)

    # US34/US35: view count or shortlist count for one project.
    @route("/designer/statistics/project")
    @requires_role(INTERIOR_DESIGNER)
    def designer_statistics_project():
        panel, show = ProjectStatisticsPanel(), Q("show")
        if show == "views":
            return panel.requestViewCount(ProjectStatRequest(sid(), Q("idpId")))
        if show == "shortlists":
            return panel.requestShortlistCount(ProjectStatRequest(sid(), Q("idpId")))
        return panel.show(Q("idpId"))

    # US39/US40: views or new saves per project for a day, week or month.
    @route("/designer/statistics/period")
    @requires_role(INTERIOR_DESIGNER)
    def designer_statistics_period():
        panel, show = PeriodStatisticsPanel(), Q("show")
        if show == "views":
            return panel.requestPeriodViews(PeriodStatRequest(sid(), Q("period"), Q("date")))
        if show == "saves":
            return panel.requestPeriodSaves(PeriodStatRequest(sid(), Q("period"), Q("date")))
        return panel.show(Q("period", "WEEK"), Q("date"))

    # US41: Portfolio Totals page.
    @route("/designer/statistics/totals")
    @requires_role(INTERIOR_DESIGNER)
    def designer_statistics_totals():
        return PortfolioTotalsPanel().requestTotals(PortfolioTotalsRequest(sid()))

    # Older statistics address; redirects to the Statistics page.
    @route("/designer/interest")
    @requires_role(INTERIOR_DESIGNER)
    def designer_interest():
        """Old address of the combined statistics page."""
        return redirect(url_for("designer_statistics", sort=Q("sort") or None))

    # ------------------------------------------------------------ user admin (US42-US51)
    # US46: User Accounts list, or the search results, 20 per page.
    @route("/admin/accounts")
    @requires_role(USER_ADMIN)
    def admin_accounts():
        # US46: opening the page lists all accounts. Submitting Search validates the supplied criteria.
        searching = "keyword" in request.args or "profileId" in request.args
        criteria = SearchAccountsRequest(Q("keyword"), Q("profileId")) if searching else None
        return SearchUserAccountsPanel().submitSearch(criteria, Q("page", "1"))

    # US42: shows or saves the Create Staff Account form.
    @route("/admin/accounts/new", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_account_new():
        form = CreateUserAccountForm()
        if request.method == "POST":
            return form.submit(CreateAccountRequest(displayName=F("displayName"), email=F("email"),
                                                    password=F("password"), profileId=F("profileId"),
                                                    contactNumber=F("contactNumber")))
        return form.show()

    # US43: one account's details.
    @route("/admin/accounts/<account_id>")
    @requires_role(USER_ADMIN)
    def admin_account_view(account_id):
        return ViewUserAccountPanel().requestDetails(AccountIdRequest(account_id))

    # US44: shows or saves the Update User Account form.
    @route("/admin/accounts/<account_id>/edit", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_account_edit(account_id):
        form = UpdateUserAccountForm()
        if request.method == "POST":
            return form.submit(UpdateAccountRequest(account_id, F("displayName"), F("email"), F("contactNumber")))
        return form.show(account_id)

    # US45: asks to confirm, then suspends the account.
    @route("/admin/accounts/<account_id>/suspend", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_account_suspend(account_id):
        dialog = SuspendUserAccountDialog()
        if request.method == "POST":
            return dialog.confirm(AccountIdRequest(account_id, actorAccountId=g.user["accountId"]))
        return dialog.askConfirmation(account_id)

    # US60: asks to confirm, then reactivates the account.
    @route("/admin/accounts/<account_id>/reactivate", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_account_reactivate(account_id):
        dialog = ReactivateUserAccountDialog()
        return dialog.confirm(AccountIdRequest(account_id)) if request.method == "POST" \
            else dialog.askConfirmation(account_id)

    # US51: User Profiles list, or the search results, 20 per page.
    @route("/admin/profiles")
    @requires_role(USER_ADMIN)
    def admin_profiles():
        criteria = SearchProfilesRequest(Q("keyword")) if "keyword" in request.args else None
        return SearchUserProfilesPanel().submitSearch(criteria, Q("page", "1"))

    # US47: shows or saves the Create User Profile form.
    @route("/admin/profiles/new", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_profile_new():
        form = CreateUserProfileForm()
        if request.method == "POST":
            return form.submit(CreateProfileRequest(F("displayName"), F("description"), F("basedOn")))
        return form.show()

    # US48: one profile's details and account count.
    @route("/admin/profiles/<profile_id>")
    @requires_role(USER_ADMIN)
    def admin_profile_view(profile_id):
        return ViewUserProfilePanel().requestDetails(ProfileIdRequest(profile_id))

    # US49: shows or saves the Update User Profile form.
    @route("/admin/profiles/<profile_id>/edit", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_profile_edit(profile_id):
        form = UpdateUserProfileForm()
        if request.method == "POST":
            return form.submit(UpdateProfileRequest(profile_id, F("description")))
        return form.show(profile_id)

    # US50: asks to confirm, then suspends the profile.
    @route("/admin/profiles/<profile_id>/suspend", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_profile_suspend(profile_id):
        dialog = SuspendUserProfileDialog()
        return dialog.confirm(ProfileIdRequest(profile_id, actorAccountId=g.user["accountId"])) \
            if request.method == "POST" else dialog.askConfirmation(profile_id)

    # US61: asks to confirm, then reactivates the profile.
    @route("/admin/profiles/<profile_id>/reactivate", methods=["GET", "POST"])
    @requires_role(USER_ADMIN)
    def admin_profile_reactivate(profile_id):
        dialog = ReactivateUserProfileDialog()
        return dialog.confirm(ProfileIdRequest(profile_id)) if request.method == "POST" \
            else dialog.askConfirmation(profile_id)

    # ------------------------------------------------------------ platform manager (US52-US59)
    # US52/US56: Project Categories list or search results; a POST creates a category.
    @route("/pm/categories", methods=["GET", "POST"])
    @requires_role(PLATFORM_MANAGER)
    def pm_categories():
        if request.method == "POST":
            return CreateCategoryForm().submit(F("name"))
        return CategoryManagementPanel().requestCategories(request.args.get("keyword"), Q("page", "1"))

    # US53: shows or saves the Create Category form.
    @route("/pm/categories/new", methods=["GET", "POST"])
    @requires_role(PLATFORM_MANAGER)
    def pm_category_new():
        form = CreateCategoryForm()
        return form.submit(F("name")) if request.method == "POST" else form.show()

    # US54: shows or saves the Update Category form.
    @route("/pm/categories/<int:category_id>/edit", methods=["GET", "POST"])
    @requires_role(PLATFORM_MANAGER)
    def pm_category_edit(category_id):
        form = UpdateCategoryForm()
        return form.submit(category_id, F("name")) if request.method == "POST" else form.show(category_id)

    # US55: asks to confirm, then removes the category.
    @route("/pm/categories/<int:category_id>/remove", methods=["GET", "POST"])
    @requires_role(PLATFORM_MANAGER)
    def pm_category_remove(category_id):
        dialog = RemoveCategoryDialog()
        return dialog.confirm(category_id) if request.method == "POST" else dialog.askConfirmation(category_id)

    # US57-US59: Platform Reports page and the generated report.
    @route("/pm/reports")
    @requires_role(PLATFORM_MANAGER)
    def pm_reports():
        return ReportPanel().requestReport(Q("periodType", "DAY"), request.args.get("periodValue"))
