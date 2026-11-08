"""Acceptance checks for combined customer filters and persistent demo previews."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import re
import sqlite3
import subprocess
import sys

import pytest

from app import create_app
from app.common import clock
from tests.test_us01_us22_acceptance import acceptance_password_hash, sample, web, sign_in  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


class FilterForm(HTMLParser):
    # Starts an HTML reader that collects each form and its fields.
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.current = None
        self.feed(html)

    # Records a form and the inputs, selects and options inside it.
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action":attrs.get("action"), "fields":{}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current["fields"][attrs["name"]] = attrs.get("value", "")
        elif tag == "select" and self.current is not None and attrs.get("name"):
            self.current["fields"][attrs["name"]] = ""
            self.select = attrs["name"]
        elif tag == "option" and self.current is not None and "selected" in attrs:
            self.current["fields"][self.select] = attrs.get("value", "")

    # Closes the current form.
    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


# Returns the IDs of the project cards on a list page.
def project_ids(html):
    return set(map(int, re.findall(r'<article class="card project">.*?href="/customer/projects/(\d+)(?:\?[^"]*)?"', html, re.S)))


# Checks combined filters intersect instead of replacing each other.
@pytest.mark.parametrize("query,indices", [
    ({"keyword":"Project 0", "categoryId":"1"}, list(range(8))),
    ({"keyword":"Project 0", "status":"PAST"}, [1,3,5,7,9]),
    ({"keyword":"Project 0", "categoryId":"1", "status":"PAST", "minBudget":"12000", "maxBudget":"16000"}, [3,5]),
    ({"categoryId":"2", "status":"CURRENT", "minBudget":"18000", "maxBudget":"22000"}, [8,10,12]),
    ({"keyword":"timber", "categoryId":"1", "status":"current", "minBudget":"12000", "maxBudget":"16000"}, [2,4,6]),
])
def test_combined_filters_intersect_instead_of_replacing_each_other(web, sample, query, indices):
    sign_in(web)
    response = web.get("/customer/projects", query_string=query)
    assert response.status_code == 200
    assert project_ids(response.get_data(as_text=True)) == {sample["projects"][i] for i in indices}


# Checks one form retains every criterion when customer adds another filter.
def test_one_form_retains_every_criterion_when_customer_adds_another_filter(web):
    sign_in(web)
    html = web.get("/customer/projects", query_string={
        "keyword":"Catalogue", "categoryId":"1", "status":"PAST", "minBudget":"0", "maxBudget":"20000",
    }).get_data(as_text=True)
    forms = [f for f in FilterForm(html).forms if "keyword" in f["fields"]]
    assert len(forms) == 1
    assert forms[0]["action"] == "/customer/projects"
    assert forms[0]["fields"] == {
        "keyword":"Catalogue", "categoryId":"1", "status":"PAST", "minBudget":"0", "maxBudget":"20000",
    }
    # A user changes only the category and submits the same form: all other fields stay active.
    query = dict(forms[0]["fields"], categoryId="2")
    html = web.get(forms[0]["action"], query_string=query).get_data(as_text=True)
    assert "Catalogue Project 09" in html and "Catalogue Project 01" not in html


# Checks combined filter pagination retains all conditions.
def test_combined_filter_pagination_retains_all_conditions(web, sample):
    stamp = clock.now_text()
    matched = []
    for i in range(25):
        matched.append(sample["db"].execute(
            "INSERT INTO interior_design_projects (designer_id,title,description,category_id,project_status,"
            "budget,created_at,updated_at) VALUES (?, ?, 'Matched collection', 1, 'PAST', 15000, ?, ?)",
            (sample["accounts"]["designer"], f"Combination Kitchen {i:02d}", stamp, stamp),
        ))
    sign_in(web)
    query = {"keyword":"Combination", "categoryId":"1", "status":"PAST", "minBudget":"10000", "maxBudget":"20000"}
    html = web.get("/customer/projects", query_string=query).get_data(as_text=True)
    pages = []
    for expected_page in (1,2,3):
        ids = project_ids(html)
        assert len(ids) == (1 if expected_page == 3 else 12)
        pages.append(ids)
        next_link = re.search(r'href="([^"]+)">Next', html)
        if expected_page == 3:
            assert next_link is None
            break
        url = next_link.group(1).replace("&amp;", "&")
        actual = parse_qs(urlparse(url).query)
        assert all(actual.get(k) == [v] for k,v in query.items())
        assert actual["page"] == [str(expected_page+1)]
        html = web.get(url).get_data(as_text=True)
    assert set.union(*pages) == set(matched)
    assert not (pages[0] & pages[1] or pages[1] & pages[2] or pages[0] & pages[2])


# Checks combination no matches does not discard any conditions.
def test_combination_no_matches_does_not_discard_any_conditions(web):
    sign_in(web)
    query = {"keyword":"not-present-anywhere", "categoryId":"1", "status":"PAST", "minBudget":"0", "maxBudget":"100"}
    html = web.get("/customer/projects", query_string=query).get_data(as_text=True)
    assert not project_ids(html)
    assert "No projects match all selected filters." in html
    fields = next(f["fields"] for f in FilterForm(html).forms if "keyword" in f["fields"])
    assert fields == query


# Checks invalid combination shows error and keeps keyword.
@pytest.mark.parametrize("query,error", [
    ({"keyword":"x"*101}, "Keyword must be 100 characters or fewer."),
    ({"categoryId":"abc"}, "Please choose a valid category."),
    ({"categoryId":"-2"}, "Please choose a valid category."),
    ({"status":"ARCHIVED"}, "Status must be Current or Past."),
    ({"minBudget":"20000"}, "Please enter a minimum and maximum budget of 0 or more."),
    ({"maxBudget":"20000"}, "Please enter a minimum and maximum budget of 0 or more."),
    ({"minBudget":"0", "maxBudget":"inf"}, "Please enter a minimum and maximum budget of 0 or more."),
    ({"minBudget":"-1", "maxBudget":"20000"}, "Please enter a minimum and maximum budget of 0 or more."),
    ({"minBudget":"20000", "maxBudget":"10000"}, "Minimum budget cannot be higher than maximum."),
    ({"page":"0"}, "Invalid page number."),
    ({"page":"1.5"}, "Invalid page number."),
])
def test_invalid_combination_shows_error_and_keeps_keyword(web, query, error):
    sign_in(web)
    query = {"keyword":"Catalogue", **query}
    html = web.get("/customer/projects", query_string=query).get_data(as_text=True)
    assert error in html
    assert query["keyword"] in html
    assert not project_ids(html)


# Checks unavailable category clears only category and keeps other criteria.
def test_unavailable_category_clears_only_category_and_keeps_other_criteria(web, sample):
    sign_in(web)
    html = web.get("/customer/projects", query_string={"keyword":"Project 01", "categoryId":"999999", "status":"PAST"}).get_data(as_text=True)
    assert "This category no longer exists." in html
    assert project_ids(html) == {sample["projects"][1]}
    fields = next(f["fields"] for f in FilterForm(html).forms if "keyword" in f["fields"])
    assert fields["keyword"] == "Project 01" and fields["status"] == "PAST" and fields["categoryId"] == ""


# Checks combination search remains literal and parameterized.
@pytest.mark.parametrize("keyword", ["%", "_", "' OR 1=1 --"])
def test_combination_search_remains_literal_and_parameterized(web, keyword):
    sign_in(web)
    html = web.get("/customer/projects", query_string={"keyword":keyword, "categoryId":"1"}).get_data(as_text=True)
    assert not project_ids(html)


# Checks existing URLs also support combined criteria.
@pytest.mark.parametrize("path", ["/customer/projects/search", "/customer/projects/category", "/customer/projects/status", "/customer/projects/budget"])
def test_existing_urls_also_support_combined_criteria(web, sample, path):
    sign_in(web)
    html = web.get(path, query_string={"keyword":"Project 0", "categoryId":"1", "status":"PAST", "minBudget":"12000", "maxBudget":"16000"}).get_data(as_text=True)
    assert project_ids(html) == {sample["projects"][3], sample["projects"][5]}


# Checks clear all returns full catalogue.
def test_clear_all_returns_full_catalogue(web):
    sign_in(web)
    html = web.get("/customer/projects", query_string={"keyword":"Project 01", "status":"PAST"}).get_data(as_text=True)
    match = re.search(r'href="([^"]+)"[^>]*>Clear All</a>', html)
    assert match and match.group(1) == "/customer/projects"
    cleared = web.get(match.group(1)).get_data(as_text=True)
    assert "15 projects" in cleared and len(project_ids(cleared)) == 12


# Checks blank budget does not filter and zero budget is retained.
def test_blank_budget_does_not_filter_and_zero_budget_is_retained(web, sample):
    sign_in(web)
    sample["db"].execute("UPDATE interior_design_projects SET budget=0 WHERE idp_id=?", (sample["projects"][0],))
    html = web.get("/customer/projects", query_string={"minBudget":"0", "maxBudget":"0"}).get_data(as_text=True)
    assert project_ids(html) == {sample["projects"][0]}
    fields = next(f["fields"] for f in FilterForm(html).forms if "keyword" in f["fields"])
    assert fields["minBudget"] == fields["maxBudget"] == "0"


# Checks photo backfill updates only empty photos and is idempotent.
def test_photo_backfill_updates_only_empty_photos_and_is_idempotent(sample):
    from scripts.add_sample_photos import backfill_photos
    db = sample["db"]
    db.execute("UPDATE interior_design_projects SET photo_url='https://example.test/own.jpg' WHERE idp_id=?", (sample["projects"][0],))
    stamp = clock.now_text()
    db.execute("INSERT INTO favourites(customer_id,idp_id,saved_at) VALUES(?,?,?)", (sample["accounts"]["customer"],sample["projects"][0],stamp))
    before = {table:db.query(f"SELECT * FROM {table}") for table in ("user_accounts","favourites","sessions","project_views")}
    first = backfill_photos(db.path)
    assert first["updated"] == 14
    assert Path(first["backup_path"]).is_file()
    assert db.scalar("SELECT COUNT(*) FROM interior_design_projects WHERE photo_url='' OR photo_url IS NULL") == 0
    assert db.scalar("SELECT photo_url FROM interior_design_projects WHERE idp_id=?", (sample["projects"][0],)) == "https://example.test/own.jpg"
    for table,data in before.items():
        assert db.query(f"SELECT * FROM {table}") == data
    assert backfill_photos(db.path)["updated"] == 0


# Checks sample photo matches room and is served locally.
@pytest.mark.parametrize("room,filename", [("Kitchen","kitchen"),("Living Room","living-room"),("Bedroom","bedroom"),
                                           ("Bathroom","bathroom"),("Home Office","home-office"),("Dining Room","dining-room")])
def test_sample_photo_matches_room_and_is_served_locally(web, room, filename):
    from app.common.sample_photos import photo_for_category
    url = photo_for_category("Japandi "+room)
    assert url == f"/static/sample-projects/{filename}.png"
    response = web.get(url)
    assert response.status_code == 200 and response.data.startswith(b"\x89PNG\r\n\x1a\n")


# Checks regenerated data uses the eight dedicated previews and a local preview for every project.
def test_new_seeded_projects_all_have_available_preview_assets(tmp_path):
    target = tmp_path/"seeded-photos.db"
    subprocess.run([sys.executable,str(ROOT/"scripts/generate_test_data.py"),"--db",str(target)],check=True,capture_output=True)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM interior_design_projects").fetchone()[0] == 320
        assert conn.execute("SELECT COUNT(*) FROM interior_design_projects WHERE photo_url IS NULL OR TRIM(photo_url)=''").fetchone()[0] == 0
        urls = [r[0] for r in conn.execute("SELECT DISTINCT photo_url FROM interior_design_projects")]
        dedicated = dict(conn.execute("SELECT idp_id, photo_url FROM interior_design_projects WHERE photo_url LIKE '%.webp'"))
    assert dedicated == {
        9: "/static/sample-projects/idp-009-japandi-dining.webp",
        97: "/static/sample-projects/idp-097-minimalist-dining.webp",
        85: "/static/sample-projects/idp-085-scandinavian-dining.webp",
        280: "/static/sample-projects/idp-280-scandinavian-dining.webp",
        231: "/static/sample-projects/idp-231-urban-modern-dining.webp",
        130: "/static/sample-projects/idp-130-industrial-dining.webp",
        302: "/static/sample-projects/idp-302-coastal-office.webp",
        106: "/static/sample-projects/idp-106-mid-century-office.webp",
    }
    assert len(urls) == 14
    assert all((ROOT/"app"/url.lstrip('/')).is_file() for url in urls)
