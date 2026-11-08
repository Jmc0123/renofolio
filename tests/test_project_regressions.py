"""Regression tests for project budgets and uploaded previews."""

from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from app.boundary import designer_pages
from app.entity.database import DatabaseConnection, init_db
from tests.conftest import PASSWORD, make_category, make_customer, make_designer, make_project


ASSETS = Path(__file__).resolve().parents[1] / "app" / "static" / "sample-projects"


# Gives the two roles their own browsers and keeps any uploaded files in the test folder.
@pytest.fixture
def project_site(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "projects.db"), testing=True)
    app.static_folder = str(tmp_path / "static")
    uploads = tmp_path / "static" / "uploads" / "idp"
    monkeypatch.setattr(designer_pages, "UPLOAD_DIR", str(uploads))
    session, _ = make_designer()
    make_customer()
    category = make_category("Industrial Dining Room")
    designer, customer = app.test_client(), app.test_client()
    for client, role, email in [(designer, "designer", "dan@example.test"),
                                (customer, "customer", "amy@example.test")]:
        response = client.post(f"/{role}/login", data={"email": email, "password": PASSWORD})
        assert response.status_code == 302
    return designer, customer, DatabaseConnection(), session, category, uploads


# Builds the designer's existing project form data, including an optional uploaded PNG.
def project_form(category, photo=None):
    data = {"title": "Industrial Dining Room", "categoryId": str(category),
            "description": "Concrete walls", "projectStatus": "PAST", "budget": "28450.49"}
    if photo is not None:
        data["photo"] = (BytesIO(photo), "photo.png")
    return data


# Uses the response's project ID to look up the exact stored preview.
def saved_photo(response, db):
    assert response.status_code == 302
    project_id = int(response.location.rsplit("/", 1)[-1])
    url = db.scalar("SELECT photo_url FROM interior_design_projects WHERE idp_id = ?", (project_id,))
    assert url
    return project_id, url


# Rejects a PNG with a valid header but missing pixel data without saving a project or file.
def test_damaged_photo_does_not_publish_a_project(project_site):
    designer, _, db, _, category, uploads = project_site
    broken = (ASSETS / "dining-room.png").read_bytes()[:33]
    response = designer.post("/designer/projects/new", data=project_form(category, broken))
    assert response.status_code == 200
    assert b"Please choose a valid JPG, PNG or WebP image." in response.data
    assert db.scalar("SELECT COUNT(*) FROM interior_design_projects") == 0
    assert not list(uploads.glob("*"))


# A failed replacement keeps the published preview intact.
def test_damaged_replacement_preserves_the_published_photo(project_site):
    designer, customer, db, _, category, uploads = project_site
    good = (ASSETS / "dining-room.png").read_bytes()
    created = designer.post("/designer/projects/new", data=project_form(category, good))
    project_id, original = saved_photo(created, db)
    response = designer.post(f"/designer/projects/{project_id}/edit", data=project_form(category, good[:33]))
    assert response.status_code == 200
    assert db.scalar("SELECT photo_url FROM interior_design_projects WHERE idp_id = ?", (project_id,)) == original
    assert customer.get(original).data == good
    assert [file.name for file in uploads.iterdir()] == [original.rsplit("/", 1)[-1]]


# Replacing and then deleting a project removes both superseded and final upload files.
def test_replaced_and_deleted_photo_urls_stop_working(project_site):
    designer, customer, db, _, category, uploads = project_site
    created = designer.post("/designer/projects/new",
                            data=project_form(category, (ASSETS / "dining-room.png").read_bytes()))
    project_id, original = saved_photo(created, db)
    edited = designer.post(f"/designer/projects/{project_id}/edit",
                           data=project_form(category, (ASSETS / "living-room.png").read_bytes()))
    _, replacement = saved_photo(edited, db)
    assert original != replacement
    assert customer.get(original).status_code == 404
    assert not (uploads / original.rsplit("/", 1)[-1]).exists()
    assert customer.get(replacement).status_code == 200
    assert designer.post(f"/designer/projects/{project_id}/delete").status_code == 302
    assert customer.get(replacement).status_code == 404
    assert not list(uploads.iterdir())


# Old unreferenced uploads return 404, while legacy uploads shared by two projects stay available.
def test_legacy_upload_access_tracks_project_references(project_site):
    designer, customer, db, session, category, uploads = project_site
    uploads.mkdir(parents=True)
    old_file = uploads / "legacy.png"
    old_file.write_bytes((ASSETS / "dining-room.png").read_bytes())
    url = "/static/uploads/idp/legacy.png"
    assert customer.get(url).status_code == 404
    first = make_project(session, category, "First Legacy Project")
    second = make_project(session, category, "Second Legacy Project")
    db.execute("UPDATE interior_design_projects SET photo_url = ?", (url,))
    assert designer.post(f"/designer/projects/{first}/delete").status_code == 302
    assert old_file.is_file() and customer.get(url).status_code == 200
    assert designer.post(f"/designer/projects/{second}/delete").status_code == 302
    assert not old_file.exists() and customer.get(url).status_code == 404


# A displayed price can be copied into the combined filter without losing the project.
def test_budget_cents_agree_between_details_and_filter(project_site):
    designer, customer, db, _, category, _ = project_site
    response = designer.post("/designer/projects/new", data=project_form(category))
    project_id = int(response.location.rsplit("/", 1)[-1])
    assert b"S$28,450.49" in customer.get(f"/customer/projects/{project_id}").data
    detail_link = f'href="/customer/projects/{project_id}?'.encode()
    match = customer.get("/customer/projects?minBudget=0&maxBudget=28450.49").data
    assert detail_link in match and b"S$28,450.49" in match
    assert detail_link not in customer.get("/customer/projects?minBudget=0&maxBudget=28450.48").data
    assert db.scalar("SELECT budget FROM interior_design_projects WHERE idp_id = ?", (project_id,)) == 28450.49


# Old fractions of a cent are normalized on startup and new inputs use the same precision.
def test_existing_and_new_budgets_use_cents(project_site):
    designer, customer, db, session, category, _ = project_site
    legacy = make_project(session, category, "Legacy Dining Room")
    db.execute("UPDATE interior_design_projects SET budget = 28450.491 WHERE idp_id = ?", (legacy,))
    init_db(db.path)
    assert db.scalar("SELECT budget FROM interior_design_projects WHERE idp_id = ?", (legacy,)) == 28450.49
    filtered = customer.get("/customer/projects?minBudget=0&maxBudget=28450.49").data
    assert b"Legacy Dining Room" in filtered and b"S$28,450.49" in filtered
    data = project_form(category)
    data["budget"] = "28450.495"
    result = designer.post("/designer/projects/new", data=data)
    project_id = int(result.location.rsplit("/", 1)[-1])
    assert db.scalar("SELECT budget FROM interior_design_projects WHERE idp_id = ?", (project_id,)) == 28450.50
