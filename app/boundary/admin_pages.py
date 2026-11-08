"""Boundary classes for US42-US51, US60 and US61 (User Admin console). Names follow the Member 5 diagrams."""
from flask import redirect, url_for, flash

from app.boundary.ui import render, paginate
from app.common.request_types import AccountIdRequest, ProfileIdRequest
from app.common.text import plural
from app.control.user_admin_controllers import (CreateUserAccountController, ViewUserAccountController,
                                                UpdateUserAccountController, SuspendUserAccountController,
                                                ReactivateUserAccountController, SearchUserAccountController,
                                                CreateUserProfileController, ViewUserProfileController,
                                                UpdateUserProfileController, SuspendUserProfileController,
                                                ReactivateUserProfileController, SearchUserProfileController)
from app.entity.database import STAFF_ROLES


# Returns every user profile, for the profile drop-down lists.
def _profiles():
    """Profile list for dropdowns, fetched through the controller (boundaries never touch entities)."""
    return SearchUserProfileController().execute().data or []


# ------------------------------------------------------------------ accounts
class SearchUserAccountsPanel:
    # Sets up the panel with the controller that lists and searches accounts.
    def __init__(self):
        self.controller = SearchUserAccountController()

    # US46: runs the account search (or the full list) and shows the chosen page.
    def submitSearch(self, request, page=None):
        return self.displayResult(self.controller.execute(request), request, page)

    # Shows the accounts for one page of 20, with errors, the search fields and page links.
    def displayResult(self, result, request, page=None):
        if not result.ok:
            flash(result.message, "error")
        rows, pager, error = paginate(result.data or [], page)
        if error:
            flash(error, "error")
        keyword = request.keyword if request else ""
        profileId = str(request.profileId or "") if request else ""
        params = {key: value for key, value in (("keyword", keyword), ("profileId", profileId)) if value}
        return render("admin/accounts.html", result=result, rows=rows, pager=pager, params=params,
                      keyword=keyword, profileId=profileId, profiles=_profiles())


class CreateUserAccountForm:
    # Sets up the form with the controller that creates staff accounts.
    def __init__(self):
        self.controller = CreateUserAccountController()

    # US42: shows the Create Staff Account form with the active staff profiles to choose from.
    def show(self, form=None):
        # US42: any active profile based on a staff role, including custom staff profiles (8 November).
        staff = [p for p in _profiles() if p.isActive and p.baseRole in STAFF_ROLES]
        return render("admin/account_form.html", heading="Create Staff Account", form=form or {}, profiles=staff,
                      creating=True)

    # US42: sends the filled-in form to the controller and shows the outcome.
    def submit(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Opens the new account on success, or shows the form again with the error (password cleared).
    def displayResult(self, result, request):
        if result.ok:
            flash(f"{result.message} The new user can now log in.", "success")
            return redirect(url_for("admin_account_view", account_id=result.data["accountId"]))
        flash(result.message, "error")
        form = dict(vars(request), password="")
        return self.show(form)


class ViewUserAccountPanel:
    # Sets up the panel with the controller that reads one account.
    def __init__(self):
        self.controller = ViewUserAccountController()

    # US43: asks the controller for one account's details.
    def requestDetails(self, request):
        return self.displayResult(self.controller.execute(request))

    # Shows the account page, or returns to the list with an error if it no longer exists.
    def displayResult(self, result):
        if not result.ok:
            flash(result.message, "error")
            return redirect(url_for("admin_accounts"))
        return render("admin/account_view.html", account=result.data)


class UpdateUserAccountForm:
    # Sets up the form with the controller that updates accounts.
    def __init__(self):
        self.controller = UpdateUserAccountController()

    # US44: shows the edit form filled with the account's current details (profile read-only).
    def show(self, accountId, form=None):
        current = ViewUserAccountController().execute(AccountIdRequest(accountId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_accounts"))
        fields = dict(current.data, displayName=current.data["name"])
        fields.update(form or {})
        return render("admin/account_form.html", heading="Update User Account", form=fields,
                      roleName=current.data["roleName"],
                      creating=False, accountId=accountId)

    # US44: sends the changed details to the controller and shows the outcome.
    def submit(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Returns to the account page on success, or shows the form again with the error.
    def displayResult(self, result, request):
        if result.ok:
            flash(result.message, "success")
            return redirect(url_for("admin_account_view", account_id=request.accountId))
        flash(result.message, "error")
        return self.show(request.accountId, vars(request))


class SuspendUserAccountDialog:
    # Sets up the dialog with the controller that suspends accounts.
    def __init__(self):
        self.controller = SuspendUserAccountController()

    # US45: asks the User Admin to confirm suspending this account.
    def askConfirmation(self, accountId):
        current = ViewUserAccountController().execute(AccountIdRequest(accountId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_accounts"))
        return render("shared/confirm.html", heading="Suspend This Account?",
                      message=f"{current.data['name']} ({current.data['email']}) will be logged out "
                              "and blocked from logging in.",
                      confirm_label="Suspend", action=url_for("admin_account_suspend", account_id=accountId),
                      cancel=url_for("admin_account_view", account_id=accountId), danger=True)

    # US45: suspends the account after the User Admin confirms.
    def confirm(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the outcome message on the account page.
    def displayResult(self, result, request):
        flash(result.message, "success" if result.ok else "error")
        return redirect(url_for("admin_account_view", account_id=request.accountId))


class ReactivateUserAccountDialog:
    """US60 Reactivate User Account: confirm, then the account can log in again."""

    # Sets up the dialog with the controller that reactivates accounts.
    def __init__(self):
        self.controller = ReactivateUserAccountController()

    # US60: asks the User Admin to confirm reactivating this account.
    def askConfirmation(self, accountId):
        current = ViewUserAccountController().execute(AccountIdRequest(accountId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_accounts"))
        return render("shared/confirm.html", heading="Reactivate This Account?",
                      message=f"{current.data['name']} ({current.data['email']}) will be able to log in again.",
                      confirm_label="Reactivate", action=url_for("admin_account_reactivate", account_id=accountId),
                      cancel=url_for("admin_account_view", account_id=accountId))

    # US60: reactivates the account after the User Admin confirms.
    def confirm(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the outcome on the account page (or the list if the account is gone).
    def displayResult(self, result, request):
        flash(result.message, "success" if result.ok else "error")
        if result.code == "NOT_FOUND":
            return redirect(url_for("admin_accounts"))
        return redirect(url_for("admin_account_view", account_id=request.accountId))


# ------------------------------------------------------------------ profiles
class SearchUserProfilesPanel:
    # Sets up the panel with the controller that lists and searches profiles.
    def __init__(self):
        self.controller = SearchUserProfileController()

    # US51: runs the profile search (or the full list) and shows the chosen page.
    def submitSearch(self, request, page=None):
        return self.displayResult(self.controller.execute(request), request, page)

    # Shows the profiles for one page of 20, with errors, the search box and page links.
    def displayResult(self, result, request, page=None):
        if not result.ok:
            flash(result.message, "error")
        rows, pager, error = paginate(result.data or [], page)
        if error:
            flash(error, "error")
        keyword = request.keyword if request else ""
        return render("admin/profiles.html", result=result, rows=rows, pager=pager,
                      params={"keyword": keyword} if keyword else {}, keyword=keyword)


class CreateUserProfileForm:
    # Sets up the form with the controller that creates profiles.
    def __init__(self):
        self.controller = CreateUserProfileController()

    # US47: shows the Create User Profile form (role name, Based on, description).
    def show(self, form=None):
        return render("admin/profile_form.html", heading="Create User Profile", form=form or {}, creating=True)

    # US47: sends the new profile to the controller and shows the outcome.
    def submit(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Opens the new profile on success, or shows the form again with the error.
    def displayResult(self, result, request):
        if result.ok:
            flash(result.message, "success")
            return redirect(url_for("admin_profile_view", profile_id=result.data.profileId))
        flash(result.message, "error")
        return self.show(vars(request))


class ViewUserProfilePanel:
    # Sets up the panel with the controller that reads one profile.
    def __init__(self):
        self.controller = ViewUserProfileController()

    # US48: asks the controller for one profile and its account count.
    def requestDetails(self, request):
        return self.displayResult(self.controller.execute(request))

    # Shows the profile page, or returns to the list with an error if it no longer exists.
    def displayResult(self, result):
        if not result.ok:
            flash(result.message, "error")
            return redirect(url_for("admin_profiles"))
        return render("admin/profile_view.html", profile=result.data["profile"],
                      accountCount=result.data["accountCount"])


class UpdateUserProfileForm:
    # Sets up the form with the controller that updates profile descriptions.
    def __init__(self):
        self.controller = UpdateUserProfileController()

    # US49: shows the edit form; only the description can be changed.
    def show(self, profileId, form=None):
        current = ViewUserProfileController().execute(ProfileIdRequest(profileId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_profiles"))
        profile = current.data["profile"]
        description = profile.description if form is None else form["description"]
        return render("admin/profile_form.html", heading="Update User Profile",
                      form={"displayName": profile.roleName, "description": description},
                      profile=profile, creating=False, profileId=profileId)

    # US49: sends the new description to the controller and shows the outcome.
    def submit(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Returns to the profile page on success, or shows the form again with the error.
    def displayResult(self, result, request):
        if result.ok:
            flash(result.message, "success")
            return redirect(url_for("admin_profile_view", profile_id=request.profileId))
        flash(result.message, "error")
        return self.show(request.profileId, vars(request))


class SuspendUserProfileDialog:
    # Sets up the dialog with the controller that suspends profiles.
    def __init__(self):
        self.controller = SuspendUserProfileController()

    # US50: asks to confirm, saying how many accounts will be blocked; built-in profiles are refused.
    def askConfirmation(self, profileId):
        current = ViewUserProfileController().execute(ProfileIdRequest(profileId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_profiles"))
        profile, count = current.data["profile"], current.data["accountCount"]
        if profile.isBuiltIn:
            flash("Built-in profiles cannot be suspended.", "error")
            return redirect(url_for("admin_profile_view", profile_id=profileId))
        return render("shared/confirm.html", heading="Suspend This Profile?",
                      message=f"Every account with the {profile.roleName} profile will be logged out and blocked "
                              f"from logging in. This will log out and block {plural(count, 'account')}.",
                      confirm_label="Suspend", action=url_for("admin_profile_suspend", profile_id=profileId),
                      cancel=url_for("admin_profile_view", profile_id=profileId), danger=True)

    # US50: suspends the profile after the User Admin confirms.
    def confirm(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the outcome message on the profile page.
    def displayResult(self, result, request):
        flash(result.message, "success" if result.ok else "error")
        return redirect(url_for("admin_profile_view", profile_id=request.profileId))


class ReactivateUserProfileDialog:
    """US61 Reactivate User Profile: confirm, then accounts with the profile can log in again."""

    # Sets up the dialog with the controller that reactivates profiles.
    def __init__(self):
        self.controller = ReactivateUserProfileController()

    # US61: asks the User Admin to confirm reactivating this profile.
    def askConfirmation(self, profileId):
        current = ViewUserProfileController().execute(ProfileIdRequest(profileId))
        if not current.ok:
            flash(current.message, "error")
            return redirect(url_for("admin_profiles"))
        profile, count = current.data["profile"], current.data["accountCount"]
        return render("shared/confirm.html", heading="Reactivate This Profile?",
                      message=f"Active accounts with the {profile.roleName} profile ({plural(count, 'account')} "
                              "in total) will be able to log in again.",
                      confirm_label="Reactivate", action=url_for("admin_profile_reactivate", profile_id=profileId),
                      cancel=url_for("admin_profile_view", profile_id=profileId))

    # US61: reactivates the profile after the User Admin confirms.
    def confirm(self, request):
        return self.displayResult(self.controller.execute(request), request)

    # Shows the outcome on the profile page (or the list if the profile is gone).
    def displayResult(self, result, request):
        flash(result.message, "success" if result.ok else "error")
        if result.code == "NOT_FOUND":
            return redirect(url_for("admin_profiles"))
        return redirect(url_for("admin_profile_view", profile_id=request.profileId))
