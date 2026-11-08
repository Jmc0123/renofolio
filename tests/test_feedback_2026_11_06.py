"""Checks for the three issues found in testing on 6 November 2026 (written before the fixes).

1. On My Interior Design Projects, keyword search and the status filter must work together.
2. Save to Favourites (US19) keeps the Customer on the project page, shows the message, and does not
   record an extra view (US18: one view per opening).
3. The Create IDP success message is "Project created successfully."
"""
import importlib

import pytest

from app import create_app
from app.common.request_types import CreateIDPRequest
from app.control.designer_controllers import CreateIDPController
from tests.conftest import PASSWORD, make_customer, make_designer, make_category, make_project


# Builds an app with a designer, past and current kitchen projects and a customer.
@pytest.fixture
def web(tmp_path):
    app = create_app(str(tmp_path / "web.db"), testing=True)
    designer, _ = make_designer()
    category = make_category()
    ids = {
        "past_kitchen": make_project(designer, category, "Past Kitchen", "PAST"),
        "current_kitchen": make_project(designer, category, "Current Kitchen", "CURRENT"),
        "past_bedroom": make_project(designer, category, "Past Bedroom", "PAST", description="Calm room"),
    }
    make_customer()
    return {"app": app, "designer_session": designer, "ids": ids, "category": category}


# Returns a test client logged in on a role's login page.
def logged_in(app, prefix, email):
    client = app.test_client()
    client.post(f"/{prefix}/login", data={"email": email, "password": PASSWORD})
    return client


# Returns the known project titles shown on a page.
def titles(html):
    import re
    return sorted(set(re.findall(r"<strong>([^<]+)</strong>", html)) & {"Past Kitchen", "Current Kitchen", "Past Bedroom"})


# ---------------------------------------------------------------- 1. search + filter together
class TestSearchAndFilterTogether:
    # 6 Nov feedback: checks controller combines keyword and status.
    def test_controller_combines_keyword_and_status(self, web):
        module = importlib.import_module("app.control.designer_controllers")
        assert hasattr(module, "SearchAndFilterMyIDPsController"), "combined controller missing"
        requests = importlib.import_module("app.common.request_types")
        result = module.SearchAndFilterMyIDPsController().execute(
            requests.MyIDPsFiltersRequest(sessionId=web["designer_session"], keyword="kitchen", status="PAST"))
        assert result.ok and [p["title"] for p in result.data] == ["Past Kitchen"]
        none = module.SearchAndFilterMyIDPsController().execute(
            requests.MyIDPsFiltersRequest(sessionId=web["designer_session"], keyword="sofa", status="PAST"))
        assert none.data == [] and none.message == "None of your past projects match 'sofa'."

    # 6 Nov feedback: checks page applies both and keeps both values.
    def test_page_applies_both_and_keeps_both_values(self, web):
        client = logged_in(web["app"], "designer", "dan@example.test")
        html = client.get("/designer/projects?q=kitchen&status=PAST").get_data(as_text=True)
        assert titles(html) == ["Past Kitchen"]
        assert 'value="kitchen"' in html and '<option value="PAST" selected' in html

    # 6 Nov feedback: checks apply filter keeps keyword and search keeps status.
    def test_apply_filter_keeps_keyword_and_search_keeps_status(self, web):
        client = logged_in(web["app"], "designer", "dan@example.test")
        # Apply Filter with a keyword typed: both apply (Past Bedroom must not appear)
        html = client.get("/designer/projects?q=kitchen&status=PAST&action=filter").get_data(as_text=True)
        assert titles(html) == ["Past Kitchen"]
        # Search with a status chosen: both apply (Current Kitchen must not appear)
        html = client.get("/designer/projects?q=kitchen&status=PAST&action=search").get_data(as_text=True)
        assert titles(html) == ["Past Kitchen"]
        html = client.get("/designer/projects?q=room&status=PAST&action=search").get_data(as_text=True)
        assert titles(html) == ["Past Bedroom"]

    # 6 Nov feedback: checks single criteria still work.
    def test_single_criteria_still_work(self, web):
        client = logged_in(web["app"], "designer", "dan@example.test")
        assert titles(client.get("/designer/projects?status=PAST").get_data(as_text=True)) == \
            ["Past Bedroom", "Past Kitchen"]
        assert titles(client.get("/designer/projects?q=kitchen").get_data(as_text=True)) == \
            ["Current Kitchen", "Past Kitchen"]
        # With one Apply filters button, a blank keyword simply means "no keyword" (all projects).
        # US31 A1 is still enforced by the Controller itself:
        from app.common.request_types import SearchMyIDPsRequest
        from app.control.designer_controllers import SearchMyIDPsController
        result = SearchMyIDPsController().execute(SearchMyIDPsRequest(web["designer_session"], "  "))
        assert result.message == "Please enter a keyword."


# ---------------------------------------------------------------- 2. save stays on the page
class TestSaveStaysOnProjectPage:
    # Counts the recorded views of a project.
    def _views(self, db, idp):
        return db.scalar("SELECT COUNT(*) FROM project_views WHERE idp_id = ?", (idp,))

    # US19: checks background save returns message and records no extra view.
    def test_background_save_returns_message_and_records_no_extra_view(self, web, fresh_db):
        client = logged_in(web["app"], "customer", "amy@example.test")
        idp = web["ids"]["current_kitchen"]
        client.get(f"/customer/projects/{idp}")
        assert self._views(fresh_db, idp) == 1
        response = client.post(f"/customer/projects/{idp}/save", headers={"X-Requested-With": "fetch"})
        assert response.is_json and response.get_json()["ok"] is True
        assert response.get_json()["message"] == "Saved to your favourites."
        again = client.post(f"/customer/projects/{idp}/save", headers={"X-Requested-With": "fetch"}).get_json()
        assert again["ok"] is False and again["message"] == "This project is already in your favourites."
        assert self._views(fresh_db, idp) == 1

    # US19: checks without javascript returns to the same project.
    def test_without_javascript_returns_to_the_same_project(self, web):
        client = logged_in(web["app"], "customer", "amy@example.test")
        idp = web["ids"]["current_kitchen"]
        response = client.post(f"/customer/projects/{idp}/save")
        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/customer/projects/{idp}")

    # US19: checks expired session tells the page to log in.
    def test_expired_session_tells_the_page_to_log_in(self, web):
        client = web["app"].test_client()
        response = client.post(f"/customer/projects/{web['ids']['current_kitchen']}/save",
                               headers={"X-Requested-With": "fetch"})
        assert response.status_code in (302, 401)


# ---------------------------------------------------------------- 3. create message
# Checks the create-project message wording from the 6 November feedback.
def test_create_project_message(web):
    result = CreateIDPController().execute(CreateIDPRequest(
        web["designer_session"], "New", "", web["category"], "CURRENT", "100"))
    assert result.ok and result.message == "Project created successfully."
