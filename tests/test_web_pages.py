"""Integration tests: every page renders for its role with the full generated test data set."""
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app import create_app

ROOT = Path(__file__).resolve().parents[1]


# Generates the full sample database once for these page tests.
@pytest.fixture(scope="module")
def data_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("web") / "demo.db"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_test_data.py"), "--db", str(db)], check=True,
                   capture_output=True)
    return str(db)


# Returns a test client for the sample database.
@pytest.fixture
def client(data_db):
    app = create_app(data_db, testing=True)
    return app.test_client()


# Logs a test client in on a role's login page.
def login(client, prefix, email):
    response = client.post(f"/{prefix}/login", data={"email": email, "password": "Password123"})
    assert response.status_code == 302, response.data
    return client


# Opens a page, checks it loaded and returns its HTML.
def ok(client, url):
    response = client.get(url, follow_redirects=True)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


# Checks protected pages redirect to login.
def test_protected_pages_redirect_to_login(client):
    for url, login_url in [("/customer/projects", "/customer/login"), ("/designer/projects", "/designer/login"),
                           ("/admin/accounts", "/admin/login"), ("/pm/reports", "/pm/login")]:
        response = client.get(url)
        assert response.status_code == 302 and response.headers["Location"].endswith(login_url)


# Checks wrong role cannot open other area.
def test_wrong_role_cannot_open_other_area(client):
    login(client, "customer", "customer@demo.com")
    assert client.get("/admin/accounts").status_code == 302


# Checks a Customer can use every page from sign-in to log-out.
def test_customer_journey(client):
    html = ok(client, "/")
    assert "Renovate Your Home with the Right Designer" in html and "design projects" in html
    login(client, "customer", "customer@demo.com")
    html = ok(client, "/customer/projects")
    assert 'aria-current="page">1</span>' in html
    ok(client, "/customer/projects?page=2")
    assert "match" in ok(client, "/customer/projects/search?keyword=kitchen")
    ok(client, "/customer/projects/category?categoryId=1")
    ok(client, "/customer/projects/status?status=PAST")
    ok(client, "/customer/projects/budget?minBudget=10000&maxBudget=50000")
    assert "Minimum budget cannot be higher" in ok(client, "/customer/projects/budget?minBudget=9&maxBudget=1")
    idp = re.search(r"/customer/projects/(\d+)", ok(client, "/customer/projects")).group(1)
    detail = ok(client, f"/customer/projects/{idp}")
    designer = re.search(r"/customer/designers/(\d+)", detail).group(1)
    ok(client, f"/customer/designers/{designer}")
    client.post(f"/customer/projects/{idp}/save")
    assert "My Favourites" in ok(client, "/customer/favourites")
    ok(client, "/customer/favourites/search?keyword=a")
    assert "Remove from Favourites?" in ok(client, f"/customer/favourites/{idp}/remove?title=x")
    assert "Removed from your favourites." in client.post(f"/customer/favourites/{idp}/remove",
                                                          follow_redirects=True).get_data(as_text=True)
    ok(client, "/customer/details")
    assert "Your details have been updated." in client.post(
        "/customer/details/edit", data={"name": "Demo Customer", "contactNumber": "91234567"},
        follow_redirects=True).get_data(as_text=True)
    assert "You have been logged out." in client.post("/customer/logout",
                                                      follow_redirects=True).get_data(as_text=True)
    assert client.get("/customer/projects").status_code == 302


# Checks registration and login errors.
def test_registration_and_login_errors(client):
    html = client.post("/customer/register", data={"name": "New", "email": "new@x.test", "password": "Password123",
                                                    "contactNumber": "91234567"}, follow_redirects=True)
    assert "Account created" in html.get_data(as_text=True)
    html = client.post("/customer/register", data={"name": "New", "email": "new@x.test", "password": "Password123",
                                                    "contactNumber": "91234567"}).get_data(as_text=True)
    assert "already registered" in html and 'value="New"' in html
    html = client.post("/designer/login", data={"email": "customer@demo.com", "password": "Password123"})
    assert "Please use the login page for your account type." in html.get_data(as_text=True)


# Checks an Interior Designer can use every page.
def test_designer_journey(client):
    login(client, "designer", "designer@demo.com")
    assert "Total Views" in ok(client, "/designer/home")
    assert "Contact Email" in ok(client, "/designer/company")
    ok(client, "/designer/company/edit")
    html = ok(client, "/designer/projects")
    idp = re.search(r"/designer/projects/(\d+)\"", html).group(1)
    assert "past project" in ok(client, "/designer/projects?status=PAST")
    ok(client, "/designer/projects?q=kitchen")
    ok(client, "/designer/projects/filter?status=PAST")        # old address redirects
    ok(client, "/designer/projects/search?keyword=kitchen")    # old address redirects
    assert "Project Statistics" in ok(client, f"/designer/projects/{idp}")
    ok(client, f"/designer/projects/{idp}/edit")
    ok(client, "/designer/projects/new")
    response = client.post("/designer/projects/new", data={"title": "Web Test Project", "description": "d",
                                                            "categoryId": "1", "projectStatus": "CURRENT",
                                                            "budget": "12345"},
                           follow_redirects=True)
    assert "Project created successfully." in response.get_data(as_text=True)
    assert "views and favourites are deleted too" in ok(client, f"/designer/projects/{idp}/delete")
    ok(client, "/designer/statistics")
    ok(client, "/designer/statistics?sort=views")
    ok(client, "/designer/statistics?sort=shortlists")
    assert "Total Views" in ok(client, f"/designer/statistics/project?idpId={idp}&show=views")
    assert "Shortlisted Now" in ok(client, f"/designer/statistics/project?idpId={idp}&show=shortlists")
    ok(client, f"/designer/statistics/period?period=MONTH&date={date.today().isoformat()}&show=views")
    ok(client, f"/designer/statistics/period?period=WEEK&date={date.today().isoformat()}&show=saves")
    assert "Please choose a period and a date." in ok(client, "/designer/statistics/period?period=WEEK&show=views")
    assert "Portfolio Totals" in ok(client, "/designer/statistics/totals")
    ok(client, "/designer/interest")                             # old address redirects


# Checks a User Admin can use every page.
def test_user_admin_journey(client):
    login(client, "admin", "admin@demo.com")
    html = ok(client, "/admin/accounts")
    assert re.search(r"28\d accounts<", html) and 'aria-label="Page 15"' in html
    ok(client, "/admin/accounts?keyword=tan&profileId=1")
    ok(client, "/admin/accounts/5")
    ok(client, "/admin/accounts/5/edit")
    ok(client, "/admin/accounts/new")
    response = client.post("/admin/accounts/new", data={"displayName": "Web Admin",
                                                        "email": "webadmin@x.test", "password": "Password123",
                                                        "profileId": "3", "contactNumber": "91234567"},
                           follow_redirects=True)
    assert "Account created." in response.get_data(as_text=True)
    assert "Suspend This Account?" in ok(client, "/admin/accounts/6/suspend")
    ok(client, "/admin/profiles")
    ok(client, "/admin/profiles?keyword=team")
    ok(client, "/admin/profiles/1")
    ok(client, "/admin/profiles/1/edit")
    ok(client, "/admin/profiles/new")
    assert "Suspend This Profile?" in ok(client, "/admin/profiles/10/suspend")


# Checks a Platform Manager can use every page.
def test_platform_manager_journey(client):
    login(client, "pm", "manager@demo.com")
    assert "120 categories" in ok(client, "/pm/categories")
    ok(client, "/pm/categories?keyword=kitchen")
    ok(client, "/pm/categories/new")
    assert "created" in client.post("/pm/categories/new", data={"name": "Web Test Category"},
                                    follow_redirects=True).get_data(as_text=True)
    ok(client, "/pm/categories/1/edit")
    assert "Remove This Category?" in ok(client, "/pm/categories/1/remove")
    for period_type, value in [("DAY", date.today().isoformat()), ("WEEK", f"{date.today():%G-W%V}"),
                               ("MONTH", f"{date.today():%Y-%m}")]:
        assert "New Saves" in ok(client, f"/pm/reports?periodType={period_type}&periodValue={value}")
