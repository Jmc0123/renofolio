"""Shared fixtures: every test gets a fresh, empty SQLite database file."""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.common import clock  # noqa: E402
from app.common.request_types import (RegistrationRequest, LoginRequest, CreateIDPRequest, CategoryRequest,  # noqa: E402
                                      CompanyInfoRequest)
from app.control.account_controllers import CreateCustomerAccountController, CreateDesignerAccountController  # noqa: E402
from app.control.designer_controllers import CreateIDPController, CreateCompanyInfoController  # noqa: E402
from app.control.login_controllers import CustomerLoginController, DesignerLoginController  # noqa: E402
from app.control.platform_controllers import CreateCategoryController  # noqa: E402
from app.entity.database import init_db, DatabaseConnection  # noqa: E402

PASSWORD = "Password123"


# Gives every test its own empty database file and an unfrozen clock.
@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    init_db(str(tmp_path / "test.db"))
    clock.freeze(None)
    yield DatabaseConnection()
    clock.freeze(None)


# Freezes the clock at 15 Oct 2026, 10:00 so time-based tests are repeatable.
@pytest.fixture
def frozen_clock():
    moment = datetime(2026, 10, 15, 10, 0, 0)
    clock.freeze(moment)
    return moment


# ---------- helpers used by many tests ----------
# Creates and logs in a customer and returns the session ID.
def make_customer(email="amy@example.test", name="Amy Tan"):
    CreateCustomerAccountController().execute(RegistrationRequest(name, email, PASSWORD, "91234567"))
    return CustomerLoginController().execute(LoginRequest(email, PASSWORD)).data["sessionId"]


# Creates and logs in a designer (with company information unless asked not to).
def make_designer(email="dan@example.test", name="Dan Lim", with_company=True):
    CreateDesignerAccountController().execute(RegistrationRequest(name, email, PASSWORD, "98765432"))
    result = DesignerLoginController().execute(LoginRequest(email, PASSWORD))
    if with_company:
        # Since 8 November a designer needs company information before creating projects (bug 5).
        CreateCompanyInfoController().execute(CompanyInfoRequest(
            result.data["sessionId"], f"{name} Studio", "", "", email, "61234567", ""))
    return result.data["sessionId"], result.data["accountId"]


# Creates a category and returns its ID.
def make_category(name="Modern Kitchen"):
    return CreateCategoryController().execute(CategoryRequest(name=name)).data["categoryId"]


# Creates a project for a logged-in designer and returns its ID.
def make_project(session_id, category_id, title="Bright Kitchen", status="CURRENT", budget="20000",
                 description="Open kitchen with island"):
    result = CreateIDPController().execute(CreateIDPRequest(session_id, title, description, category_id, status, budget))
    assert result.ok, result
    return result.data["idpId"]
