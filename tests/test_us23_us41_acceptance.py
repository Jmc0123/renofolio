"""US23-US41 acceptance checks written from the updated SoftwareAss.docx use cases and B-C-E diagrams.

Classes, requests and entity methods are looked up by the names in the design, inside each test, so a
missing name fails only the tests that need it. These tests were run against the unchanged 3 November
code first (TDD red) and kept as the regression suite afterwards.
"""
import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.common import clock
from app.common.request_types import LoginRequest, FavouriteRequest
from app.control.favourite_controllers import SaveFavouriteController, RemoveFavouriteController
from app.control.login_controllers import DesignerLoginController
from tests.conftest import PASSWORD, make_customer, make_designer, make_category

CONTROL_MODULES = ("app.control.designer_controllers", "app.control.interest_controllers")


# Creates a controller by its design name, failing clearly if it does not exist.
def C(name):
    """Controller from the design, e.g. C('FilterMyIDPsController')."""
    for module in CONTROL_MODULES:
        mod = importlib.import_module(module)
        if hasattr(mod, name):
            return getattr(mod, name)()
    raise AssertionError(f"Controller {name} from the design is not implemented")


# Creates a request object by its design name.
def R(name, **fields):
    """Request object from the design, e.g. R('ProjectStatRequest', sessionId=..., idpId=...)."""
    mod = importlib.import_module("app.common.request_types")
    assert hasattr(mod, name), f"Request type {name} from the design is not implemented"
    return getattr(mod, name)(**fields)


# Creates an entity collection by module and class name.
def E(module, name):
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        raise AssertionError(f"Entity module {module} from the design is not implemented")
    assert hasattr(mod, name), f"Entity {name} from the design is not implemented"
    return getattr(mod, name)()


# Returns an entity method named in the design, failing clearly if it is missing.
def entity_method(module, cls, method):
    obj = E(module, cls)
    assert hasattr(obj, method), f"{cls}.{method}() from the design is not implemented"
    return getattr(obj, method)


COMPANY = dict(companyName="Studio Lim Interiors", description="Modern and Scandinavian homes",
               address="12 Kaki Bukit Rd, #03-05", contactEmail="hello@studiolim.sg", contactNumber="+6561234567",
               website="https://studiolim.sg")


# Builds a company request with sample values that tests can override.
def company_request(session_id, kind="CompanyInfoRequest", **overrides):
    return R(kind, sessionId=session_id, **dict(COMPANY, **overrides))


# Creates a project through the controller and returns its ID.
def new_project(session_id, category_id, title="Bright Family Kitchen", status="CURRENT", budget="21000",
                description="Open kitchen with an island"):
    result = C("CreateIDPController").execute(R(
        "CreateIDPRequest", sessionId=session_id, title=title, description=description, categoryId=category_id,
        projectStatus=status, budget=budget, photoUrl=""))
    assert result.ok, result
    return result.data["idpId"]


# Adds a project view at a given time.
def add_view(db, idp_id, customer_id, when):
    db.execute("INSERT INTO project_views (idp_id, customer_id, viewed_at) VALUES (?, ?, ?)",
               (idp_id, customer_id, when.strftime(clock.TIME_FORMAT)))


# Adds a favourite save (and optional removal) at given times.
def add_save(db, idp_id, customer_id, when, removed=None):
    db.execute("INSERT INTO favourites (customer_id, idp_id, saved_at, removed_at) VALUES (?, ?, ?, ?)",
               (customer_id, idp_id, when.strftime(clock.TIME_FORMAT),
                removed.strftime(clock.TIME_FORMAT) if removed else None))


# Returns a customer's account ID by email.
def customer_id(db, email="amy@example.test"):
    return db.scalar("SELECT account_id FROM user_accounts WHERE email = ?", (email,))


# ============================================================ US23-US25 company information
class TestUS23CreateCompanyInformation:
    # US23: checks normal flow saves one record.
    def test_normal_flow_saves_one_record(self, fresh_db):
        session_id, designer_id = make_designer(with_company=False)
        result = C("CreateCompanyInfoController").execute(company_request(session_id))
        assert result.ok and result.message == "Company information saved."
        assert entity_method("app.entity.companies", "Companies", "hasCompany")(designer_id) is True
        row = fresh_db.query_one("SELECT * FROM companies WHERE designer_id = ?", (designer_id,))
        assert row["contact_email"] == "hello@studiolim.sg" and row["contact_number"] == "+6561234567"

    # US23: checks invalid details are rejected and nothing is saved.
    @pytest.mark.parametrize("field,value,message", [
        ("companyName", "", None), ("contactEmail", "", None), ("contactNumber", "", None),
        ("contactEmail", "hello-at-studio", "Please enter a valid contact email."),
        ("contactNumber", "12ab", None)])
    def test_invalid_details_save_nothing(self, fresh_db, field, value, message):
        session_id, _ = make_designer(with_company=False)
        result = C("CreateCompanyInfoController").execute(company_request(session_id, **{field: value}))
        assert result.code == "INVALID_INPUT"
        if message:
            assert result.message == message
        assert fresh_db.scalar("SELECT COUNT(*) FROM companies") == 0

    # US23: checks company already exists.
    def test_company_already_exists(self, fresh_db):
        session_id, _ = make_designer(with_company=False)
        C("CreateCompanyInfoController").execute(company_request(session_id))
        again = C("CreateCompanyInfoController").execute(company_request(session_id, companyName="Other"))
        assert not again.ok and again.message == "Company information already exists. Use Edit instead."
        assert fresh_db.scalar("SELECT company_name FROM companies") == "Studio Lim Interiors"

    # US23: checks session expired and wrong role save nothing.
    def test_session_expired_and_wrong_role_save_nothing(self, fresh_db):
        assert C("CreateCompanyInfoController").execute(company_request("expired")).code == "SESSION_EXPIRED"
        customer_session = make_customer()
        assert not C("CreateCompanyInfoController").execute(company_request(customer_session)).ok
        assert fresh_db.scalar("SELECT COUNT(*) FROM companies") == 0

    # US23: checks schema matches relational model.
    def test_schema_matches_relational_model(self, fresh_db):
        columns = {r["name"]: r for r in fresh_db.query("PRAGMA table_info(companies)")}
        for name in ("company_id", "designer_id", "company_name", "description", "address", "contact_email",
                     "contact_number", "website", "updated_at"):
            assert name in columns, name
        for required in ("company_name", "contact_email", "contact_number", "updated_at"):
            assert columns[required]["notnull"] == 1, required


class TestUS24ViewCompanyInformation:
    # US24: checks normal flow shows all details.
    def test_normal_flow_shows_all_details(self):
        session_id, _ = make_designer(with_company=False)
        C("CreateCompanyInfoController").execute(company_request(session_id))
        result = C("ViewCompanyInfoController").execute(R("ViewCompanyInfoRequest", sessionId=session_id))
        assert result.ok
        for key, value in COMPANY.items():
            assert result.data[key] == value

    # US24: checks no company information yet.
    def test_no_company_information_yet(self):
        session_id, _ = make_designer(with_company=False)
        result = C("ViewCompanyInfoController").execute(R("ViewCompanyInfoRequest", sessionId=session_id))
        assert not result.ok and result.message == "You have not added company information yet."

    # US24: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        result = C("ViewCompanyInfoController").execute(R("ViewCompanyInfoRequest", sessionId="expired"))
        assert result.code == "SESSION_EXPIRED"


class TestUS25UpdateCompanyInformation:
    # US25: checks normal flow updates and customers see it.
    def test_normal_flow_updates_and_customers_see_it(self, fresh_db):
        session_id, designer_id = make_designer(with_company=False)
        C("CreateCompanyInfoController").execute(company_request(session_id))
        result = C("UpdateCompanyInfoController").execute(
            company_request(session_id, "UpdateCompanyInfoRequest", companyName="Studio Lim Design"))
        assert result.ok and result.message == "Company information updated."
        public = C("ViewDesignerCompanyInfoController").execute(R("DesignerIdRequest", designerId=designer_id))
        assert public.data["companyName"] == "Studio Lim Design"

    # US25: checks invalid details are rejected.
    def test_invalid_details(self, fresh_db):
        session_id, _ = make_designer(with_company=False)
        C("CreateCompanyInfoController").execute(company_request(session_id))
        result = C("UpdateCompanyInfoController").execute(
            company_request(session_id, "UpdateCompanyInfoRequest", contactEmail="bad"))
        assert result.code == "INVALID_INPUT" and result.message == "Please enter a valid contact email."
        assert fresh_db.scalar("SELECT contact_email FROM companies") == "hello@studiolim.sg"

    # US25: checks no company to update.
    def test_no_company_to_update(self):
        session_id, _ = make_designer(with_company=False)
        result = C("UpdateCompanyInfoController").execute(company_request(session_id, "UpdateCompanyInfoRequest"))
        assert not result.ok and "create" in result.message.lower()

    # US25: checks only own company changes.
    def test_only_own_company_changes(self, fresh_db):
        dan, _ = make_designer(with_company=False)
        eve, _ = make_designer("eve@example.test", "Eve", with_company=False)
        C("CreateCompanyInfoController").execute(company_request(dan))
        C("CreateCompanyInfoController").execute(company_request(eve, companyName="Eve Studio"))
        C("UpdateCompanyInfoController").execute(company_request(eve, "UpdateCompanyInfoRequest", companyName="Eve 2"))
        names = sorted(r["company_name"] for r in fresh_db.query("SELECT company_name FROM companies"))
        assert names == ["Eve 2", "Studio Lim Interiors"]

    # US25: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        result = C("UpdateCompanyInfoController").execute(company_request("expired", "UpdateCompanyInfoRequest"))
        assert result.code == "SESSION_EXPIRED"


# ============================================================ US26-US31 portfolio
class TestUS26CreateIDP:
    # US26: checks normal flow customers can find it.
    def test_normal_flow_customers_can_find_it(self):
        session_id, _ = make_designer()
        category = make_category()
        result = C("CreateIDPController").execute(R(
            "CreateIDPRequest", sessionId=session_id, title="Bright Family Kitchen", description="Island",
            categoryId=category, projectStatus="CURRENT", budget="21000", photoUrl=""))
        assert result.ok and result.message == "Project created successfully."
        from app.common.request_types import BrowseIDPsRequest
        from app.control.browse_controllers import BrowseIDPsController
        assert BrowseIDPsController().execute(BrowseIDPsRequest(1)).data["total"] == 1

    # US26: checks invalid details are rejected and nothing is saved.
    @pytest.mark.parametrize("field,value,message", [
        ("budget", "-500", "Budget must be between S$0 and S$10,000,000."), ("title", "", None), ("categoryId", "", None),
        ("projectStatus", "DONE", None)])
    def test_invalid_details_save_nothing(self, fresh_db, field, value, message):
        session_id, _ = make_designer()
        fields = dict(sessionId=session_id, title="Kitchen", description="", categoryId=make_category(),
                      projectStatus="CURRENT", budget="1000", photoUrl="")
        fields[field] = value
        result = C("CreateIDPController").execute(R("CreateIDPRequest", **fields))
        assert result.code == "INVALID_INPUT"
        if message:
            assert result.message == message
        assert fresh_db.scalar("SELECT COUNT(*) FROM interior_design_projects") == 0

    # US26: checks session expired and wrong role.
    def test_session_expired_and_wrong_role(self, fresh_db):
        category = make_category()
        fields = dict(title="Kitchen", description="", categoryId=category, projectStatus="CURRENT", budget="1",
                      photoUrl="")
        assert C("CreateIDPController").execute(R("CreateIDPRequest", sessionId="x", **fields)).code == \
            "SESSION_EXPIRED"
        assert not C("CreateIDPController").execute(R("CreateIDPRequest", sessionId=make_customer(), **fields)).ok
        assert fresh_db.scalar("SELECT COUNT(*) FROM interior_design_projects") == 0


class TestUS27ViewMyIDPs:
    # US27: checks lists only own projects and opens one.
    def test_lists_only_own_projects_and_opens_one(self):
        dan, _ = make_designer()
        eve, _ = make_designer("eve@example.test", "Eve")
        category = make_category()
        mine = new_project(dan, category, "Mine")
        new_project(eve, category, "Not mine")
        listing = C("ViewMyIDPsController").execute(R("ViewMyIDPsRequest", sessionId=dan))
        assert [p["title"] for p in listing.data] == ["Mine"]
        detail = C("ViewMyIDPsController").execute(R("ViewMyIDPsRequest", sessionId=dan, idpId=mine))
        assert detail.data["title"] == "Mine"

    # US27: checks no projects yet.
    def test_no_projects_yet(self):
        dan, _ = make_designer()
        result = C("ViewMyIDPsController").execute(R("ViewMyIDPsRequest", sessionId=dan))
        assert result.message == "You have not created any projects yet."

    # US27: checks project not found or not owned.
    def test_project_not_found_or_not_owned(self):
        dan, _ = make_designer()
        eve, _ = make_designer("eve@example.test", "Eve")
        other = new_project(eve, make_category())
        for idp in (other, 99999):
            result = C("ViewMyIDPsController").execute(R("ViewMyIDPsRequest", sessionId=dan, idpId=idp))
            assert not result.ok and result.message == "This project is not available."

    # US27: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        assert C("ViewMyIDPsController").execute(R("ViewMyIDPsRequest", sessionId="x")).code == "SESSION_EXPIRED"


class TestUS28FilterMyIDPs:
    # US28: checks filters own projects by status.
    def test_filters_own_projects_by_status(self):
        dan, _ = make_designer()
        category = make_category()
        new_project(dan, category, "Now", "CURRENT")
        new_project(dan, category, "Then", "PAST")
        result = C("FilterMyIDPsController").execute(R("FilterMyIDPsRequest", sessionId=dan, status="current"))
        assert [p["title"] for p in result.data] == ["Now"]
        assert entity_method("app.entity.interior_design_projects", "InteriorDesignProjects", "filterMineByStatus")

    # US28: checks missing or invalid status.
    @pytest.mark.parametrize("status", ["", "ARCHIVED"])
    def test_missing_or_invalid_status(self, status):
        dan, _ = make_designer()
        result = C("FilterMyIDPsController").execute(R("FilterMyIDPsRequest", sessionId=dan, status=status))
        assert result.code == "INVALID_INPUT"

    # US28: checks no projects with that status.
    def test_no_projects_with_that_status(self):
        dan, _ = make_designer()
        new_project(dan, make_category(), "Now", "CURRENT")
        result = C("FilterMyIDPsController").execute(R("FilterMyIDPsRequest", sessionId=dan, status="PAST"))
        assert result.ok and result.data == [] and result.message == "You have no past projects yet."

    # US28: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        result = C("FilterMyIDPsController").execute(R("FilterMyIDPsRequest", sessionId="x", status="PAST"))
        assert result.code == "SESSION_EXPIRED"


# Builds an update-project request with sample values that tests can override.
def update_request(session_id, idp_id, category, **overrides):
    fields = dict(sessionId=session_id, idpId=idp_id, title="Bright Family Kitchen", description="Done",
                  categoryId=category, projectStatus="PAST", budget="25000", photoUrl="")
    fields.update(overrides)
    return R("UpdateIDPRequest", **fields)


class TestUS29UpdateIDP:
    # US29: checks normal flow current to past.
    def test_normal_flow_current_to_past(self, fresh_db):
        dan, _ = make_designer()
        category = make_category()
        idp = new_project(dan, category)
        result = C("UpdateIDPController").execute(update_request(dan, idp, category))
        assert result.ok and result.message == "Project updated."
        assert fresh_db.scalar("SELECT project_status FROM interior_design_projects WHERE idp_id = ?", (idp,)) == "PAST"

    # US29: checks invalid details are rejected.
    def test_invalid_details(self, fresh_db):
        dan, _ = make_designer()
        category = make_category()
        idp = new_project(dan, category)
        result = C("UpdateIDPController").execute(update_request(dan, idp, category, budget="-1"))
        assert result.message == "Budget must be between S$0 and S$10,000,000."
        assert fresh_db.scalar("SELECT budget FROM interior_design_projects") == 21000

    # US29: checks not found or not owned changes nothing.
    def test_not_found_or_not_owned_changes_nothing(self, fresh_db):
        dan, _ = make_designer()
        eve, _ = make_designer("eve@example.test", "Eve")
        category = make_category()
        others = new_project(eve, category, "Eve's")
        for idp in (others, 99999):
            result = C("UpdateIDPController").execute(update_request(dan, idp, category, title="Hacked"))
            assert not result.ok and result.message == "This project is no longer available."
        assert fresh_db.scalar("SELECT title FROM interior_design_projects") == "Eve's"
        is_owner = entity_method("app.entity.interior_design_projects", "InteriorDesignProjects", "isOwner")
        eve_id = fresh_db.scalar("SELECT account_id FROM user_accounts WHERE email = 'eve@example.test'")
        assert is_owner(eve_id, others) is True

    # US29: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        dan, _ = make_designer()
        category = make_category()
        idp = new_project(dan, category)
        assert C("UpdateIDPController").execute(update_request("x", idp, category)).code == "SESSION_EXPIRED"


class TestUS30DeleteIDP:
    # Creates two projects with views and favourites for the delete tests.
    def _setup(self, db):
        dan, _ = make_designer()
        category = make_category()
        doomed, kept = new_project(dan, category, "Doomed"), new_project(dan, category, "Kept")
        make_customer()
        amy = customer_id(db)
        now = datetime.now()
        for idp in (doomed, kept):
            add_view(db, idp, amy, now)
            add_save(db, idp, amy, now - timedelta(hours=1), removed=now)
        db.execute("INSERT INTO favourites (customer_id, idp_id, saved_at) VALUES (?, ?, ?)",
                   (amy, doomed, now.strftime(clock.TIME_FORMAT)))
        return dan, doomed, kept

    # US30: checks normal flow deletes project views and favourites.
    def test_normal_flow_deletes_project_views_and_favourites(self, fresh_db):
        dan, doomed, kept = self._setup(fresh_db)
        result = C("DeleteIDPController").execute(R("DeleteIDPRequest", sessionId=dan, idpId=doomed))
        assert result.ok and result.message == "Project deleted."
        count = lambda table, idp: fresh_db.scalar(f"SELECT COUNT(*) FROM {table} WHERE idp_id = ?", (idp,))
        assert count("interior_design_projects", doomed) == 0
        assert count("project_views", doomed) == 0 and count("favourites", doomed) == 0
        assert count("interior_design_projects", kept) == 1
        assert count("project_views", kept) == 1 and count("favourites", kept) == 1

    # US30: checks cancelling deletes nothing.
    def test_designer_cancels(self, fresh_db):
        dan, doomed, _ = self._setup(fresh_db)
        result = C("DeleteIDPController").execute(R("DeleteIDPRequest", sessionId=dan, idpId=doomed, confirmed=False))
        assert not result.ok
        assert fresh_db.scalar("SELECT COUNT(*) FROM interior_design_projects WHERE idp_id = ?", (doomed,)) == 1

    # US30: checks not found or not owned deletes nothing.
    def test_not_found_or_not_owned_deletes_nothing(self, fresh_db):
        _, doomed, _ = self._setup(fresh_db)
        eve, _ = make_designer("eve@example.test", "Eve")
        for idp in (doomed, 99999):
            result = C("DeleteIDPController").execute(R("DeleteIDPRequest", sessionId=eve, idpId=idp))
            assert not result.ok and result.message == "This project is no longer available."
        assert fresh_db.scalar("SELECT COUNT(*) FROM project_views WHERE idp_id = ?", (doomed,)) == 1

    # US30: checks an ended session is refused and nothing changes.
    def test_session_expired(self, fresh_db):
        _, doomed, _ = self._setup(fresh_db)
        assert C("DeleteIDPController").execute(R("DeleteIDPRequest", sessionId="x", idpId=doomed)).code == \
            "SESSION_EXPIRED"

    # US30: checks one transaction rolls back children if project delete fails.
    def test_one_transaction_rolls_back_children_if_project_delete_fails(self, fresh_db):
        dan, doomed, _ = self._setup(fresh_db)
        fresh_db.execute("CREATE TRIGGER block_delete BEFORE DELETE ON interior_design_projects "
                         "BEGIN SELECT RAISE(ABORT, 'blocked for test'); END")
        result = C("DeleteIDPController").execute(R("DeleteIDPRequest", sessionId=dan, idpId=doomed))
        assert not result.ok
        assert fresh_db.scalar("SELECT COUNT(*) FROM project_views WHERE idp_id = ?", (doomed,)) == 1
        assert fresh_db.scalar("SELECT COUNT(*) FROM favourites WHERE idp_id = ?", (doomed,)) == 2

    # US30: checks schema cascades from projects.
    def test_schema_cascades_from_projects(self, fresh_db):
        for table in ("project_views", "favourites"):
            keys = fresh_db.query(f"PRAGMA foreign_key_list({table})")
            idp_key = [k for k in keys if k["from"] == "idp_id"][0]
            assert idp_key["on_delete"] == "CASCADE", table


class TestUS31SearchMyIDPs:
    # US31: checks case insensitive and only own.
    def test_case_insensitive_and_only_own(self):
        dan, _ = make_designer()
        eve, _ = make_designer("eve@example.test", "Eve")
        category = make_category()
        new_project(dan, category, "Bright Family Kitchen")
        new_project(dan, category, "Modern Condo", description="Open KITCHEN plan")
        new_project(eve, category, "Eve Kitchen")
        result = C("SearchMyIDPsController").execute(R("SearchMyIDPsRequest", sessionId=dan, keyword="kitchen"))
        assert sorted(p["title"] for p in result.data) == ["Bright Family Kitchen", "Modern Condo"]

    # US31: checks empty keyword no matches literal wildcards.
    def test_empty_keyword_no_matches_literal_wildcards(self):
        dan, _ = make_designer()
        new_project(dan, make_category(), "Kitchen")
        empty = C("SearchMyIDPsController").execute(R("SearchMyIDPsRequest", sessionId=dan, keyword="  "))
        assert empty.message == "Please enter a keyword."
        none = C("SearchMyIDPsController").execute(R("SearchMyIDPsRequest", sessionId=dan, keyword="rooftop"))
        assert none.data == [] and none.message == "None of your projects match 'rooftop'."
        wildcard = C("SearchMyIDPsController").execute(R("SearchMyIDPsRequest", sessionId=dan, keyword="%"))
        assert wildcard.data == []

    # US31: checks an ended session is refused and nothing changes.
    def test_session_expired(self):
        result = C("SearchMyIDPsController").execute(R("SearchMyIDPsRequest", sessionId="x", keyword="a"))
        assert result.code == "SESSION_EXPIRED"


# ============================================================ US32-US33 customer views a designer
class TestUS32US33PublicDesigner:
    # US32/US33: checks portfolio groups and no view recorded.
    def test_portfolio_groups_and_no_view_recorded(self, fresh_db):
        dan, designer_id = make_designer()
        category = make_category()
        new_project(dan, category, "Now", "CURRENT")
        new_project(dan, category, "Then", "PAST")
        result = C("ViewDesignerPortfolioController").execute(R("DesignerIdRequest", designerId=designer_id))
        assert [p["title"] for p in result.data["current"]] == ["Now"]
        assert [p["title"] for p in result.data["past"]] == ["Then"]
        assert fresh_db.scalar("SELECT COUNT(*) FROM project_views") == 0

    # US32/US33: checks designer has no projects.
    def test_designer_has_no_projects(self):
        _, designer_id = make_designer()
        result = C("ViewDesignerPortfolioController").execute(R("DesignerIdRequest", designerId=designer_id))
        assert result.message == "This designer has no projects yet."

    # US32/US33: checks invalid designer ID.
    def test_invalid_designer_id(self):
        assert C("ViewDesignerPortfolioController").execute(R("DesignerIdRequest", designerId="abc")).code == \
            "INVALID_INPUT"
        assert C("ViewDesignerCompanyInfoController").execute(R("DesignerIdRequest", designerId="")).code == \
            "INVALID_INPUT"

    # US32/US33: checks company details exactly as entered.
    def test_company_details_exactly_as_entered(self):
        dan, designer_id = make_designer(with_company=False)
        C("CreateCompanyInfoController").execute(company_request(dan))
        result = C("ViewDesignerCompanyInfoController").execute(R("DesignerIdRequest", designerId=designer_id))
        for key, value in COMPANY.items():
            assert result.data[key] == value

    # US32/US33: checks no company information.
    def test_no_company_information(self):
        _, designer_id = make_designer(with_company=False)
        result = C("ViewDesignerCompanyInfoController").execute(R("DesignerIdRequest", designerId=designer_id))
        assert not result.ok and result.message == "This designer has not added company information yet."


# ============================================================ US34-US41 statistics
# Builds Dan's three projects and Eve's one, with views and saves on known dates, for the statistics tests.
@pytest.fixture
def stats(fresh_db):
    """Dan has three projects. Amy and Ben view and shortlist them; Eve's project must never be counted."""
    dan, dan_id = make_designer()
    eve, _ = make_designer("eve@example.test", "Eve")
    category = make_category()
    ids = {"b": new_project(dan, category, "B Loft"), "a": new_project(dan, category, "A Condo"),
           "c": new_project(dan, category, "C Study"), "eve": new_project(eve, category, "Eve Project")}
    make_customer()
    make_customer("ben@example.test", "Ben")
    amy, ben = customer_id(fresh_db), customer_id(fresh_db, "ben@example.test")
    day = datetime(2026, 10, 20, 12, 0)  # Tuesday
    for idp, n in (("b", 3), ("a", 3), ("c", 1), ("eve", 9)):
        for i in range(n):
            add_view(fresh_db, ids[idp], amy, day + timedelta(minutes=i))
    add_view(fresh_db, ids["a"], ben, datetime(2026, 10, 26, 23, 59))  # Monday next week
    add_view(fresh_db, ids["c"], ben, datetime(2026, 10, 19, 0, 0))    # Monday of this week, midnight
    add_save(fresh_db, ids["a"], amy, day)
    add_save(fresh_db, ids["c"], amy, day)
    add_save(fresh_db, ids["c"], ben, day, removed=day + timedelta(hours=1))  # removed later
    add_save(fresh_db, ids["b"], ben, datetime(2026, 9, 30, 23, 59))
    add_save(fresh_db, ids["eve"], amy, day)
    return dict(ids, session=dan, designer=dan_id, eve_session=eve, db=fresh_db)


# Builds a statistics request for a session with extra fields.
def stat_request(name, session, **fields):
    return R(name, sessionId=session, **fields)


class TestUS34US35ProjectStatistics:
    # US34/US35: checks the view count counts every view.
    def test_view_count(self, stats):
        result = C("ViewProjectViewCountController").execute(
            stat_request("ProjectStatRequest", stats["session"], idpId=stats["a"]))
        assert result.ok and result.data["viewCount"] == 4
        assert entity_method("app.entity.project_views", "ProjectViews", "countByProject")(stats["a"]) == 4

    # US34/US35: checks shortlist count only current.
    def test_shortlist_count_only_current(self, stats):
        result = C("ViewShortlistCountController").execute(
            stat_request("ProjectStatRequest", stats["session"], idpId=stats["c"]))
        assert result.ok and result.data["shortlistCount"] == 1
        assert entity_method("app.entity.favourites", "Favourites", "countCurrent")(stats["c"]) == 1

    # US34/US35: checks invalid, not-owned and ended-session requests are refused.
    @pytest.mark.parametrize("controller", ["ViewProjectViewCountController", "ViewShortlistCountController"])
    def test_alternative_flows(self, stats, controller):
        assert C(controller).execute(stat_request("ProjectStatRequest", stats["session"], idpId="")).code == \
            "INVALID_INPUT"
        not_owned = C(controller).execute(stat_request("ProjectStatRequest", stats["session"], idpId=stats["eve"]))
        assert not not_owned.ok and not_owned.message == "This project is not available."
        assert C(controller).execute(stat_request("ProjectStatRequest", "x", idpId=stats["a"])).code == \
            "SESSION_EXPIRED"

    # US34/US35: checks zero when no activity.
    def test_zero_when_no_activity(self, stats):
        dan = stats["session"]
        fresh = new_project(dan, make_category("Coastal Bathroom"), "Fresh")
        views = C("ViewProjectViewCountController").execute(stat_request("ProjectStatRequest", dan, idpId=fresh))
        saves = C("ViewShortlistCountController").execute(stat_request("ProjectStatRequest", dan, idpId=fresh))
        assert views.data["viewCount"] == 0 and saves.data["shortlistCount"] == 0


class TestUS36US37US38InterestSummary:
    # Returns the summary rows as (title, views, shortlists).
    def _rows(self, controller, session):
        result = C(controller).execute(stat_request("InterestSummaryRequest", session))
        assert result.ok, result
        return [(r["title"], r["viewCount"], r["shortlistCount"]) for r in result.data]

    # US36/US37/US38: checks summary matches US34 US35 and excludes others.
    def test_summary_matches_us34_us35_and_excludes_others(self, stats):
        rows = {t: (v, s) for t, v, s in self._rows("ViewInterestSummaryController", stats["session"])}
        assert rows == {"A Condo": (4, 1), "B Loft": (3, 1), "C Study": (2, 1)}
        for name in ("countPerProject", "countCurrentPerProject"):
            module = "app.entity.project_views" if name == "countPerProject" else "app.entity.favourites"
            cls = "ProjectViews" if name == "countPerProject" else "Favourites"
            assert entity_method(module, cls, name)

    # US36/US37/US38: checks sort by views ties by title.
    def test_sort_by_views_ties_by_title(self, stats):
        add_view(stats["db"], stats["b"], customer_id(stats["db"]), datetime(2026, 10, 21))  # B ties A on 4
        titles = [t for t, _, _ in self._rows("SortByViewCountController", stats["session"])]
        assert titles == ["A Condo", "B Loft", "C Study"]

    # US36/US37/US38: checks sort by shortlists ties by title.
    def test_sort_by_shortlists_ties_by_title(self, stats):
        titles = [t for t, _, _ in self._rows("SortByShortlistCountController", stats["session"])]
        assert titles == ["A Condo", "B Loft", "C Study"]  # all have 1 current shortlist
        add_save(stats["db"], stats["c"], customer_id(stats["db"], "ben@example.test"), datetime(2026, 10, 22))
        titles = [t for t, _, _ in self._rows("SortByShortlistCountController", stats["session"])]
        assert titles == ["C Study", "A Condo", "B Loft"]

    # US36/US37/US38: checks no projects and session expired.
    @pytest.mark.parametrize("controller", ["ViewInterestSummaryController", "SortByViewCountController",
                                            "SortByShortlistCountController"])
    def test_no_projects_and_session_expired(self, controller):
        dan, _ = make_designer()
        empty = C(controller).execute(stat_request("InterestSummaryRequest", dan))
        assert empty.data == [] and empty.message == "You have no projects yet."
        assert C(controller).execute(stat_request("InterestSummaryRequest", "x")).code == "SESSION_EXPIRED"


class TestUS39US40PeriodStatistics:
    # Returns the period counts by project title.
    def _counts(self, controller, session, period, date):
        result = C(controller).execute(stat_request("PeriodStatRequest", session, period=period, date=date))
        assert result.ok, result
        return {r["title"]: r["count"] for r in result.data["rows"]}

    # US39/US40: checks views day week month boundaries.
    def test_views_day_week_month_boundaries(self, stats):
        s = stats["session"]
        assert self._counts("ViewPeriodViewsController", s, "DAY", "2026-10-20") == \
            {"A Condo": 3, "B Loft": 3, "C Study": 1}
        # Week Monday 19 Oct 00:00 to Sunday 25 Oct: includes the Monday-midnight view, excludes 26 Oct
        assert self._counts("ViewPeriodViewsController", s, "WEEK", "2026-10-22") == \
            {"A Condo": 3, "B Loft": 3, "C Study": 2}
        assert self._counts("ViewPeriodViewsController", s, "MONTH", "2026-10-05") == \
            {"A Condo": 4, "B Loft": 3, "C Study": 2}

    # US39/US40: checks projects with no views show zero.
    def test_projects_with_no_views_show_zero(self, stats):
        assert self._counts("ViewPeriodViewsController", stats["session"], "DAY", "2026-10-01") == \
            {"A Condo": 0, "B Loft": 0, "C Study": 0}

    # US39/US40: checks new saves count even if removed later.
    def test_new_saves_count_even_if_removed_later(self, stats):
        s = stats["session"]
        assert self._counts("ViewPeriodSavesController", s, "DAY", "2026-10-20") == \
            {"A Condo": 1, "B Loft": 0, "C Study": 2}
        assert self._counts("ViewPeriodSavesController", s, "MONTH", "2026-09-30") == \
            {"A Condo": 0, "B Loft": 1, "C Study": 0}

    # US39/US40: checks missing period or date.
    @pytest.mark.parametrize("controller", ["ViewPeriodViewsController", "ViewPeriodSavesController"])
    @pytest.mark.parametrize("period,date,message", [
        ("", "2026-10-20", "Please choose a period and a date."), ("WEEK", "", "Please choose a period and a date."),
        ("YEAR", "2026-10-20", "Please choose a period and a date."),
        ("DAY", "2026-13-40", "Please choose a valid date.")])  # 8 November: an impossible date is named as such
    def test_missing_period_or_date(self, stats, controller, period, date, message):
        result = C(controller).execute(stat_request("PeriodStatRequest", stats["session"], period=period, date=date))
        assert result.code == "INVALID_INPUT" and result.message == message

    # US39/US40: checks no projects and session expired.
    @pytest.mark.parametrize("controller", ["ViewPeriodViewsController", "ViewPeriodSavesController"])
    def test_no_projects_and_session_expired(self, controller):
        dan, _ = make_designer()
        empty = C(controller).execute(stat_request("PeriodStatRequest", dan, period="DAY", date="2026-10-20"))
        assert empty.message == "You have no projects yet."
        expired = C(controller).execute(stat_request("PeriodStatRequest", "x", period="DAY", date="2026-10-20"))
        assert expired.code == "SESSION_EXPIRED"


class TestUS41PortfolioTotals:
    # US41: checks totals equal sums of US36.
    def test_totals_equal_sums_of_us36(self, stats):
        result = C("ViewPortfolioTotalsController").execute(stat_request("PortfolioTotalsRequest", stats["session"]))
        assert result.data["totalViews"] == 9 and result.data["totalShortlists"] == 3
        assert entity_method("app.entity.project_views", "ProjectViews", "countByDesigner")(stats["designer"]) == 9
        assert entity_method("app.entity.favourites", "Favourites", "countCurrentByDesigner")(stats["designer"]) == 3

    # US41: checks zero when no projects and session expired.
    def test_zero_when_no_projects_and_session_expired(self):
        dan, _ = make_designer()
        result = C("ViewPortfolioTotalsController").execute(stat_request("PortfolioTotalsRequest", dan))
        assert result.ok and result.data["totalViews"] == 0 and result.data["totalShortlists"] == 0
        assert C("ViewPortfolioTotalsController").execute(stat_request("PortfolioTotalsRequest", "x")).code == \
            "SESSION_EXPIRED"


# ============================================================ pages (Boundary)
# Builds an app with a logged-in designer, one project and its company for the page tests.
@pytest.fixture
def web(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "web.db"), testing=True)
    client = app.test_client()
    dan, designer_id = make_designer()
    category = make_category()
    idp = new_project(dan, category, "Bright Family Kitchen")
    client.post("/designer/login", data={"email": "dan@example.test", "password": PASSWORD})
    return {"client": client, "idp": idp, "designer": designer_id, "category": category}


# Opens a page, follows redirects and returns its HTML.
def page(client, url, **kwargs):
    response = client.get(url, follow_redirects=True, **kwargs)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


class TestDesignerPages:
    # Designer pages: checks statistics pages exist.
    def test_statistics_pages_exist(self, web):
        c = web["client"]
        assert "Project Interest Summary" in page(c, "/designer/statistics")
        assert "Sort by Views" in page(c, "/designer/statistics")
        assert "Total Views" in page(c, f"/designer/statistics/project?idpId={web['idp']}&show=views")
        assert "Shortlisted Now" in page(c, f"/designer/statistics/project?idpId={web['idp']}&show=shortlists")
        assert "Statistics for a Period" in page(c, "/designer/statistics/period?period=WEEK&date=2026-10-20&show=views")
        assert "Portfolio Totals" in page(c, "/designer/statistics/totals")

    # Designer pages: checks delete dialog warns about views and favourites.
    def test_delete_dialog_warns_about_views_and_favourites(self, web):
        html = page(web["client"], f"/designer/projects/{web['idp']}/delete")
        assert "views and favourites are deleted too" in html

    # Designer pages: checks create project with photo upload.
    def test_create_project_with_photo_upload(self, web, fresh_db):
        import io
        png = (Path(__file__).resolve().parents[1] / "app/static/sample-projects/kitchen.png").read_bytes()
        response = web["client"].post("/designer/projects/new", data={
            "title": "Photo Project", "description": "", "categoryId": str(web["category"]), "projectStatus": "PAST",
            "budget": "5000", "photo": (io.BytesIO(png), "kitchen.png")},
            content_type="multipart/form-data", follow_redirects=True)
        assert "Project created successfully." in response.get_data(as_text=True)
        url = fresh_db.scalar("SELECT photo_url FROM interior_design_projects WHERE title = 'Photo Project'")
        assert url and url.startswith("/static/uploads/")
        stored = Path(__file__).resolve().parents[1] / "app" / url.lstrip("/")
        assert stored.exists()
        idp = fresh_db.scalar("SELECT idp_id FROM interior_design_projects WHERE title = 'Photo Project'")
        deleted = web["client"].post(f"/designer/projects/{idp}/delete", follow_redirects=True)
        assert "Project deleted." in deleted.get_data(as_text=True)
        assert not stored.exists()  # US30: the uploaded file goes with the project

    # Designer pages: checks my projects filter has all option and clear.
    def test_my_projects_filter_has_all_option_and_clear(self, web):
        html = page(web["client"], "/designer/projects?status=PAST")
        assert "You have no past projects yet." in html and "Clear All" in html

    # Designer pages: checks customer portfolio and company pages.
    def test_customer_portfolio_and_company_pages(self, web):
        from tests.conftest import make_customer as _mk  # noqa: F401
        client = web["client"]
        client.post("/designer/logout")
        make_customer()
        client.post("/customer/login", data={"email": "amy@example.test", "password": PASSWORD})
        portfolio = page(client, f"/customer/designers/{web['designer']}")
        assert "Company Information" in portfolio and "Bright Family Kitchen" in portfolio
        company = page(client, f"/customer/designers/{web['designer']}/company")
        # Since 8 November a designer must add company information before publishing a project (bug 5),
        # so the public company page shows the details instead of the "not added yet" message.
        assert "Dan Lim Studio" in company and "Back to Portfolio" in company


# ============================================================ upgrading a database made before 6 November
# Checks an older database file is upgraded without losing any rows.
def test_existing_database_is_upgraded_without_losing_rows(tmp_path):
    """Older databases have company_information (phone/email) and no cascade; init_db() upgrades them in place."""
    import sqlite3
    from app.entity.database import init_db
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE user_profiles (profile_id INTEGER PRIMARY KEY, role_code TEXT UNIQUE, role_name TEXT,
            description TEXT, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE user_accounts (account_id INTEGER PRIMARY KEY, username TEXT, name TEXT, email TEXT UNIQUE,
            password_hash TEXT, contact_number TEXT, profile_id INTEGER, status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE project_categories (category_id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE company_information (company_id INTEGER PRIMARY KEY, designer_id INTEGER UNIQUE,
            company_name TEXT, description TEXT, address TEXT, phone TEXT, email TEXT, website TEXT,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE interior_design_projects (idp_id INTEGER PRIMARY KEY, designer_id INTEGER, title TEXT,
            description TEXT, category_id INTEGER, project_status TEXT, budget REAL, photo_url TEXT,
            created_at TEXT, updated_at TEXT, removed_at TEXT);
        CREATE TABLE project_views (view_id INTEGER PRIMARY KEY, idp_id INTEGER REFERENCES interior_design_projects(idp_id),
            customer_id INTEGER, viewed_at TEXT);
        CREATE TABLE favourites (favourite_id INTEGER PRIMARY KEY, customer_id INTEGER,
            idp_id INTEGER REFERENCES interior_design_projects(idp_id), saved_at TEXT, removed_at TEXT);
        INSERT INTO user_profiles VALUES (2, 'INTERIOR_DESIGNER', 'Interior Designer', '', 'ACTIVE', 't', 't');
        INSERT INTO user_accounts VALUES (7, NULL, 'Dan', 'dan@x.test', 'h', '91234567', 2, 'ACTIVE', 't', 't');
        INSERT INTO project_categories VALUES (1, 'Kitchen');
        INSERT INTO company_information VALUES (3, 7, 'Oak', 'd', 'a', '61234567', 'oak@x.test', 'oak.sg', 't', 'u');
        INSERT INTO interior_design_projects VALUES (5, 7, 'P', '', 1, 'PAST', 1, '', 't', 't', NULL);
        INSERT INTO project_views VALUES (11, 5, 9, '2026-10-01 10:00:00');
        INSERT INTO favourites VALUES (12, 9, 5, '2026-10-01 10:00:00', NULL);
    """)
    old.commit()
    old.close()
    db = init_db(path)
    init_db(path)  # running it again changes nothing
    assert db.query("SELECT company_id, designer_id, contact_email, contact_number FROM companies") == \
        [{"company_id": 3, "designer_id": 7, "contact_email": "oak@x.test", "contact_number": "61234567"}]
    assert db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE name = 'company_information'") == 0
    assert db.scalar("SELECT COUNT(*) FROM project_views") == 1 and db.scalar("SELECT COUNT(*) FROM favourites") == 1
    for table in ("project_views", "favourites"):
        assert [k for k in db.query(f"PRAGMA foreign_key_list({table})") if k["from"] == "idp_id"][0]["on_delete"] \
            == "CASCADE"
    db.execute("DELETE FROM interior_design_projects WHERE idp_id = 5")
    assert db.scalar("SELECT COUNT(*) FROM project_views") == 0 and db.scalar("SELECT COUNT(*) FROM favourites") == 0
