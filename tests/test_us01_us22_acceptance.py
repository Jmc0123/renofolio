"""Acceptance/regression checks for the US01-US22 handover.

US01-US12 use SoftwareAss.docx. US13-US22 use SoftwareAss (1).docx.
Fixtures insert catalogue rows directly so these tests do not depend on
the unfinished designer/admin user stories.
"""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.common import clock
from app.common.request_types import (
    FavouriteRequest, FilterByBudgetRequest, IDPIdRequest, LoginRequest,
    SearchFavouritesRequest, SessionRequest, UpdateDetailsRequest,
)
from app.control.account_controllers import ViewPersonalDetailsController, UpdatePersonalDetailsController
from app.control.browse_controllers import FilterIDPsByBudgetController, ViewIDPDetailsController
from app.control.favourite_controllers import (
    SaveFavouriteController, ViewFavouritesController, SearchFavouritesController,
    RemoveFavouriteController,
)
from app.control.login_controllers import (
    CustomerLoginController, DesignerLoginController, UserAdminLoginController,
    PlatformManagerLoginController, CustomerLogoutController, DesignerLogoutController,
    UserAdminLogoutController, PlatformManagerLogoutController,
)
from app.entity.sessions import Sessions

PASSWORD = "Password123"
ROLES = [
    ("customer", "CUSTOMER", CustomerLoginController, CustomerLogoutController, "/customer/home"),
    ("designer", "INTERIOR_DESIGNER", DesignerLoginController, DesignerLogoutController, "/designer/home"),
    ("admin", "USER_ADMIN", UserAdminLoginController, UserAdminLogoutController, "/admin/accounts"),
    ("pm", "PLATFORM_MANAGER", PlatformManagerLoginController, PlatformManagerLogoutController, "/pm/categories"),
]


# Builds one password hash for all generated accounts (hashing is slow).
@pytest.fixture(scope="session")
def acceptance_password_hash():
    return generate_password_hash(PASSWORD)


# Builds a database with accounts for every role and status, and sample projects.
@pytest.fixture
def sample(fresh_db, acceptance_password_hash):
    stamp = clock.now_text()
    accounts = {}
    for prefix, role, *_ in ROLES:
        profile = fresh_db.scalar("SELECT profile_id FROM user_profiles WHERE role_code = ?", (role,))
        accounts[prefix] = fresh_db.execute(
            "INSERT INTO user_accounts (name,email,password_hash,contact_number,profile_id,created_at,updated_at) "
            "VALUES (?, ?, ?, '91234567', ?, ?, ?)",
            (f"{prefix.title()} Person", f"{prefix}@acceptance.test", acceptance_password_hash, profile, stamp, stamp),
        )
    accounts["other"] = fresh_db.execute(
        "INSERT INTO user_accounts (name,email,password_hash,contact_number,profile_id,created_at,updated_at) "
        "SELECT 'Other Customer', 'other@acceptance.test', ?, '98887777', profile_id, ?, ? "
        "FROM user_profiles WHERE role_code = 'CUSTOMER'", (acceptance_password_hash, stamp, stamp),
    )
    kitchen = fresh_db.execute("INSERT INTO project_categories (name) VALUES ('Kitchen')")
    bedroom = fresh_db.execute("INSERT INTO project_categories (name) VALUES ('Bedroom')")
    projects = []
    for i in range(15):
        projects.append(fresh_db.execute(
            "INSERT INTO interior_design_projects (designer_id,title,description,category_id,project_status,"
            "budget,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (accounts["designer"], f"Catalogue Project {i:02d}", f"Timber interior number {i:02d}",
             kitchen if i < 8 else bedroom, "CURRENT" if i % 2 == 0 else "PAST", 10000 + i * 1000, stamp, stamp),
        ))
    return {"accounts": accounts, "projects": projects, "category": kitchen, "db": fresh_db}


# Returns a test client for the sample database.
@pytest.fixture
def web(sample):
    return create_app(sample["db"].path, testing=True).test_client()


# Logs a test client in as the sample account of a role.
def sign_in(client, prefix="customer"):
    response = client.post(f"/{prefix}/login", data={"email": f"{prefix}@acceptance.test", "password": PASSWORD})
    assert response.status_code == 302
    return response


# Checks US02 US07 US09 US11 all role login flows.
@pytest.mark.parametrize("prefix,role,login_class,logout_class,home", ROLES)
@pytest.mark.parametrize("scenario,code", [
    ("normal", "LOGGED_IN"), ("empty", "INVALID_INPUT"), ("unknown", "LOGIN_FAILED"),
    ("wrong_password", "LOGIN_FAILED"), ("suspended_account", "SUSPENDED"),
    ("suspended_profile", "SUSPENDED"), ("wrong_role", "WRONG_ROLE"),
])
def test_us02_us07_us09_us11_all_role_login_flows(sample, prefix, role, login_class, logout_class, home,
                                                 scenario, code):
    db = sample["db"]
    email, password = f"{prefix}@acceptance.test", PASSWORD
    if scenario == "empty":
        email = password = ""
    elif scenario == "unknown":
        email = "unknown@acceptance.test"
    elif scenario == "wrong_password":
        password = "WrongPassword123"
    elif scenario == "suspended_account":
        db.execute("UPDATE user_accounts SET status = 'SUSPENDED' WHERE account_id = ?", (sample["accounts"][prefix],))
    elif scenario == "suspended_profile":
        db.execute("UPDATE user_profiles SET status = 'SUSPENDED' WHERE role_code = ?", (role,))
    elif scenario == "wrong_role":
        email = "designer@acceptance.test" if prefix == "customer" else "customer@acceptance.test"
    result = login_class().execute(LoginRequest(email, password))
    assert result.code == code
    assert db.scalar("SELECT COUNT(*) FROM sessions") == (1 if code == "LOGGED_IN" else 0)
    if result.ok:
        assert len(result.data["sessionId"]) >= 32


# Checks US05 US08 US10 US12 expired logout deletes server row.
@pytest.mark.parametrize("prefix,role,login_class,logout_class,home", ROLES)
def test_us05_us08_us10_us12_expired_logout_deletes_server_row(sample, frozen_clock, prefix, role,
                                                             login_class, logout_class, home):
    sid = Sessions().createSession(sample["accounts"][prefix])
    clock.freeze(frozen_clock + timedelta(minutes=31))
    assert logout_class().execute(SessionRequest(sid)).ok
    assert sample["db"].scalar("SELECT COUNT(*) FROM sessions WHERE session_id = ?", (sid,)) == 0


# Checks US02 US12 idle timeout refresh logout and replay.
@pytest.mark.parametrize("prefix,role,login_class,logout_class,home", ROLES)
def test_us02_us12_idle_timeout_refresh_logout_and_replay(web, sample, frozen_clock, prefix, role,
                                                        login_class, logout_class, home):
    sign_in(web, prefix)
    with web.session_transaction() as cookie:
        sid = cookie["sid"]
    clock.freeze(frozen_clock + timedelta(minutes=20))
    response = web.get(home)
    assert response.status_code == 200
    assert "no-store" in response.headers.get("Cache-Control", "")
    clock.freeze(frozen_clock + timedelta(minutes=40))
    assert web.get(home).status_code == 200  # twenty minutes since the last request
    clock.freeze(frozen_clock + timedelta(minutes=71))
    assert web.get(home).headers["Location"].endswith(f"/{prefix}/login")
    assert web.post(f"/{prefix}/logout").status_code == 302
    # Even an expired token cannot be replayed by a caller bypassing the browser.
    assert not Sessions().isActive(sid)
    assert web.get(home).status_code == 302


# Checks US01 US06 registration errors keep fields but not password.
@pytest.mark.parametrize("prefix", ["customer", "designer"])
def test_us01_us06_registration_errors_keep_fields_but_not_password(web, prefix):
    response = web.post(f"/{prefix}/register", data={
        "name": "New Person", "email": "invalid-email", "password": "SecretMustNotAppear", "contactNumber": "91234567",
    })
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'value="New Person"' in html and 'value="invalid-email"' in html
    assert "SecretMustNotAppear" not in html


# Checks US03 US04 cannot change another customer or readonly email.
def test_us03_us04_cannot_change_another_customer_or_readonly_email(web, sample):
    sign_in(web)
    response = web.post("/customer/details/edit", data={
        "name": "Updated Customer", "contactNumber": "+6588887777",
        "accountId": sample["accounts"]["other"], "email": "forged@acceptance.test",
    }, follow_redirects=True)
    assert "Your details have been updated." in response.get_data(as_text=True)
    own = sample["db"].query_one("SELECT name,email FROM user_accounts WHERE account_id = ?", (sample["accounts"]["customer"],))
    other = sample["db"].query_one("SELECT name,email FROM user_accounts WHERE account_id = ?", (sample["accounts"]["other"],))
    assert own == {"name": "Updated Customer", "email": "customer@acceptance.test"}
    assert other["name"] == "Other Customer"


# Lists every Customer controller with a request, for the role and status checks.
def customer_requests(sid, project):
    return [
        (ViewPersonalDetailsController, SessionRequest(sid)),
        (UpdatePersonalDetailsController, UpdateDetailsRequest(sid, "Changed", "91234567")),
        (ViewIDPDetailsController, IDPIdRequest(project, sid)),
        (SaveFavouriteController, FavouriteRequest(sid, project)),
        (ViewFavouritesController, SessionRequest(sid)),
        (SearchFavouritesController, SearchFavouritesRequest(sid, "Catalogue")),
        (RemoveFavouriteController, FavouriteRequest(sid, project)),
    ]


# Checks customer controllers enforce role and status without http guard.
@pytest.mark.parametrize("request_index", range(7))
@pytest.mark.parametrize("state,expected", [("wrong_role", "FORBIDDEN"), ("suspended", "SUSPENDED")])
def test_customer_controllers_enforce_role_and_status_without_http_guard(sample, request_index, state, expected):
    account = sample["accounts"]["designer" if state == "wrong_role" else "customer"]
    sid = Sessions().createSession(account)
    if state == "suspended":
        sample["db"].execute("UPDATE user_accounts SET status = 'SUSPENDED' WHERE account_id = ?", (account,))
    controller, request = customer_requests(sid, sample["projects"][0])[request_index]
    result = controller().execute(request)
    assert result.code == expected
    assert sample["db"].scalar("SELECT COUNT(*) FROM project_views") == 0
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites") == 0
    assert sample["db"].scalar("SELECT name FROM user_accounts WHERE account_id = ?", (account,)) != "Changed"


# Checks US13 US17 empty results are visible in browser html.
@pytest.mark.parametrize("path,message", [
    ("/customer/projects", "No projects to show yet."),
    ("/customer/projects/search?keyword=missing", "No projects match"),
    ("/customer/projects/category?categoryId=1", "No projects in this category."),
    ("/customer/projects/status?status=PAST", "No projects with this status."),
    ("/customer/projects/budget?minBudget=0&maxBudget=100", "No projects in this budget range."),
])
def test_us13_us17_empty_results_are_visible_in_browser_html(web, sample, path, message):
    sample["db"].execute("UPDATE interior_design_projects SET removed_at = ?", (clock.now_text(),))
    sign_in(web)
    response = web.get(path)
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and message in html
    assert '<article class="card project">' not in html


# Checks US15 deleted category error keeps the full project list.
def test_us15_deleted_category_error_keeps_the_full_project_list(web, sample):
    sign_in(web)
    html = web.get("/customer/projects/category?categoryId=999999").get_data(as_text=True)
    assert "This category no longer exists." in html
    assert html.count('<article class="card project">') == 12
    assert "15 projects" in html


# Checks US20 saved project shows saved date and removal link.
def test_us20_saved_project_shows_saved_date_and_removal_link(web, sample):
    sign_in(web)
    project = sample["projects"][0]
    web.post(f"/customer/projects/{project}/save")
    html = web.get("/customer/favourites").get_data(as_text=True)
    assert f"/customer/favourites/{project}/remove" in html
    assert clock.now_text()[:10] in html
    assert "Catalogue Project 00" in html


# Checks US17 rejects non finite budget.
@pytest.mark.parametrize("low,high", [("0", "inf"), ("inf", "inf"), ("0", "1e309"), ("nan", "20000")])
def test_us17_rejects_non_finite_budget(low, high):
    assert FilterIDPsByBudgetController().execute(FilterByBudgetRequest(low, high)).code == "INVALID_INPUT"


# Checks US13 US17 pagination preserves filters and has no duplicates.
@pytest.mark.parametrize("path", [
    "/customer/projects", "/customer/projects/search?keyword=Catalogue",
    "/customer/projects/category?categoryId=1", "/customer/projects/status?status=PAST",
    "/customer/projects/budget?minBudget=0&maxBudget=50000",
])
def test_us13_us17_pagination_preserves_filters_and_has_no_duplicates(web, sample, path):
    sample["db"].execute("UPDATE interior_design_projects SET category_id = 1, project_status = 'PAST'")
    sign_in(web)
    html = web.get(path).get_data(as_text=True)
    first = re.findall(r'<article class="card project">.*?href="/customer/projects/(\d+)(?:\?[^"]*)?"', html, re.S)
    match = re.search(r'href="([^"]+)">Next', html)
    assert match, html
    next_url = match.group(1).replace("&amp;", "&")
    original = parse_qs(urlparse(path).query)
    next_query = parse_qs(urlparse(next_url).query)
    assert all(next_query.get(k) == v for k, v in original.items())
    second_html = web.get(next_url).get_data(as_text=True)
    second = re.findall(r'<article class="card project">.*?href="/customer/projects/(\d+)(?:\?[^"]*)?"', second_html, re.S)
    assert len(first) == 12 and len(second) == 3
    assert not set(first).intersection(second)
    assert set(map(int, first + second)) == set(sample["projects"])


# Checks US18 US21 unavailable projects cannot be viewed saved or listed.
@pytest.mark.parametrize("hidden_state", ["removed", "suspended_account", "suspended_profile"])
def test_us18_us21_unavailable_projects_cannot_be_viewed_saved_or_listed(web, sample, hidden_state):
    sign_in(web)
    project = sample["projects"][0]
    web.post(f"/customer/projects/{project}/save")
    if hidden_state == "removed":
        sample["db"].execute("UPDATE interior_design_projects SET removed_at = ? WHERE idp_id = ?", (clock.now_text(), project))
    elif hidden_state == "suspended_account":
        sample["db"].execute("UPDATE user_accounts SET status = 'SUSPENDED' WHERE account_id = ?", (sample["accounts"]["designer"],))
    else:
        sample["db"].execute("UPDATE user_profiles SET status = 'SUSPENDED' WHERE role_code = 'INTERIOR_DESIGNER'")
    before = sample["db"].scalar("SELECT COUNT(*) FROM project_views")
    detail = web.get(f"/customer/projects/{project}", follow_redirects=True).get_data(as_text=True)
    assert "This project is no longer available." in detail
    assert sample["db"].scalar("SELECT COUNT(*) FROM project_views") == before
    for path in ["/customer/favourites", "/customer/favourites/search?keyword=Catalogue"]:
        assert "Catalogue Project 00" not in web.get(path).get_data(as_text=True)
    # Saving a different hidden project must also fail, rather than just hitting duplicate handling.
    other = sample["projects"][1]
    if hidden_state == "removed":
        sample["db"].execute("UPDATE interior_design_projects SET removed_at = ? WHERE idp_id = ?", (clock.now_text(), other))
    response = web.post(f"/customer/projects/{other}/save", follow_redirects=True)
    assert "This project is no longer available" in response.get_data(as_text=True)
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites") == 1


# Checks US14 US21 search treats keyword as literal text.
@pytest.mark.parametrize("keyword", ["%", "_"])
def test_us14_us21_search_treats_keyword_as_literal_text(web, sample, keyword):
    sign_in(web)
    project = sample["projects"][0]
    web.post(f"/customer/projects/{project}/save")
    for path in ["/customer/projects/search", "/customer/favourites/search"]:
        response = web.get(path, query_string={"keyword": keyword})
        assert "Catalogue Project 00" not in response.get_data(as_text=True)


# Checks US18 US22 full customer flow view count duplicate cancel privacy resave.
def test_us18_us22_full_customer_flow_view_count_duplicate_cancel_privacy_resave(web, sample):
    sign_in(web)
    project = sample["projects"][0]
    assert web.get(f"/customer/projects/{project}").status_code == 200
    assert sample["db"].scalar("SELECT COUNT(*) FROM project_views") == 1
    for _ in range(2):
        assert web.post(f"/customer/projects/{project}/save").status_code == 302
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NULL") == 1
    html = web.get(f"/customer/favourites/{project}/remove").get_data(as_text=True)
    assert "Remove from Favourites?" in html
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NULL") == 1
    # Visiting Cancel performs no write.
    web.get("/customer/favourites")
    with web.session_transaction() as cookie:
        owner_sid = cookie["sid"]
    other_sid = Sessions().createSession(sample["accounts"]["other"])
    assert RemoveFavouriteController().execute(FavouriteRequest(other_sid, project)).code == "NOT_IN_FAVOURITES"
    assert ViewFavouritesController().execute(SessionRequest(other_sid)).data == []
    assert len(ViewFavouritesController().execute(SessionRequest(owner_sid)).data) == 1
    web.post(f"/customer/favourites/{project}/remove")
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NULL") == 0
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NOT NULL") == 1
    assert web.post(f"/customer/projects/{project}/save").status_code == 302
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NULL") == 1


# Checks US21 keyword length limit matches project search.
def test_us21_keyword_length_limit_matches_project_search(sample):
    sid = Sessions().createSession(sample["accounts"]["customer"])
    assert SearchFavouritesController().execute(SearchFavouritesRequest(sid, "x" * 101)).code == "INVALID_INPUT"


# Checks US13 US22 http requires customer login.
@pytest.mark.parametrize("path,method", [
    ("/customer/projects", "get"), ("/customer/projects/search?keyword=Catalogue", "get"),
    ("/customer/projects/category?categoryId=1", "get"), ("/customer/projects/status?status=PAST", "get"),
    ("/customer/projects/budget?minBudget=0&maxBudget=50000", "get"), ("/customer/projects/1", "get"),
    ("/customer/projects/1/save", "post"), ("/customer/favourites", "get"),
    ("/customer/favourites/search?keyword=Catalogue", "get"), ("/customer/favourites/1/remove", "post"),
])
def test_us13_us22_http_requires_customer_login(web, sample, path, method):
    response = getattr(web, method)(path)
    assert response.status_code == 302 and response.headers["Location"].endswith("/customer/login")
    sign_in(web, "designer")
    response = getattr(web, method)(path)
    assert response.status_code == 302 and response.headers["Location"].endswith("/customer/login")
    assert sample["db"].scalar("SELECT COUNT(*) FROM favourites") == 0
    assert sample["db"].scalar("SELECT COUNT(*) FROM project_views") == 0
