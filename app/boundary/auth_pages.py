"""Boundary classes for US01-US12: registration, login, logout, home pages, personal details."""
from flask import redirect, url_for, flash

from app.boundary.ui import render, start_login_session, end_login_session, current_session_id, handle_expired
from app.common.request_types import (RegistrationRequest, LoginRequest, SessionRequest, UpdateDetailsRequest,
                                      BrowseIDPsRequest)
from app.control.browse_controllers import BrowseIDPsController
from app.control.favourite_controllers import ViewFavouritesController
from app.control.platform_controllers import ViewCategoriesController
from app.control.account_controllers import (CreateCustomerAccountController, CreateDesignerAccountController,
                                             ViewPersonalDetailsController, UpdatePersonalDetailsController)
from app.control.login_controllers import (CustomerLoginController, DesignerLoginController, UserAdminLoginController,
                                           PlatformManagerLoginController, CustomerLogoutController,
                                           DesignerLogoutController, UserAdminLogoutController,
                                           PlatformManagerLogoutController)
from app.entity.database import CUSTOMER


# ------------------------------------------------------------------ registration (US01, US06)
class _RegistrationPage:
    controller_class = None
    role_label = ""
    login_endpoint = ""

    # Sets up the sign-up page with its role's registration controller.
    def __init__(self):
        self.controller = self.controller_class()

    # US01/US06: shows the sign-up form, keeping any values already entered.
    def show(self, form=None):
        return render("auth/register.html", role_label=self.role_label, form=form or {},
                      login_endpoint=self.login_endpoint)

    # US01/US06: sends the sign-up details to the controller and shows the outcome.
    def submitRegistration(self, name, email, password, contactNumber):
        result = self.controller.execute(RegistrationRequest(name, email, password, contactNumber))
        if result.success:
            return self.displaySuccessMessage()
        return self.displayErrorMessage(result.message, {"name": name, "email": email, "contactNumber": contactNumber})

    # Tells the user the account was created and opens the login page.
    def displaySuccessMessage(self):
        flash("Account created. You can now log in.", "success")
        return redirect(url_for(self.login_endpoint))

    # Shows the error and the form again with the entered values (not the password).
    def displayErrorMessage(self, message, form):
        flash(message, "error")  # entered values (except the password) are kept
        return self.show(form)


class CustomerRegistrationPage(_RegistrationPage):
    controller_class, role_label, login_endpoint = CreateCustomerAccountController, "Customer", "customer_login"


class DesignerRegistrationPage(_RegistrationPage):
    controller_class, role_label, login_endpoint = CreateDesignerAccountController, "Interior Designer", "designer_login"


# ------------------------------------------------------------------ login (US02, US07, US09, US11)
class _LoginPage:
    controller_class = None
    role_label = ""
    home_endpoint = ""
    register_endpoint = None
    staff = False

    # Sets up the login page with its role's login controller.
    def __init__(self):
        self.controller = self.controller_class()

    # US02/US07/US09/US11: shows the login form for this role.
    def show(self, email=""):
        return render("auth/login.html", role_label=self.role_label, email=email,
                      register_endpoint=self.register_endpoint, staff=self.staff)

    # Checks the email and password; on success starts the session and opens the home page.
    def submitLogin(self, email, password):
        result = self.controller.execute(LoginRequest(email, password))
        if result.success:
            start_login_session(result.data)
            return self.openHomePage()
        return self.displayLoginError(result.message, email)

    # Opens the role's home page after a successful login.
    def openHomePage(self):
        return redirect(url_for(self.home_endpoint))

    # Shows the login error and the form again with the email kept.
    def displayLoginError(self, message, email):
        flash(message, "error")
        return self.show(email)


class CustomerLoginPage(_LoginPage):
    controller_class, role_label, home_endpoint = CustomerLoginController, "Customer", "customer_home"
    register_endpoint = "customer_register"


class DesignerLoginPage(_LoginPage):
    controller_class, role_label, home_endpoint = DesignerLoginController, "Interior Designer", "designer_home"
    register_endpoint = "designer_register"


class UserAdminLoginPage(_LoginPage):
    controller_class, role_label, home_endpoint = UserAdminLoginController, "User Admin", "admin_accounts"
    staff = True


class PlatformManagerLoginPage(_LoginPage):
    controller_class, role_label, home_endpoint = PlatformManagerLoginController, "Platform Manager", "pm_categories"
    staff = True


# ------------------------------------------------------------------ public landing page
class LandingPage:
    """Public home page: a preview of real projects and the sign-up / log-in entry points."""

    # Sets up the public first page with the project and category controllers.
    def __init__(self):
        self.browseController = BrowseIDPsController()
        self.categoriesController = ViewCategoriesController()

    # Shows the public first page with the project and category counts and three preview tiles.
    def show(self):
        projects = self.browseController.execute(BrowseIDPsRequest(1))
        items = projects.data["items"] if projects.ok and projects.data else []
        categories = self.categoriesController.execute().data or []
        return render("index.html", projectCount=projects.data["total"] if projects.data else 0,
                      categoryCount=len(categories), preview=self.pickPreview(items))

    # Picks the three newest projects that have different photos for the preview tiles.
    def pickPreview(self, items, count=3):
        """The three newest projects with different photos, so the first page never shows the same picture
        twice side by side (8 November). Repeats are used only when there are not enough different photos."""
        chosen, photos = [], set()
        for project in items:
            if project.get("photoUrl") not in photos:
                chosen.append(project)
                photos.add(project.get("photoUrl"))
            if len(chosen) == count:
                return chosen
        return (chosen + [p for p in items if p not in chosen])[:count]


# ------------------------------------------------------------------ home pages with Log Out (US05, US08, US10, US12)
class _HomePage:
    logout_controller_class = None
    login_endpoint = ""

    # Sets up a role's home page with its logout controller.
    def __init__(self):
        self.logoutController = self.logout_controller_class()

    # US05/US08/US10/US12: ends the session and returns to the role's login page.
    def logout(self):
        result = self.logoutController.execute(SessionRequest(current_session_id()))
        end_login_session()
        flash(result.message, "success")
        return redirect(url_for(self.login_endpoint))


class CustomerHomePage(_HomePage):
    logout_controller_class, login_endpoint = CustomerLogoutController, "customer_login"

    # Shows the Customer home page: search box, shortcuts, favourite count and newest projects.
    def show(self):
        projects = BrowseIDPsController().execute(BrowseIDPsRequest(1))
        favourites = ViewFavouritesController().execute(SessionRequest(current_session_id()))
        expired = handle_expired(favourites, CUSTOMER)
        if expired:
            return expired
        return render("customer/home.html", projectCount=(projects.data or {}).get("total", 0),
                      newest=(projects.data or {}).get("items", [])[:4], favouriteCount=len(favourites.data or []))


class DesignerHomePage(_HomePage):
    logout_controller_class, login_endpoint = DesignerLogoutController, "designer_login"


class UserAdminHomePage(_HomePage):
    logout_controller_class, login_endpoint = UserAdminLogoutController, "admin_login"


class PlatformManagerHomePage(_HomePage):
    logout_controller_class, login_endpoint = PlatformManagerLogoutController, "pm_login"


# ------------------------------------------------------------------ personal details (US03, US04)
class PersonalDetailsPage:
    # Sets up the page with the controller that reads the Customer's details.
    def __init__(self):
        self.controller = ViewPersonalDetailsController()

    # US03: reads the logged-in Customer's details (or goes to login if the session ended).
    def requestDetails(self):
        result = self.controller.execute(SessionRequest(current_session_id()))
        return handle_expired(result, CUSTOMER) or self.displayDetails(result.data)

    # Shows the Personal Details page.
    def displayDetails(self, details):
        return render("customer/details.html", details=details)


class UpdatePersonalDetailsPage:
    # Sets up the page with the controllers that read and update personal details.
    def __init__(self):
        self.controller = UpdatePersonalDetailsController()
        self.viewController = ViewPersonalDetailsController()

    # US04: shows the edit form filled with the Customer's current name and contact number.
    def show(self, form=None):
        result = self.viewController.execute(SessionRequest(current_session_id()))
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        return render("customer/details_edit.html", details=result.data, form=form or result.data)

    # US04: saves the new name and contact number and shows the outcome.
    def submitUpdate(self, name, contactNumber):
        result = self.controller.execute(UpdateDetailsRequest(current_session_id(), name, contactNumber))
        expired = handle_expired(result, CUSTOMER)
        if expired:
            return expired
        if result.success:
            flash(result.message, "success")
            return redirect(url_for("customer_details"))
        flash(result.message, "error")
        return self.show({"name": name, "contactNumber": contactNumber})
