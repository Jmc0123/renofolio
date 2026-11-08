"""US42-US51 (User Admin) and US52-US59 (Platform Manager)."""
from datetime import timedelta

import pytest

from app.common import clock
from app.common.request_types import (CreateAccountRequest, AccountIdRequest, UpdateAccountRequest,
                                      SearchAccountsRequest, CreateProfileRequest, ProfileIdRequest,
                                      UpdateProfileRequest, SearchProfilesRequest, LoginRequest, CategoryRequest,
                                      SearchCategoriesRequest, ReportRequest, IDPIdRequest, FavouriteRequest)
from app.control.browse_controllers import ViewIDPDetailsController
from app.control.favourite_controllers import SaveFavouriteController
from app.control.login_controllers import UserAdminLoginController, PlatformManagerLoginController, \
    CustomerLoginController
from app.control.platform_controllers import (ViewCategoriesController, CreateCategoryController,
                                              UpdateCategoryController, RemoveCategoryController,
                                              SearchCategoriesController, GenerateDailyReportController,
                                              GenerateWeeklyReportController, GenerateMonthlyReportController)
from app.control.user_admin_controllers import (CreateUserAccountController, ViewUserAccountController,
                                                UpdateUserAccountController, SuspendUserAccountController,
                                                SearchUserAccountController, CreateUserProfileController,
                                                ViewUserProfileController, UpdateUserProfileController,
                                                SuspendUserProfileController, SearchUserProfileController)
from app.entity.user_profiles import UserProfiles
from tests.conftest import PASSWORD, make_customer, make_designer, make_category, make_project


# Returns the profile ID for a built-in role code.
def profile_id(code):
    return UserProfiles().findByRoleCode(code).profileId


# Creates a staff account with the given role and returns the result.
def staff(email="mgr@example.test", role="PLATFORM_MANAGER"):
    return CreateUserAccountController().execute(
        CreateAccountRequest("Mia Manager", email, PASSWORD, profile_id(role), "91234567"))


# ---------------------------------------------------------------- US42-US46 accounts
class TestUserAccounts:
    # US42-US46: checks create staff account can log in.
    def test_create_staff_account_can_log_in(self):
        result = staff()
        assert result.ok and result.code == "CREATED"
        assert PlatformManagerLoginController().execute(LoginRequest("mgr@example.test", PASSWORD)).ok

    # US42-US46: checks create rejects customer profile.
    def test_create_rejects_customer_profile(self):
        assert staff(role="CUSTOMER").code == "INVALID_PROFILE"

    # US42-US46: checks a duplicate email is refused.
    def test_create_duplicate(self):
        staff()
        assert staff(email="MGR@example.test").code == "DUPLICATE"

    # US42-US46: checks invalid details are refused.
    @pytest.mark.parametrize("name,email,password,contact", [
        ("", "a@b.co", PASSWORD, "91234567"), ("Name", "bad", PASSWORD, "91234567"),
        ("Name", "a@b.co", "short", "91234567"), ("Name", "a@b.co", PASSWORD, ""),
    ])
    def test_create_invalid(self, name, email, password, contact):
        request = CreateAccountRequest(name, email, password, profile_id("USER_ADMIN"), contact)
        assert CreateUserAccountController().execute(request).code == "INVALID_INPUT"

    # US42-US46: checks an account can be viewed and updated.
    def test_view_and_update(self):
        account_id = staff().data["accountId"]
        assert ViewUserAccountController().execute(AccountIdRequest(account_id)).data["name"] == "Mia Manager"
        result = UpdateUserAccountController().execute(
            UpdateAccountRequest(account_id, "Mia M.", "mia@example.test", "91234567"))
        assert result.ok and result.data["roleCode"] == "PLATFORM_MANAGER" and result.data["email"] == "mia@example.test"
        assert ViewUserAccountController().execute(AccountIdRequest(999)).code == "NOT_FOUND"
        assert ViewUserAccountController().execute(AccountIdRequest("x")).code == "INVALID_INPUT"

    # US42-US46: checks a suspended account cannot log in.
    def test_suspend_blocks_login(self):
        account_id = staff().data["accountId"]
        admin_id = staff(email="admin@example.test", role="USER_ADMIN").data["accountId"]
        request = AccountIdRequest(account_id, actorAccountId=admin_id)
        assert SuspendUserAccountController().execute(request).ok
        assert PlatformManagerLoginController().execute(LoginRequest("mgr@example.test", PASSWORD)).code == "SUSPENDED"
        assert SuspendUserAccountController().execute(request).code == "ALREADY_SUSPENDED"

    # US42-US46: checks search by name email or profile.
    def test_search_by_name_email_or_profile(self):
        staff()
        make_customer()
        assert len(SearchUserAccountController().execute(SearchAccountsRequest("mia")).data) == 1
        assert len(SearchUserAccountController().execute(SearchAccountsRequest("example.test")).data) == 2
        by_profile = SearchUserAccountController().execute(SearchAccountsRequest("", profile_id("CUSTOMER")))
        assert [a["email"] for a in by_profile.data] == ["amy@example.test"]
        assert SearchUserAccountController().execute(SearchAccountsRequest("nobody")).code == "EMPTY"


# ---------------------------------------------------------------- US47-US51 profiles
class TestUserProfiles:
    # US47-US51: checks a record can be created, viewed and updated.
    def test_create_view_update(self):
        result = CreateUserProfileController().execute(CreateProfileRequest("Support", "Helps users", "PLATFORM_MANAGER"))
        assert result.ok and result.data.isActive
        pid = result.data.profileId
        assert ViewUserProfileController().execute(ProfileIdRequest(pid)).data["profile"].roleName == "Support"
        assert UpdateUserProfileController().execute(UpdateProfileRequest(pid, "Helps staff")).ok
        updated = ViewUserProfileController().execute(ProfileIdRequest(pid)).data["profile"]
        assert updated.roleName == "Support" and updated.description == "Helps staff"

    # US47-US51: checks invalid details are refused.
    @pytest.mark.parametrize("name,description", [("", "Description"), (" ", ""), ("Support", "x" * 501)])
    def test_create_invalid(self, name, description):
        assert CreateUserProfileController().execute(CreateProfileRequest(name, description)).code == "INVALID_INPUT"

    # US47-US51: checks create duplicate role name.
    def test_create_duplicate_role_name(self):
        assert CreateUserProfileController().execute(
            CreateProfileRequest(" customer ", "Dup", "PLATFORM_MANAGER")).code == "DUPLICATE"

    # Since 8 November built-in profiles cannot be suspended, so a custom staff profile is used here.
    def test_suspend_profile_blocks_all_its_accounts(self):
        pid = CreateUserProfileController().execute(
            CreateProfileRequest("Night Team", "", "PLATFORM_MANAGER")).data.profileId
        for email in ("amy@example.test", "ben@example.test"):
            assert CreateUserAccountController().execute(
                CreateAccountRequest("Night Staff", email, PASSWORD, pid, "91234567")).ok
        assert SuspendUserProfileController().execute(ProfileIdRequest(pid, actorAccountId=999)).ok
        for email in ("amy@example.test", "ben@example.test"):
            assert PlatformManagerLoginController().execute(LoginRequest(email, PASSWORD)).code == "SUSPENDED"
        make_customer("cara@example.test", "Cara")
        built_in = SuspendUserProfileController().execute(ProfileIdRequest(profile_id("CUSTOMER"), actorAccountId=999))
        assert built_in.code == "BUILT_IN_PROFILE"
        # make_customer() used a fresh email, so this customer logs in normally: the Customer profile is unchanged.
        assert CustomerLoginController().execute(LoginRequest("cara@example.test", PASSWORD)).ok

    # US47-US51: checks search finds matches, lists all and rejects a blank keyword.
    def test_search(self):
        assert len(SearchUserProfileController().execute(SearchProfilesRequest("manager")).data) == 1
        assert len(SearchUserProfileController().execute().data) == 4
        assert SearchUserProfileController().execute(SearchProfilesRequest("unmatched")).code == "EMPTY"
        assert SearchUserProfileController().execute(SearchProfilesRequest(" ")).code == "INVALID_INPUT"


# ---------------------------------------------------------------- US52-US56 categories
class TestCategories:
    # US52-US56: checks a category can be created, viewed, renamed and searched.
    def test_create_view_update_search(self):
        assert ViewCategoriesController().execute().code == "EMPTY"
        cid = CreateCategoryController().execute(CategoryRequest(name="Japandi Bedroom")).data["categoryId"]
        assert [c.name for c in ViewCategoriesController().execute().data] == ["Japandi Bedroom"]
        assert UpdateCategoryController().execute(CategoryRequest(cid, "Japandi Master Bedroom")).ok
        assert SearchCategoriesController().execute(SearchCategoriesRequest("master")).data[0].categoryId == cid
        assert SearchCategoriesController().execute(SearchCategoriesRequest("zzz")).code == "EMPTY"
        assert SearchCategoriesController().execute(SearchCategoriesRequest("")).code == "INVALID_INPUT"

    # US52-US56: checks blank or too-long names are refused.
    @pytest.mark.parametrize("name", ["", " ", "x" * 51])
    def test_invalid_name(self, name):
        assert CreateCategoryController().execute(CategoryRequest(name=name)).code == "INVALID_INPUT"

    # US52-US56: checks duplicate name ignores case.
    def test_duplicate_name_ignores_case(self):
        CreateCategoryController().execute(CategoryRequest(name="Coastal Kitchen"))
        assert CreateCategoryController().execute(CategoryRequest(name="coastal kitchen")).code == "DUPLICATE"

    # US52-US56: checks remove unused and in use.
    def test_remove_unused_and_in_use(self):
        used, unused = make_category("Used"), make_category("Unused")
        designer, _ = make_designer()
        make_project(designer, used)
        assert RemoveCategoryController().execute(CategoryRequest(categoryId=used)).code == "IN_USE"
        assert RemoveCategoryController().execute(CategoryRequest(categoryId=unused)).ok
        assert RemoveCategoryController().execute(CategoryRequest(categoryId=unused)).code == "NOT_FOUND"


# ---------------------------------------------------------------- US57-US59 reports
class TestReports:
    # US57-US59: checks daily, weekly and monthly reports count correctly.
    def test_daily_weekly_monthly_counts(self, frozen_clock):
        designer, _ = make_designer()
        idp = make_project(designer, make_category())
        customer = make_customer()
        ViewIDPDetailsController().execute(IDPIdRequest(idp, customer))
        SaveFavouriteController().execute(FavouriteRequest(customer, idp))
        clock.freeze(frozen_clock + timedelta(days=3))

        day = GenerateDailyReportController().execute(ReportRequest("2026-10-15")).data["summary"]
        assert day == {"newAccounts": 2, "newProjects": 1, "projectViews": 1, "newSaves": 1}
        assert GenerateDailyReportController().execute(ReportRequest("2026-10-14")).data["summary"]["projectViews"] == 0
        week = GenerateWeeklyReportController().execute(ReportRequest("2026-W42")).data
        assert week["summary"] == day
        month = GenerateMonthlyReportController().execute(ReportRequest("2026-10")).data
        assert month["title"] == "Monthly Report - October 2026"

    # US57-US59: checks a missing or wrong period is refused.
    @pytest.mark.parametrize("controller_class,value", [(GenerateDailyReportController, "15/10/2026"),
                                                        (GenerateWeeklyReportController, "2026-W99"),
                                                        (GenerateMonthlyReportController, "")])
    def test_invalid_period(self, controller_class, value):
        assert controller_class().execute(ReportRequest(value)).code == "INVALID_INPUT"

    # US57-US59: checks valid period without activity shows zero.
    def test_valid_period_without_activity_shows_zero(self, frozen_clock):
        report = GenerateMonthlyReportController().execute(ReportRequest("2027-01"))
        assert report.ok
        assert report.data["summary"] == {"newAccounts": 0, "newProjects": 0, "projectViews": 0, "newSaves": 0}
