"""Acceptance checks for the Final US42–US59 use cases and their cross-role effects."""
from datetime import datetime, timedelta
from html import unescape
import re

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.common import clock
from app.common.text import friendly_datetime
from app.entity.database import DatabaseConnection
from tests.conftest import PASSWORD


# Builds one password hash for the test accounts.
@pytest.fixture(scope="module")
def password_hash():
    return generate_password_hash(PASSWORD)


# Builds an app with one account per role and a designer company.
@pytest.fixture
def web(tmp_path, password_hash, frozen_clock):
    app = create_app(str(tmp_path / "final-web.db"), testing=True)
    db = DatabaseConnection()
    people = [
        ("Ada Admin", "admin@example.test", "USER_ADMIN"),
        ("Mia Manager", "pm@example.test", "PLATFORM_MANAGER"),
        ("Dan Designer", "designer@example.test", "INTERIOR_DESIGNER"),
        ("Cora Customer", "customer@example.test", "CUSTOMER"),
    ]
    for name, email, code in people:
        db.execute(
            "INSERT INTO user_accounts (name, email, password_hash, contact_number, profile_id, "
            "created_at, updated_at) SELECT ?, ?, ?, '91234567', profile_id, ?, ? "
            "FROM user_profiles WHERE role_code = ?",
            (name, email, password_hash, "2026-01-01 00:00:00", "2026-01-01 00:00:00", code),
        )
    # Since 8 November a designer needs company information before creating projects (bug 5).
    db.execute("INSERT INTO companies (designer_id, company_name, contact_email, contact_number, created_at, updated_at) "
               "SELECT account_id, 'Dan Studio', 'dan@studio.test', '61234567', ?, ? FROM user_accounts "
               "WHERE email = 'designer@example.test'", ("2026-01-01 00:00:00", "2026-01-01 00:00:00"))
    return app, db


# Logs a test client in on a role's login page.
def sign_in(app, prefix, email=None):
    client = app.test_client()
    response = client.post(f"/{prefix}/login", data={"email": email or f"{prefix}@example.test", "password": PASSWORD})
    assert response.status_code == 302
    return client


# Checks a page opened and returns its decoded HTML.
def page(response):
    assert response.status_code == 200, response.status_code
    return unescape(response.get_data(as_text=True))


# Returns the profile ID for a role code.
def profile(db, code):
    return db.scalar("SELECT profile_id FROM user_profiles WHERE role_code = ?", (code,))


# Returns an account row by email.
def account(db, email):
    return db.query_one("SELECT * FROM user_accounts WHERE email = ?", (email,))


# Returns valid Create Staff Account form values that tests can override.
def staff_fields(db, **overrides):
    return dict({"displayName": "New Staff", "email": "staff@example.test", "password": PASSWORD,
                 "profileId": profile(db, "PLATFORM_MANAGER"), "contactNumber": "98765432"}, **overrides)


# Adds a project for the designer straight into the database.
def add_project(db, category_id, *, title="Studio Project", created_at=None, removed_at=None):
    designer = account(db, "designer@example.test")["account_id"]
    stamp = created_at or clock.now_text()
    return db.execute(
        "INSERT INTO interior_design_projects (designer_id, title, category_id, project_status, budget, "
        "created_at, updated_at, removed_at) VALUES (?, ?, ?, 'CURRENT', 25000, ?, ?, ?)",
        (designer, title, category_id, stamp, stamp, removed_at),
    )


# Checks US42 staff creation and US43 private details.
@pytest.mark.parametrize("role,prefix", [("USER_ADMIN", "admin"), ("PLATFORM_MANAGER", "pm")])
def test_us42_staff_creation_and_us43_private_details(web, role, prefix):
    app, db = web
    admin = sign_in(app, "admin")
    form = page(admin.get("/admin/accounts/new"))
    assert 'name="username"' not in form
    response = admin.post("/admin/accounts/new", data=staff_fields(db, profileId=profile(db, role)))
    assert response.status_code == 302
    saved = account(db, "staff@example.test")
    assert saved["profile_id"] == profile(db, role) and saved["status"] == "ACTIVE"
    assert saved["password_hash"] != PASSWORD and check_password_hash(saved["password_hash"], PASSWORD)
    assert saved["password_hash"] != account(db, "admin@example.test")["password_hash"]
    html = page(admin.get(response.headers["Location"]))
    for label in ("Account created.", "New Staff", "98765432", friendly_datetime(saved["created_at"]), "Edit",
                  "Suspend"):
        assert label in html
    assert saved["password_hash"] not in html
    sign_in(app, prefix, "staff@example.test")


# Checks US42 invalid or duplicate staff creation changes nothing.
@pytest.mark.parametrize("case", ["no-contact", "bad-contact", "custom", "inactive-staff", "customer", "duplicate"])
def test_us42_invalid_or_duplicate_staff_creation_changes_nothing(web, case):
    app, db = web
    admin = sign_in(app, "admin")
    fields = staff_fields(db, username="legacy-staff")
    if case == "no-contact":
        fields["contactNumber"] = ""
    elif case == "bad-contact":
        fields["contactNumber"] = "abc"
    elif case == "custom":
        # 8 November: custom staff profiles are allowed, but a custom profile based on Customer is not staff.
        fields["profileId"] = db.execute(
            "INSERT INTO user_profiles (role_code, role_name, base_role, created_at, updated_at) VALUES "
            "('SUPPORT', 'Support', 'CUSTOMER', ?, ?)", (clock.now_text(), clock.now_text()))
        assert ">Support" not in page(admin.get("/admin/accounts/new"))
    elif case == "inactive-staff":
        db.execute("UPDATE user_profiles SET status='SUSPENDED' WHERE role_code='PLATFORM_MANAGER'")
    elif case == "customer":
        fields["profileId"] = profile(db, "CUSTOMER")
    else:
        fields["email"] = " CUSTOMER@EXAMPLE.TEST "
    count = db.scalar("SELECT COUNT(*) FROM user_accounts")
    html = page(admin.post("/admin/accounts/new", data=fields))
    assert db.scalar("SELECT COUNT(*) FROM user_accounts") == count
    assert PASSWORD not in html
    assert "This email is already registered." in html if case == "duplicate" else "banner error" in html


# Checks US43 and US48 missing records show messages.
def test_us43_and_us48_missing_records_show_messages(web):
    app, _ = web
    admin = sign_in(app, "admin")
    for path, message in (("/admin/accounts/9999", "This account no longer exists."),
                          ("/admin/profiles/9999", "This profile no longer exists.")):
        assert message in page(admin.get(path, follow_redirects=True))


# Checks US44 update preserves role even with forged profile.
def test_us44_update_preserves_role_even_with_forged_profile(web):
    app, db = web
    admin = sign_in(app, "admin")
    old = account(db, "pm@example.test")
    url = f"/admin/accounts/{old['account_id']}/edit"
    assert '<select id="profileId"' not in page(admin.get(url))
    response = admin.post(url, data={"displayName": "Mia Updated", "email": "mia@example.test",
                                    "contactNumber": "81234567", "profileId": profile(db, "USER_ADMIN")})
    assert response.status_code == 302
    updated = account(db, "mia@example.test")
    assert updated["profile_id"] == old["profile_id"] and updated["password_hash"] == old["password_hash"]
    assert updated["contact_number"] == "81234567" and updated["name"] == "Mia Updated"
    assert not account(db, "pm@example.test")
    sign_in(app, "pm", "mia@example.test")


# Checks US44 duplicate email cannot partially change account.
def test_us44_duplicate_email_cannot_partially_change_account(web):
    app, db = web
    admin = sign_in(app, "admin")
    old = account(db, "pm@example.test")
    html = page(admin.post(f"/admin/accounts/{old['account_id']}/edit", data={
        "displayName": "New name", "email": "CUSTOMER@example.test", "contactNumber": "81234567",
    }))
    assert "This email is already used by another account." in html
    assert account(db, "pm@example.test") == old


# Checks US45 self protection cancel and session revocation.
def test_us45_self_protection_cancel_and_session_revocation(web):
    app, db = web
    admin = sign_in(app, "admin")
    own = account(db, "admin@example.test")["account_id"]
    html = page(admin.post(f"/admin/accounts/{own}/suspend", follow_redirects=True))
    assert "You cannot suspend your own account." in html
    assert account(db, "admin@example.test")["status"] == "ACTIVE"
    first = sign_in(app, "pm")
    second = sign_in(app, "pm")
    target = account(db, "pm@example.test")["account_id"]
    path = f"/admin/accounts/{target}/suspend"
    assert "Cancel" in page(admin.get(path))
    assert account(db, "pm@example.test")["status"] == "ACTIVE"
    assert db.scalar("SELECT COUNT(*) FROM sessions WHERE account_id=?", (target,)) == 2
    assert "Account suspended." in page(admin.post(path, follow_redirects=True))
    assert db.scalar("SELECT COUNT(*) FROM sessions WHERE account_id=?", (target,)) == 0
    assert account(db, "pm@example.test")["status"] == "SUSPENDED"
    for client in (first, second):
        assert client.get("/pm/reports").headers["Location"] == "/pm/login"
    assert "This account is already suspended." in page(admin.post(path, follow_redirects=True))


# Checks US46 and US48 search count covers all matches.
def test_us46_and_us48_search_count_covers_all_matches(web, password_hash):
    app, db = web
    admin = sign_in(app, "admin")
    pid = profile(db, "CUSTOMER")
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO user_accounts (name, email, password_hash, profile_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(f"Case Person {i:03d}", f"person{i}@example.test", password_hash, pid, clock.now_text(),
              clock.now_text()) for i in range(205)],
        )
    assert "206 accounts" in page(admin.get(f"/admin/profiles/{pid}"))
    html = page(admin.get(f"/admin/accounts?keyword=&profileId={pid}"))
    assert "206 accounts with the selected profile" in html and 'aria-label="Page 11"' in html
    assert "Case Person 204" in page(admin.get(f"/admin/accounts?keyword=&profileId={pid}&page=11"))  # 20 per page
    assert "205 accounts match 'CASE PERSON'" in page(admin.get(f"/admin/accounts?keyword=CASE+PERSON&profileId={pid}"))
    assert "No accounts match" in page(admin.get(f"/admin/accounts?keyword=Mia&profileId={pid}"))


# Checks explicit empty submission validates.
@pytest.mark.parametrize("path,message", [
    ("/admin/accounts?keyword=&profileId=", "Please enter a name, email or profile."),
    ("/admin/profiles?keyword=+", "Please enter a keyword."),
    ("/pm/categories?keyword=", "Please enter a keyword."),
    ("/pm/reports?periodType=DAY&periodValue=", "Please select a date."),
    ("/pm/reports?periodType=WEEK&periodValue=", "Please select a week."),
    ("/pm/reports?periodType=MONTH&periodValue=", "Please select a month."),
])
def test_explicit_empty_submission_validates(web, path, message):
    app, _ = web
    client = sign_in(app, path.split("/")[1])
    assert message in page(client.get(path))
    assert message not in page(client.get(path.split("?")[0]))


# Checks US47 create by name and reject duplicate role name.
def test_us47_create_by_name_and_reject_duplicate_role_name(web):
    app, db = web
    admin = sign_in(app, "admin")
    assert 'name="roleCode"' not in page(admin.get("/admin/profiles/new"))
    create = admin.post("/admin/profiles/new", data={"displayName": "Support Team", "description": "Assists customers",
                                                     "basedOn": "PLATFORM_MANAGER"})
    assert create.status_code == 302
    created = db.query_one("SELECT * FROM user_profiles WHERE role_name='Support Team'")
    assert created["status"] == "ACTIVE" and created["role_code"]
    duplicate = admin.post("/admin/profiles/new", data={"displayName": " support TEAM ", "roleCode": "ANOTHER_ROLE",
                                                        "basedOn": "PLATFORM_MANAGER"})
    assert "This role name already exists." in page(duplicate)
    assert db.scalar("SELECT COUNT(*) FROM user_profiles") == 5
    assert "Support Team" in page(admin.get("/admin/profiles?keyword=ASSISTS"))


# Checks US49 description only and nonempty.
def test_us49_description_only_and_nonempty(web):
    app, db = web
    admin = sign_in(app, "admin")
    pid = profile(db, "CUSTOMER")
    url = f"/admin/profiles/{pid}/edit"
    before = db.query_one("SELECT * FROM user_profiles WHERE profile_id=?", (pid,))
    assert "Please enter a description." in page(admin.post(url, data={"displayName": "Renamed", "description": ""}))
    assert db.query_one("SELECT * FROM user_profiles WHERE profile_id=?", (pid,)) == before
    assert admin.post(url, data={"displayName": "Forged name", "description": "Updated description"}).status_code == 302
    after = db.query_one("SELECT * FROM user_profiles WHERE profile_id=?", (pid,))
    assert after["role_name"] == before["role_name"] and after["role_code"] == before["role_code"]
    assert after["description"] == "Updated description"


# Checks US50 protected admin role and bulk session revocation.
def test_us50_protected_admin_role_and_bulk_session_revocation(web):
    app, db = web
    admin = sign_in(app, "admin")
    admin_pid = profile(db, "USER_ADMIN")
    blocked = admin.post(f"/admin/profiles/{admin_pid}/suspend", follow_redirects=True)
    assert "Built-in profiles cannot be suspended." in page(blocked)  # 8 November: all four built-in profiles
    # A custom staff profile is used for the bulk logout, since built-in profiles are protected.
    admin.post("/admin/profiles/new", data={"displayName": "Report Team", "basedOn": "PLATFORM_MANAGER"})
    pid = db.scalar("SELECT profile_id FROM user_profiles WHERE role_name = 'Report Team'")
    db.execute("UPDATE user_accounts SET profile_id = ? WHERE email = 'pm@example.test'", (pid,))
    first, second = sign_in(app, "pm"), sign_in(app, "pm")
    old = account(db, "pm@example.test")
    url = f"/admin/profiles/{pid}/suspend"
    assert "Cancel" in page(admin.get(url))
    assert db.scalar("SELECT status FROM user_profiles WHERE profile_id=?", (pid,)) == "ACTIVE"
    assert "Profile suspended." in page(admin.post(url, follow_redirects=True))
    assert db.scalar("SELECT COUNT(*) FROM sessions WHERE account_id=?", (old["account_id"],)) == 0
    assert account(db, "pm@example.test") == old
    for client in (first, second):
        assert client.get("/pm/reports").headers["Location"] == "/pm/login"


# Checks US46 US51 US56 treat wildcards as literal text.
def test_us46_us51_us56_treat_wildcards_as_literal_text(web):
    app, _ = web
    admin, manager = sign_in(app, "admin"), sign_in(app, "pm")
    for client, path, noun in ((admin, "/admin/accounts", "accounts"),
                               (admin, "/admin/profiles", "profiles"),
                               (manager, "/pm/categories", "categories")):
        assert f"No {noun} match '%'" in page(client.get(path + "?keyword=%25"))


# Checks US52 visible count and US55 hidden project still blocks removal.
def test_us52_visible_count_and_us55_hidden_project_still_blocks_removal(web):
    app, db = web
    manager = sign_in(app, "pm")
    cid = db.execute("INSERT INTO project_categories (name) VALUES ('Suspended Studio Category')")
    add_project(db, cid)
    db.execute("UPDATE user_accounts SET status='SUSPENDED' WHERE email='designer@example.test'")
    html = page(manager.get("/pm/categories"))
    assert re.search(r'Suspended Studio Category</td><td class="num">0</td>', html)
    assert "used by 1 project and" in page(manager.post(f"/pm/categories/{cid}/remove", follow_redirects=True))
    assert db.scalar("SELECT COUNT(*) FROM project_categories WHERE category_id=?", (cid,)) == 1
    db.execute("UPDATE user_accounts SET status='ACTIVE' WHERE email='designer@example.test'")
    html = page(manager.get("/pm/categories"))
    assert re.search(r'Suspended Studio Category</td><td class="num">1</td>', html)


# Checks US53 single letter category and US54 rename in designer and customer.
def test_us53_single_letter_category_and_us54_rename_in_designer_and_customer(web):
    app, db = web
    manager = sign_in(app, "pm")
    assert "Category created." in page(manager.post("/pm/categories", data={"name": " X "}, follow_redirects=True))
    cid = db.scalar("SELECT category_id FROM project_categories WHERE name='X'")
    assert cid
    idp = add_project(db, cid)
    assert "already exists" in page(manager.post("/pm/categories", data={"name": "x"}, follow_redirects=True))
    assert manager.post(f"/pm/categories/{cid}/edit", data={"name": "Updated Category"}).status_code == 302
    assert db.scalar("SELECT category_id FROM interior_design_projects WHERE idp_id=?", (idp,)) == cid
    designer, customer = sign_in(app, "designer"), sign_in(app, "customer")
    assert "Updated Category" in page(designer.get("/designer/projects/new"))
    assert "Updated Category" in page(customer.get(f"/customer/projects?categoryId={cid}"))
    assert "1 category matches 'UPDATED'" in page(manager.get("/pm/categories?keyword=UPDATED"))


# Checks US57 US59 four metrics count all roles and historical saves.
@pytest.mark.parametrize("period,value,start,end", [
    ("DAY", "2026-10-15", "2026-10-15 00:00:00", "2026-10-16 00:00:00"),
    ("WEEK", "2026-10-14", "2026-10-12 00:00:00", "2026-10-19 00:00:00"),
    ("MONTH", "2024-02", "2024-02-01 00:00:00", "2024-03-01 00:00:00"),
])
def test_us57_us59_four_metrics_count_all_roles_and_historical_saves(web, period, value, start, end):
    app, db = web
    manager = sign_in(app, "pm")
    before_start = (datetime.fromisoformat(start) - timedelta(seconds=1)).isoformat(sep=" ")
    last = (datetime.fromisoformat(end) - timedelta(seconds=1)).isoformat(sep=" ")
    db.execute("UPDATE user_accounts SET created_at=?", (start,))
    cid = db.execute("INSERT INTO project_categories (name) VALUES ('Report Category')")
    inside = add_project(db, cid, created_at=start)
    add_project(db, cid, created_at=end)
    legacy = add_project(db, cid, created_at=start, removed_at=end)
    customer = account(db, "customer@example.test")["account_id"]
    with db.transaction() as conn:
        conn.executemany("INSERT INTO project_views (idp_id, customer_id, viewed_at) VALUES (?, ?, ?)",
                         [(inside, customer, ts) for ts in (before_start, start, last, end)] + [(legacy, customer, last)])
        conn.executemany("INSERT INTO favourites (idp_id, customer_id, saved_at, removed_at) VALUES (?, ?, ?, ?)",
                         [(inside, customer, start, last), (inside, customer, last, end),
                          (inside, customer, end, None), (legacy, customer, last, None)])
    tables = ("user_accounts", "interior_design_projects", "project_views", "favourites")
    before = [db.query(f"SELECT * FROM {table}") for table in tables]
    html = page(manager.get(f"/pm/reports?periodType={period}&periodValue={value}"))
    expected = {"New Accounts": 4, "New Projects": 1, "Project Views": 2, "New Saves": 2}
    for name, count in expected.items():
        assert re.search(rf'{name}</[^>]+>\s*<[^>]+>{count}</', html)
    assert "New customers" not in html and "Most viewed projects" not in html
    assert [db.query(f"SELECT * FROM {table}") for table in tables] == before


# Checks invalid report date is handled without server error.
@pytest.mark.parametrize("period,value", [("DAY", "9999-12-31"), ("WEEK", "2026-W99"), ("MONTH", "9999-12")])
def test_invalid_report_date_is_handled_without_server_error(web, period, value):
    app, _ = web
    manager = sign_in(app, "pm")
    assert "Please select a valid" in page(manager.get(f"/pm/reports?periodType={period}&periodValue={value}"))


# Checks staff routes require current session and role.
def test_staff_routes_require_current_session_and_role(web, frozen_clock):
    app, db = web
    customer = sign_in(app, "customer")
    assert customer.post("/admin/accounts/new", data=staff_fields(db)).headers["Location"] == "/admin/login"
    assert customer.post("/pm/categories", data={"name": "Forbidden"}).headers["Location"] == "/pm/login"
    admin, manager = sign_in(app, "admin"), sign_in(app, "pm")
    clock.freeze(frozen_clock + timedelta(minutes=31))
    assert admin.post("/admin/accounts/new", data=staff_fields(db)).headers["Location"] == "/admin/login"
    assert manager.get("/pm/reports?periodType=DAY&periodValue=2026-10-15").headers["Location"] == "/pm/login"
    assert not account(db, "staff@example.test")


# Checks v3 project edit keeps persisted photo and detail title.
def test_v3_project_edit_keeps_persisted_photo_and_detail_title(web):
    app, db = web
    designer, customer = sign_in(app, "designer"), sign_in(app, "customer")
    cid = db.execute("INSERT INTO project_categories (name) VALUES ('Preview')")
    pid = add_project(db, cid)
    original = "/static/sample-projects/kitchen.png"
    db.execute("UPDATE interior_design_projects SET photo_url=? WHERE idp_id=?", (original, pid))
    assert designer.post(f"/designer/projects/{pid}/edit", data={
        "title": "Studio Project", "categoryId": cid, "projectStatus": "PAST", "budget": "25000",
        "currentPhotoUrl": "/static/uploads/idp/forged.png",
    }).status_code == 302
    assert db.scalar("SELECT photo_url FROM interior_design_projects WHERE idp_id=?", (pid,)) == original
    html = page(customer.get(f"/customer/projects/{pid}"))
    assert re.search(r"<title>Studio Project[^<]*</title>", html)


# Checks v3 designer statistics reject date overflow.
def test_v3_designer_statistics_reject_date_overflow(web):
    app, _ = web
    designer = sign_in(app, "designer")
    html = page(designer.get("/designer/statistics/period?show=views&period=DAY&date=9999-12-31"))
    assert "Please choose a valid date." in html  # 8 November: an out-of-range date is named as such
