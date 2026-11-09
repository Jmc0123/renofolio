"""Checks for the 8 November 2026 review, written before the fixes (test-first).

Covers: the Renofolio name and footer, Title Case wording, the six wording questions, the eight bugs
(including US60/US61 Reactivate and "Based on" staff profiles), the confusing behaviour list and the
sample-data text. Each test states the rule it protects.
"""
import os
import re
import subprocess
import sys
from html import unescape
from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.boundary import designer_pages
from app.entity.database import DatabaseConnection, init_db
from tests.conftest import PASSWORD

ROOT = os.path.join(os.path.dirname(__file__), "..")


# ---------------------------------------------------------------- shared set-up
# Builds a password hash once, because hashing for every test would be slow.
@pytest.fixture(scope="module")
def password_hash():
    return generate_password_hash(PASSWORD)


# Creates an app with one account per built-in role, two categories and a designer with a company.
@pytest.fixture
def web(tmp_path, password_hash):
    app = create_app(str(tmp_path / "review.db"), testing=True)
    db = DatabaseConnection()
    for name, email, code in [("Ada Admin", "admin@example.test", "USER_ADMIN"),
                              ("Mia Manager", "pm@example.test", "PLATFORM_MANAGER"),
                              ("Dan Designer", "designer@example.test", "INTERIOR_DESIGNER"),
                              ("Cora Customer", "customer@example.test", "CUSTOMER")]:
        add_account(db, password_hash, name, email, code)
    db.execute("INSERT INTO project_categories (name) VALUES ('Modern Kitchen'), ('Calm Bedroom')")
    designer = account_id(db, "designer@example.test")
    db.execute("INSERT INTO companies (designer_id, company_name, contact_email, contact_number, created_at, "
               "updated_at) VALUES (?, 'Oak Atelier', 'hello@oak.test', '61234567', '2026-01-01 00:00:00', "
               "'2026-01-01 00:00:00')", (designer,))
    return app, db


# Inserts one account with the given built-in or custom role code.
def add_account(db, password_hash, name, email, code, status="ACTIVE"):
    db.execute("INSERT INTO user_accounts (name, email, password_hash, contact_number, profile_id, status, "
               "created_at, updated_at) SELECT ?, ?, ?, '91234567', profile_id, ?, '2026-06-09 13:59:40', "
               "'2026-06-09 13:59:40' FROM user_profiles WHERE role_code = ?",
               (name, email, password_hash, status, code))


# Returns the account ID for an email address.
def account_id(db, email):
    return db.scalar("SELECT account_id FROM user_accounts WHERE email = ?", (email,))


# Returns the profile ID for a role code.
def profile_id(db, code):
    return db.scalar("SELECT profile_id FROM user_profiles WHERE role_code = ?", (code,))


# Logs a test client in on the given role's login page.
def sign_in(app, prefix, email):
    client = app.test_client()
    response = client.post(f"/{prefix}/login", data={"email": email, "password": PASSWORD})
    assert response.status_code == 302, unescape(response.get_data(as_text=True))[:3000]
    return client


# Returns the page HTML with entities decoded.
def html(response):
    return unescape(response.get_data(as_text=True))


# Returns the banner messages shown on a page.
def banners(response):
    return [re.sub(r"<[^>]+>", "", m).strip()
            for m in re.findall(r'class="banner[^"]*"[^>]*>(.*?)</div>', html(response), re.S)]


# Adds a project for the designer straight into the database and returns its ID.
def add_project(db, title="Bright Kitchen", status="CURRENT", budget=25000, photo="/static/sample-projects/kitchen.png"):
    designer = account_id(db, "designer@example.test")
    category = db.scalar("SELECT category_id FROM project_categories WHERE name = 'Modern Kitchen'")
    return db.execute("INSERT INTO interior_design_projects (designer_id, title, description, category_id, "
                      "project_status, budget, photo_url, created_at, updated_at) VALUES (?, ?, 'calm', ?, ?, ?, ?, "
                      "'2026-10-28 09:15:00', '2026-10-28 09:15:00')",
                      (designer, title, category, status, budget, photo))


# ---------------------------------------------------------------- Title Case checker
SMALL_WORDS = {"a", "an", "the", "and", "or", "nor", "for", "to", "of", "in", "on", "at", "by", "with", "from",
               "as", "per", "vs", "via", "into", "out", "up"}


# Returns the words in a UI label that break the Title Case rule (empty list when the label is fine).
def title_case_problems(text):
    words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", re.sub(r"\(.*?\)|e\.g\..*$|https?://\S+|\S+@\S+", "", text))
    problems = []
    for position, word in enumerate(words):
        # "Log In", "Sign Up": the second word belongs to the verb, so it is capitalised like any main word.
        phrasal = position > 0 and words[position - 1].lower() in ("log", "sign")
        if word.lower() in SMALL_WORDS and position > 0 and not phrasal:
            if word != word.lower():
                problems.append(word)
        elif not word[0].isupper():
            problems.append(word)
    return problems


# Collects button, link-button, menu, heading and form-label texts from a page.
def ui_labels(page_html):
    page_html = re.sub(r"<script.*?</script>", "", page_html, flags=re.S)
    # Text only screen readers hear (e.g. "1 unread" on the Messages badge) is not a visible label.
    page_html = re.sub(r'<span class="sr-only">.*?</span>', "", page_html, flags=re.S)
    patterns = [r"<button[^>]*>(.*?)</button>", r'<a[^>]*class="[^"]*\bbtn\b[^"]*"[^>]*>(.*?)</a>',
                r'<nav[^>]*class="nav"[^>]*>(.*?)</nav>', r'<div class="menu">(.*?)</div>',
                r"<h1[^>]*>(.*?)</h1>", r"<h2[^>]*>(.*?)</h2>", r"<label[^>]*>(.*?)</label>", r"<th[^>]*>(.*?)</th>",
                r'<div class="foot-brand">.*?</div>\s*(.*?)</footer>']
    texts = []
    for pattern in patterns:
        for chunk in re.findall(pattern, page_html, re.S):
            for piece in re.split(r"<[^>]+>", chunk):
                piece = unescape(piece).strip()
                if piece and not piece.startswith("©"):
                    texts.append(piece)
    return texts


# ---------------------------------------------------------------- name, footer and Title Case
class TestRenofolioNameAndTitleCase:
    # Checks the brand, browser tab name and footer use Renofolio, and DesignMatch is gone.
    def test_brand_and_footer(self, web):
        app, _ = web
        page = html(app.test_client().get("/"))
        assert "© 2026 Renofolio · CSIT314 student project" in page
        assert "· Renofolio</title>" in page
        assert "DesignMatch" not in page and "Design<span>Match" not in page
        assert "Reno<span>folio</span>" in page

    # Checks the three first-page facts all start with a bold word (Q2).
    def test_free_for_customers_is_aligned(self, web):
        app, _ = web
        assert "<li><strong>Free</strong> for customers</li>" in html(app.test_client().get("/"))

    # Checks every button, menu item, heading, label and table header on the main pages uses Title Case (Q1).
    def test_title_case_on_every_role_page(self, web):
        app, db = web
        idp = add_project(db)
        customer = sign_in(app, "customer", "customer@example.test")
        customer.post(f"/customer/projects/{idp}/save")
        designer = sign_in(app, "designer", "designer@example.test")
        admin = sign_in(app, "admin", "admin@example.test")
        manager = sign_in(app, "pm", "pm@example.test")
        public = app.test_client()
        pages = {
            public: ["/", "/customer/login", "/customer/register", "/designer/login", "/designer/register",
                     "/admin/login", "/pm/login"],
            customer: ["/customer/home", "/customer/projects", f"/customer/projects/{idp}", "/customer/favourites",
                       "/customer/details", "/customer/details/edit"],
            designer: ["/designer/home", "/designer/projects", f"/designer/projects/{idp}", "/designer/company",
                       "/designer/company/edit", "/designer/projects/new", f"/designer/projects/{idp}/edit",
                       "/designer/statistics", "/designer/statistics/totals", "/designer/statistics/period"],
            admin: ["/admin/accounts", "/admin/accounts/new", "/admin/accounts/1", "/admin/accounts/1/edit",
                    "/admin/accounts/2/suspend", "/admin/profiles", "/admin/profiles/new", "/admin/profiles/1",
                    "/admin/profiles/1/edit"],
            manager: ["/pm/categories", "/pm/categories/new", "/pm/categories/1/edit", "/pm/categories/1/remove",
                      "/pm/reports"],
        }
        failures = []
        for client, urls in pages.items():
            for url in urls:
                response = client.get(url)
                assert response.status_code == 200, url
                for text in ui_labels(html(response)):
                    if title_case_problems(text):
                        failures.append(f"{url}: {text!r}")
        assert not failures, "\n".join(sorted(set(failures)))


# ---------------------------------------------------------------- the six wording questions
class TestWordingQuestions:
    # Checks "In Your Favourites" is a plain status (not a link) and the message keeps "View My Favourites" (Q4).
    def test_favourite_badge_is_not_a_link(self, web):
        app, db = web
        idp = add_project(db)
        customer = sign_in(app, "customer", "customer@example.test")
        customer.post(f"/customer/projects/{idp}/save")
        page = html(customer.get(f"/customer/projects/{idp}"))
        assert re.search(r'<span class="tag active"[^>]*>♥ In Your Favourites</span>', page)
        assert not re.search(r"<a[^>]*>♥ In Your Favourites", page)
        assert "View My Favourites" in page  # the in-page script still adds the link to the message
        assert "document.createElement('span')" in page  # the script also adds a plain status, not a link

    # Checks the account search label, example placeholder and hint (Q5).
    def test_account_search_wording(self, web):
        app, _ = web
        page = html(sign_in(app, "admin", "admin@example.test").get("/admin/accounts"))
        assert ">Name or Email</label>" in page
        assert 'placeholder="e.g. Rachel or rachel@example.com"' in page
        assert "Enter a name or email, or choose a profile." in page
        assert "Optional search text" not in page

    # Checks the profile heading, label, placeholder and count wording before and after a search (Q6).
    def test_profile_list_wording(self, web):
        app, _ = web
        admin = sign_in(app, "admin", "admin@example.test")
        page = html(admin.get("/admin/profiles"))
        assert "<h1>User Profiles</h1>" in page and ">Role Name or Description</label>" in page
        assert 'placeholder="e.g. Platform Manager or staff"' in page
        assert re.search(r'class="muted">4 profiles</p>', page)
        searched = html(admin.get("/admin/profiles?keyword=staff"))
        assert "2 profiles match 'staff'" in searched

    # Checks account counts read naturally before and after a search.
    def test_account_count_wording(self, web):
        app, _ = web
        admin = sign_in(app, "admin", "admin@example.test")
        assert re.search(r'class="muted">4 accounts</p>', html(admin.get("/admin/accounts")))
        assert "1 account matches 'mia'" in html(admin.get("/admin/accounts?keyword=mia"))

    # Checks no page or message uses "(s)" instead of a real plural.
    def test_no_bracket_plurals(self, web):
        app, db = web
        for i in range(13):
            add_project(db, title=f"Kitchen {i:02d}")
        customer = sign_in(app, "customer", "customer@example.test")
        customer.post("/customer/projects/1/save")
        admin = sign_in(app, "admin", "admin@example.test")
        manager = sign_in(app, "pm", "pm@example.test")
        checks = [customer.get("/customer/favourites"), customer.get("/customer/projects?page=9"),
                  admin.get("/admin/accounts"), admin.get("/admin/profiles/1"), admin.get("/admin/profiles"),
                  manager.post("/pm/categories/1/remove", follow_redirects=True), manager.get("/pm/categories")]
        for response in checks:
            assert "(s)" not in html(response)
        assert "There are 2 pages." in html(checks[1])
        assert "'Modern Kitchen' is used by 13 projects and cannot be removed." in html(checks[5])
        assert "1 saved project" in html(checks[0])


# ---------------------------------------------------------------- naming chosen on 8 November
class TestChosenNames:
    # Checks the menus and headings use the names chosen for each page.
    def test_menu_and_heading_names(self, web):
        app, _ = web
        customer = sign_in(app, "customer", "customer@example.test")
        home = html(customer.get("/customer/home"))
        assert ">Browse Projects</a>" in home and ">My Favourites</a>" in home
        assert "Browse Interior Design Projects" not in home
        assert "<h1>Interior Design Projects</h1>" in html(customer.get("/customer/projects"))
        designer = sign_in(app, "designer", "designer@example.test")
        dash = html(designer.get("/designer/home"))
        assert ">Home</a>" in dash and ">Dashboard</a>" not in dash and ">My Projects</a>" in dash
        assert "<h1>Interior Designer Home</h1>" in dash
        assert "<h1>My Interior Design Projects</h1>" in html(designer.get("/designer/projects"))
        assert "Portfolio Statistics" in html(designer.get("/designer/statistics"))
        manager = sign_in(app, "pm", "pm@example.test")
        categories = html(manager.get("/pm/categories"))
        assert ">Categories</a>" in categories and "<h1>Project Categories</h1>" in categories
        admin = sign_in(app, "admin", "admin@example.test")
        accounts = html(admin.get("/admin/accounts"))
        assert ">User Accounts</a>" in accounts and ">User Profiles</a>" in accounts

    # Checks categories use an Edit button like every other list, and the edit page keeps its Update heading.
    def test_edit_button_on_categories(self, web):
        app, _ = web
        manager = sign_in(app, "pm", "pm@example.test")
        page = html(manager.get("/pm/categories"))
        assert re.search(r'class="btn secondary small" href="/pm/categories/\d+/edit">Edit</a>', page)
        assert ">Update</a>" not in page
        assert "<h1>Update Category</h1>" in html(manager.get("/pm/categories/1/edit"))

    # Checks the login email label is "Email" and the name label is "Full Name" on every form.
    def test_email_and_name_labels(self, web):
        app, _ = web
        public = app.test_client()
        for url in ["/customer/login", "/designer/login", "/admin/login", "/pm/login", "/customer/register",
                    "/designer/register"]:
            page = html(public.get(url))
            assert ">Email</label>" in page and "E-mail" not in page, url
        for url in ["/customer/register", "/designer/register"]:
            assert ">Full Name</label>" in html(public.get(url))
        customer = sign_in(app, "customer", "customer@example.test")
        details = html(customer.get("/customer/details")) + html(customer.get("/customer/details/edit"))
        assert "E-mail" not in details and ">Email<" in details
        designer = sign_in(app, "designer", "designer@example.test")
        assert ">Contact Email</label>" in html(designer.get("/designer/company/edit"))

    # Checks each login page heading names its role.
    @pytest.mark.parametrize("url,heading", [("/customer/login", "Customer Log In"),
                                             ("/designer/login", "Interior Designer Log In"),
                                             ("/admin/login", "User Admin Log In"),
                                             ("/pm/login", "Platform Manager Log In")])
    def test_login_headings(self, web, url, heading):
        app, _ = web
        assert f"<h1>{heading}</h1>" in html(app.test_client().get(url))

    # Checks the public header: "For Designers" goes to the designer login and the duplicate top-bar links are gone.
    def test_public_header(self, web):
        app, _ = web
        page = html(app.test_client().get("/"))
        assert re.search(r'<a href="/designer/login">For Designers</a>', page)
        assert "Interior designers</a>" not in page and "Log In / Sign Up" not in page
        assert "For Interior Designers</a>" not in page

    # Checks staff login pages do not offer a Sign Up button, because staff cannot sign up.
    @pytest.mark.parametrize("url", ["/admin/login", "/pm/login"])
    def test_staff_login_has_no_sign_up(self, web, url):
        app, _ = web
        assert ">Sign Up</a>" not in html(app.test_client().get(url))


# ---------------------------------------------------------------- bug 1: whole-profile suspension
class TestBug1BuiltInProfiles:
    # Checks none of the four built-in profiles can be suspended and the button is hidden.
    @pytest.mark.parametrize("code", ["CUSTOMER", "INTERIOR_DESIGNER", "USER_ADMIN", "PLATFORM_MANAGER"])
    def test_built_in_profiles_are_protected(self, web, code):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        pid = profile_id(db, code)
        response = admin.post(f"/admin/profiles/{pid}/suspend", follow_redirects=True)
        assert "Built-in profiles cannot be suspended." in banners(response)
        assert db.scalar("SELECT status FROM user_profiles WHERE profile_id = ?", (pid,)) == "ACTIVE"
        assert f"/admin/profiles/{pid}/suspend" not in html(admin.get(f"/admin/profiles/{pid}"))

    # Checks the confirmation for a custom profile says how many accounts will be blocked.
    def test_confirmation_shows_affected_accounts(self, web, password_hash):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Support Team", "description": "Help desk",
                                                "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Support Team'")
        for i in range(2):
            admin.post("/admin/accounts/new", data={"displayName": f"Sam {i}", "email": f"sam{i}@example.test",
                                                    "password": PASSWORD, "contactNumber": "91234567",
                                                    "profileId": pid})
        assert "This will log out and block 2 accounts." in html(admin.get(f"/admin/profiles/{pid}/suspend"))

    # Checks a User Admin cannot suspend the custom profile their own account uses.
    def test_cannot_suspend_own_profile(self, web, password_hash):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Admin Team", "basedOn": "USER_ADMIN"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Admin Team'")
        db.execute("UPDATE user_accounts SET profile_id = ? WHERE email = 'admin@example.test'", (pid,))
        admin = sign_in(app, "admin", "admin@example.test")
        response = admin.post(f"/admin/profiles/{pid}/suspend", follow_redirects=True)
        assert "You cannot suspend your own profile." in banners(response)

    # Checks favourites hidden by a suspended designer are reported, not described as "no saved projects".
    def test_hidden_favourites_are_reported(self, web):
        app, db = web
        idp = add_project(db)
        customer = sign_in(app, "customer", "customer@example.test")
        customer.post(f"/customer/projects/{idp}/save")
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post(f"/admin/accounts/{account_id(db, 'designer@example.test')}/suspend")
        page = html(customer.get("/customer/favourites"))
        assert "1 saved project is currently unavailable." in page
        assert "You have no saved projects yet." not in page


# ---------------------------------------------------------------- bug 2: suspended while logged in
class TestBug2SuspendedMessage:
    # Checks a user suspended while logged in is told the account is suspended, not that the session expired.
    def test_suspended_account_gets_the_real_reason(self, web):
        app, db = web
        manager = sign_in(app, "pm", "pm@example.test")
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post(f"/admin/accounts/{account_id(db, 'pm@example.test')}/suspend")
        response = manager.get("/pm/categories", follow_redirects=True)
        assert "Your account is suspended. Please contact the administrator." in banners(response)
        assert "Your session has expired. Please log in again." not in banners(response)

    # Checks the same for a custom profile suspended while one of its users is logged in.
    def test_suspended_profile_gets_the_real_reason(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Report Team", "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Report Team'")
        admin.post("/admin/accounts/new", data={"displayName": "Rae", "email": "rae@example.test", "password": PASSWORD,
                                                "contactNumber": "91234567", "profileId": pid})
        rae = sign_in(app, "pm", "rae@example.test")
        admin.post(f"/admin/profiles/{pid}/suspend")
        response = rae.get("/pm/reports", follow_redirects=True)
        assert "Your account is suspended. Please contact the administrator." in banners(response)


# ---------------------------------------------------------------- bug 3: US60 / US61 Reactivate
class TestBug3Reactivate:
    # Checks US60: a suspended account shows Reactivate, asks to confirm, becomes active and can log in again.
    def test_us60_reactivate_account(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        target = account_id(db, "customer@example.test")
        admin.post(f"/admin/accounts/{target}/suspend")
        view = html(admin.get(f"/admin/accounts/{target}"))
        assert f'href="/admin/accounts/{target}/reactivate">Reactivate</a>' in view
        confirm = html(admin.get(f"/admin/accounts/{target}/reactivate"))
        assert "Reactivate This Account?" in confirm and "will be able to log in again" in confirm
        response = admin.post(f"/admin/accounts/{target}/reactivate", follow_redirects=True)
        assert "Account reactivated." in banners(response)
        assert db.scalar("SELECT status FROM user_accounts WHERE account_id = ?", (target,)) == "ACTIVE"
        sign_in(app, "customer", "customer@example.test")

    # Checks US60 alternative flows: already active, and reactivating while the profile is still suspended.
    def test_us60_alternative_flows(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        target = account_id(db, "customer@example.test")
        response = admin.post(f"/admin/accounts/{target}/reactivate", follow_redirects=True)
        assert "This account is already active." in banners(response)
        admin.post("/admin/profiles/new", data={"displayName": "Night Team", "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Night Team'")
        admin.post("/admin/accounts/new", data={"displayName": "Nia", "email": "nia@example.test", "password": PASSWORD,
                                                "contactNumber": "91234567", "profileId": pid})
        nia = account_id(db, "nia@example.test")
        admin.post(f"/admin/accounts/{nia}/suspend")
        admin.post(f"/admin/profiles/{pid}/suspend")
        response = admin.post(f"/admin/accounts/{nia}/reactivate", follow_redirects=True)
        assert any(m.startswith("Account reactivated.") and "profile is still suspended" in m
                   for m in banners(response))

    # Checks US61: a suspended custom profile can be reactivated and its users can log in again.
    def test_us61_reactivate_profile(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Audit Team", "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Audit Team'")
        admin.post("/admin/accounts/new", data={"displayName": "Ali", "email": "ali@example.test", "password": PASSWORD,
                                                "contactNumber": "91234567", "profileId": pid})
        admin.post(f"/admin/profiles/{pid}/suspend")
        assert f'href="/admin/profiles/{pid}/reactivate">Reactivate</a>' in html(admin.get(f"/admin/profiles/{pid}"))
        assert "Reactivate This Profile?" in html(admin.get(f"/admin/profiles/{pid}/reactivate"))
        response = admin.post(f"/admin/profiles/{pid}/reactivate", follow_redirects=True)
        assert "Profile reactivated." in banners(response)
        sign_in(app, "pm", "ali@example.test")
        again = admin.post(f"/admin/profiles/{pid}/reactivate", follow_redirects=True)
        assert "This profile is already active." in banners(again)


# ---------------------------------------------------------------- bug 4: "Based on" staff profiles
class TestBug4BasedOnProfiles:
    # Checks a new profile must be based on User Admin or Platform Manager.
    def test_based_on_is_required(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        form = html(admin.get("/admin/profiles/new"))
        assert ">Based on</label>" in form and 'name="basedOn"' in form
        for value in ["", "CUSTOMER", "INTERIOR_DESIGNER", "BOSS"]:
            response = admin.post("/admin/profiles/new", data={"displayName": f"Team {value}", "basedOn": value})
            assert "Please choose User Admin or Platform Manager." in banners(response)
        assert db.scalar("SELECT COUNT(*) FROM user_profiles") == 4

    # Checks a staff account with a custom profile logs in with the base role's pages and shows its own profile name.
    def test_custom_profile_account_logs_in_with_base_role(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Support Team", "description": "Help desk",
                                                "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Support Team'")
        view = html(admin.get(f"/admin/profiles/{pid}"))
        assert "Based on" in view and "Platform Manager" in view
        assert f'value="{pid}"' in html(admin.get("/admin/accounts/new"))
        response = admin.post("/admin/accounts/new", data={"displayName": "Amy", "email": "amy@example.test",
                                                           "password": PASSWORD, "contactNumber": "91234567",
                                                           "profileId": pid}, follow_redirects=True)
        assert any(m.startswith("Account created.") for m in banners(response))
        amy = sign_in(app, "pm", "amy@example.test")
        assert amy.get("/pm/categories").status_code == 200
        wrong = app.test_client().post("/admin/login", data={"email": "amy@example.test", "password": PASSWORD})
        assert "Please use the login page for your account type." in banners(wrong)
        assert "Support Team" in html(admin.get("/admin/accounts?keyword=amy"))

    # Checks a profile based on User Admin gives the User Admin pages.
    def test_user_admin_based_profile(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Account Desk", "basedOn": "USER_ADMIN"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Account Desk'")
        admin.post("/admin/accounts/new", data={"displayName": "Ben", "email": "ben@example.test", "password": PASSWORD,
                                                "contactNumber": "91234567", "profileId": pid})
        assert sign_in(app, "admin", "ben@example.test").get("/admin/accounts").status_code == 200

    # Checks Customer and Interior Designer profiles still cannot be used for staff accounts.
    def test_non_staff_profiles_still_rejected(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        response = admin.post("/admin/accounts/new", data={"displayName": "X", "email": "x@example.test",
                                                           "password": PASSWORD, "contactNumber": "91234567",
                                                           "profileId": profile_id(db, "CUSTOMER")})
        assert "Choose an active User Admin or Platform Manager profile." in banners(response)

    # Checks the based-on role is shown but cannot be changed when editing a profile.
    def test_based_on_is_read_only_on_edit(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        admin.post("/admin/profiles/new", data={"displayName": "Ops", "basedOn": "PLATFORM_MANAGER"})
        pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Ops'")
        form = html(admin.get(f"/admin/profiles/{pid}/edit"))
        assert ">Based on</label>" in form and 'name="basedOn"' not in form

    # Checks an older database gains the based_on column without losing rows.
    def test_database_upgrade_adds_based_on(self, tmp_path):
        path = str(tmp_path / "old.db")
        init_db(path)
        db = DatabaseConnection()
        db.execute("INSERT INTO user_profiles (role_code, role_name, description, status, created_at, updated_at) "
                   "VALUES ('SUPPORT_TEAM_01', 'Support Team 01', 'x', 'ACTIVE', '2026-01-01', '2026-01-01')")
        conn = db.connect()
        conn.execute("ALTER TABLE user_profiles DROP COLUMN base_role")
        conn.commit()
        conn.close()
        init_db(path)
        values = {r["role_code"]: r["base_role"] for r in db.query("SELECT role_code, base_role FROM user_profiles")}
        assert values["USER_ADMIN"] == "USER_ADMIN" and values["CUSTOMER"] == "CUSTOMER"
        assert values["SUPPORT_TEAM_01"] == "PLATFORM_MANAGER" and len(values) == 5


# Checks that a built-in role already suspended in an older database rejects new registrations.
@pytest.mark.parametrize("code,prefix", [("CUSTOMER", "customer"), ("INTERIOR_DESIGNER", "designer")])
def test_registration_rejects_inactive_builtin_profile(web, code, prefix):
    _, db = web
    db.execute("UPDATE user_profiles SET status = 'SUSPENDED' WHERE role_code = ?", (code,))
    app = create_app(db.path, testing=True)
    email = "new-registration@example.test"

    response = app.test_client().post(f"/{prefix}/register", data={
        "name": "New User", "email": email, "password": PASSWORD, "contactNumber": "91234567",
    })

    assert response.status_code == 200
    assert account_id(db, email) is None
    expected = "Registration is unavailable because this role is inactive. Please contact the administrator."
    assert expected in banners(response)
    assert f'value="{email}"' in html(response)


# ---------------------------------------------------------------- bug 5: company first
class TestBug5CompanyFirst:
    # Checks a designer without company information is sent to add it before creating a project.
    def test_create_project_requires_company(self, web, password_hash):
        app, db = web
        add_account(db, password_hash, "New Designer", "new@example.test", "INTERIOR_DESIGNER")
        designer = sign_in(app, "designer", "new@example.test")
        response = designer.get("/designer/projects/new", follow_redirects=True)
        assert "Please add your company information before creating a project." in banners(response)
        assert response.request.path == "/designer/company/new"
        category = db.scalar("SELECT category_id FROM project_categories LIMIT 1")
        posted = designer.post("/designer/projects/new", data={"title": "T", "categoryId": category,
                                                                "projectStatus": "CURRENT", "budget": "1000"},
                               follow_redirects=True)
        assert "Please add your company information before creating a project." in banners(posted)
        assert db.scalar("SELECT COUNT(*) FROM interior_design_projects") == 0


# ---------------------------------------------------------------- bugs 6 and 7: budget rules
class TestBug6And7Budget:
    # Posts the create-project form with a budget and returns the response.
    def create(self, app, db, budget):
        designer = sign_in(app, "designer", "designer@example.test")
        category = db.scalar("SELECT category_id FROM project_categories LIMIT 1")
        return designer.post("/designer/projects/new", data={"title": "Budget Test", "categoryId": category,
                                                              "projectStatus": "CURRENT", "budget": budget},
                             follow_redirects=True)

    # Checks budgets above S$10,000,000, negative or not numbers are rejected with one clear message.
    @pytest.mark.parametrize("budget", ["10000001", "1e300", "-5", "abc", "inf"])
    def test_budget_out_of_range(self, web, budget):
        app, db = web
        assert "Budget must be between S$0 and S$10,000,000." in banners(self.create(app, db, budget))

    # Checks the top of the range is accepted.
    def test_budget_maximum_accepted(self, web):
        app, db = web
        assert "Project created successfully." in banners(self.create(app, db, "10000000"))

    # Checks a blank budget asks for one.
    def test_blank_budget(self, web):
        app, db = web
        assert "Please enter a budget." in banners(self.create(app, db, ""))

    # Checks the customer budget filter uses the same range.
    def test_customer_filter_range(self, web):
        app, _ = web
        customer = sign_in(app, "customer", "customer@example.test")
        response = customer.get("/customer/projects?minBudget=0&maxBudget=20000000")
        assert "Budget must be between S$0 and S$10,000,000." in banners(response)


# ---------------------------------------------------------------- US26 and US29: photo validation errors
class TestProjectPhotoValidation:
    # Keeps the stored photo and entered fields when edit validation rejects the form.
    @pytest.mark.parametrize("field,message", [("title", "Please enter a title."),
                                             ("budget", "Please enter a budget.")])
    @pytest.mark.parametrize("with_photo", [False, True], ids=["no-upload", "upload"])
    def test_edit_form_keeps_original_photo_on_validation_error(self, web, tmp_path, monkeypatch,
                                                                 field, message, with_photo):
        app, db = web
        uploads = tmp_path / "uploads"
        monkeypatch.setattr(designer_pages, "UPLOAD_DIR", str(uploads))
        original = "/static/sample-projects/kitchen.png"
        idp = add_project(db, photo=original)
        project_query = "SELECT * FROM interior_design_projects WHERE idp_id = ?"
        before = db.query_one(project_query, (idp,))
        designer = sign_in(app, "designer", "designer@example.test")
        data = {"title": "Edited Title", "description": "Unsaved description", "categoryId": str(before["category_id"]),
                "projectStatus": "PAST", "budget": "1500"}
        data[field] = ""
        if with_photo:
            new_photo = Path(ROOT, "app", "static", "sample-projects", "bedroom.png")
            data["photo"] = (BytesIO(new_photo.read_bytes()), "bedroom.png")
            message += " Please choose the new photo again."

        response = designer.post(f"/designer/projects/{idp}/edit", data=data, content_type="multipart/form-data")

        assert response.status_code == 200
        assert message in banners(response)
        assert original in html(response) and "Unsaved description" in html(response)
        assert db.query_one(project_query, (idp,)) == before
        assert not list(uploads.glob("*"))

    # Discards a rejected upload from the create form and asks the designer to select it again.
    def test_create_form_discards_photo_on_validation_error(self, web, tmp_path, monkeypatch):
        app, db = web
        uploads = tmp_path / "uploads"
        monkeypatch.setattr(designer_pages, "UPLOAD_DIR", str(uploads))
        designer = sign_in(app, "designer", "designer@example.test")
        category = db.scalar("SELECT category_id FROM project_categories LIMIT 1")
        photo = Path(ROOT, "app", "static", "sample-projects", "bedroom.png")

        response = designer.post("/designer/projects/new", data={
            "title": "", "description": "Unsaved description", "categoryId": str(category),
            "projectStatus": "PAST", "budget": "1500", "photo": (BytesIO(photo.read_bytes()), "bedroom.png"),
        })

        assert response.status_code == 200
        assert "Please enter a title. Please choose the photo again." in banners(response)
        assert db.scalar("SELECT COUNT(*) FROM interior_design_projects") == 0
        assert not list(uploads.glob("*"))


# ---------------------------------------------------------------- bug 8: period statistics message
class TestBug8PeriodMessage:
    # Checks an impossible date is reported as an invalid date, while a missing one still asks for both.
    def test_invalid_date_message(self, web):
        app, db = web
        add_project(db)
        designer = sign_in(app, "designer", "designer@example.test")
        bad = designer.get("/designer/statistics/period?period=MONTH&date=2026-13-01&show=views")
        assert "Please choose a valid date." in banners(bad)
        far = designer.get("/designer/statistics/period?period=WEEK&date=9999-12-31&show=views")
        assert "Please choose a valid date." in banners(far)
        missing = designer.get("/designer/statistics/period?period=MONTH&date=&show=views")
        assert "Please choose a period and a date." in banners(missing)


# ---------------------------------------------------------------- confusing behaviour
class TestConfusingBehaviour:
    # Checks staff lists show 20 rows per page with page numbers, and keep the search when paging.
    def test_staff_lists_are_paged(self, web, password_hash):
        app, db = web
        for i in range(30):
            add_account(db, password_hash, f"Pat {i:02d}", f"pat{i:02d}@example.test", "CUSTOMER")
        admin = sign_in(app, "admin", "admin@example.test")
        first = html(admin.get("/admin/accounts"))
        assert first.count("<tr>") - 1 == 20 and 'aria-label="Page 2"' in first and "34 accounts" in first
        second = html(admin.get("/admin/accounts?page=2"))
        assert second.count("<tr>") - 1 == 14
        searched = html(admin.get("/admin/accounts?keyword=pat"))
        assert re.search(r'href="/admin/accounts\?[^"]*keyword=pat[^"]*page=2|href="/admin/accounts\?[^"]*page=2[^"]*keyword=pat', searched)
        for name in range(25):
            db.execute("INSERT INTO project_categories (name) VALUES (?)", (f"Extra {name:02d}",))
        manager = sign_in(app, "pm", "pm@example.test")
        assert 'aria-label="Page 2"' in html(manager.get("/pm/categories"))
        bad = admin.get("/admin/accounts?page=9")
        assert "Page 9 does not exist. There are 2 pages." in banners(bad)

    # Checks dates are shown as "9 Jun 2026" style, not raw database timestamps.
    def test_friendly_dates(self, web):
        app, db = web
        idp = add_project(db)
        admin = sign_in(app, "admin", "admin@example.test")
        view = html(admin.get(f"/admin/accounts/{account_id(db, 'customer@example.test')}"))
        assert "9 Jun 2026, 1:59 PM" in view and "2026-06-09 13:59:40" not in view
        customer = sign_in(app, "customer", "customer@example.test")
        customer.post(f"/customer/projects/{idp}/save")
        favourites = html(customer.get("/customer/favourites"))
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", favourites, flags=re.S))
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b", visible)  # machine-readable <time> attributes may keep ISO
        detail = html(customer.get(f"/customer/projects/{idp}"))
        assert "28 Oct 2026" in detail

    # Checks the browser tab for an account shows the person's name.
    def test_account_tab_title(self, web):
        app, db = web
        admin = sign_in(app, "admin", "admin@example.test")
        page = html(admin.get(f"/admin/accounts/{account_id(db, 'customer@example.test')}"))
        assert "<title>Cora Customer · Renofolio</title>" in page

    # Checks a restart keeps the same secret key, so people stay logged in.
    def test_secret_key_survives_restart(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        path = str(tmp_path / "restart.db")
        first = create_app(path, testing=True)
        second = create_app(path, testing=True)
        assert first.config["SECRET_KEY"] == second.config["SECRET_KEY"]
        assert os.path.exists(os.path.join(str(tmp_path), ".renofolio_secret_key"))
        monkeypatch.setenv("SECRET_KEY", "from-environment")
        assert create_app(path, testing=True).config["SECRET_KEY"] == "from-environment"

    # Checks the key file is never committed.
    def test_secret_key_file_is_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore")) as handle:
            assert ".renofolio_secret_key" in handle.read()

    # Checks the fonts are served locally so an offline demo looks the same.
    def test_fonts_are_local(self, web):
        app, _ = web
        page = html(app.test_client().get("/"))
        assert "fonts.googleapis.com" not in page
        with open(os.path.join(ROOT, "app", "static", "style.css"), encoding="utf-8") as handle:
            css = handle.read()
        assert "@font-face" in css and "/static/fonts/" in css
        fonts = os.listdir(os.path.join(ROOT, "app", "static", "fonts"))
        assert any(f.startswith("inter") for f in fonts) and any(f.startswith("fraunces") for f in fonts)

    # Checks the first page shows preview tiles with different photos.
    def test_first_page_photos_differ(self, web):
        app, db = web
        # The three newest projects share one photo, so picking the newest three would repeat it.
        for i, room in enumerate(["bedroom", "bathroom", "kitchen", "kitchen", "kitchen"]):
            add_project(db, title=f"Room {i}", photo=f"/static/sample-projects/{room}.png")
        page = html(app.test_client().get("/"))
        photos = re.findall(r'class="board-tile[^"]*" style="[^"]*url\(\'([^\']+)\'\)', page)
        assert len(photos) == 3 and len(set(photos)) == 3

    # Checks staff table action buttons stay on one line.
    def test_row_actions_do_not_wrap(self):
        with open(os.path.join(ROOT, "app", "static", "style.css"), encoding="utf-8") as handle:
            css = handle.read()
        assert re.search(r"\.row-actions\s*\{[^}]*flex-wrap:\s*nowrap", css)


# ---------------------------------------------------------------- sample data text
class TestSampleData:
    # Checks generated descriptions keep proper nouns capitalised and use "an HDB".
    def test_generated_text_case(self, tmp_path):
        path = str(tmp_path / "generated.db")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "generate_test_data.py"), "--db", path],
                       check=True, capture_output=True)
        init_db(path)
        db = DatabaseConnection()
        texts = [r["description"] for r in db.query("SELECT description FROM interior_design_projects")]
        texts += [r["description"] for r in db.query("SELECT description FROM companies")]
        joined = " ".join(texts)
        assert " hdb " not in joined and "a HDB" not in joined and "an HDB" in joined
        assert not re.search(r"\b(peranakan|japandi|scandinavian)\b", joined)
        assert db.scalar("SELECT COUNT(*) FROM user_accounts") == 282
        staff_on_custom = db.scalar(
            "SELECT COUNT(*) FROM user_accounts a JOIN user_profiles p USING (profile_id) "
            "WHERE p.role_code NOT IN ('CUSTOMER', 'INTERIOR_DESIGNER', 'USER_ADMIN', 'PLATFORM_MANAGER')")
        assert staff_on_custom > 0


# ---------------------------------------------------------------- 9 November: no "Page X of Y" text
class TestNoPageOfText:
    # Checks no list shows "Page X of Y": the highlighted number and the last page number already say it.
    def test_page_of_text_removed_everywhere(self, web, password_hash):
        app, db = web
        for i in range(13):
            add_project(db, title=f"Kitchen {i:02d}")
        for i in range(25):
            add_account(db, password_hash, f"Pat {i:02d}", f"pat{i:02d}@example.test", "CUSTOMER")
            db.execute("INSERT INTO project_categories (name) VALUES (?)", (f"Extra {i:02d}",))
        customer = sign_in(app, "customer", "customer@example.test")
        admin = sign_in(app, "admin", "admin@example.test")
        manager = sign_in(app, "pm", "pm@example.test")
        for client, url in [(customer, "/customer/projects"), (customer, "/customer/projects?page=2"),
                            (admin, "/admin/accounts"), (admin, "/admin/profiles"), (manager, "/pm/categories")]:
            page = html(client.get(url))
            assert not re.search(r"Page \d+ of \d+", page), url
        page = html(customer.get("/customer/projects?page=2"))
        assert 'aria-current="page">2</span>' in page and "Go to Page" in page
