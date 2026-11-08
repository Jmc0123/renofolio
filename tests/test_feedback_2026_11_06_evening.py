"""Checks for the second round of testing feedback on 6 November 2026 (written before the fixes).

1. Opening a project and going Back returns to the same list page with the same filters
   (Customer browse list, and the designer's My Interior Design Projects).
2. My Interior Design Projects has one filter form like Browse IDPs: Keyword and Status work on their
   own or together, with one Apply filters button, Clear all and the hint text.
3. The Customer browse list lets the Customer choose which page to go to.
"""
import re
from urllib.parse import urlparse, parse_qs

import pytest

from app import create_app
from tests.conftest import PASSWORD, make_customer, make_designer, make_category, make_project


# Builds an app with 35 projects (4 list pages) and a customer.
@pytest.fixture
def web(tmp_path):
    app = create_app(str(tmp_path / "web.db"), testing=True)
    designer, _ = make_designer()
    kitchen, bedroom = make_category("Modern Kitchen"), make_category("Calm Bedroom")
    for i in range(35):  # 35 projects across 3 customer pages at 12 per page.
        make_project(designer, kitchen if i % 2 else bedroom, f"Hall Project {i:02d}", "PAST" if i % 3 else "CURRENT",
                     description="kitchen island" if i % 5 == 0 else "calm")
    make_customer()
    return {"app": app}


# Returns a test client logged in on a role's login page.
def client_for(app, prefix, email):
    client = app.test_client()
    client.post(f"/{prefix}/login", data={"email": email, "password": PASSWORD})
    return client


# Returns the query values of a link as a dictionary.
def query(href):
    return {k: v[0] for k, v in parse_qs(urlparse(href.replace("&amp;", "&")).query).items()}


# ---------------------------------------------------------------- 1. Back returns to the same page
class TestBackKeepsPageAndFilters:
    # Back link: checks customer card link carries page and filters.
    def test_customer_card_link_carries_page_and_filters(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects?page=2&status=PAST").get_data(as_text=True)
        link = re.search(r'href="(/customer/projects/\d+\?[^"]+)"', html)
        assert link, "project links do not carry the list position"
        assert query(link.group(1)) == {"page": "2", "status": "PAST"}

    # Back link: checks customer back link returns to same page.
    def test_customer_back_link_returns_to_same_page(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects/5?page=3&keyword=calm&status=PAST").get_data(as_text=True)
        back = re.search(r'href="([^"]*)"[^>]*>\s*← Back to projects', html).group(1)
        assert urlparse(back.replace("&amp;", "&")).path == "/customer/projects"
        assert query(back) == {"page": "3", "keyword": "calm", "status": "PAST"}

    # Back link: checks unknown or unsafe values are not copied into the back link.
    def test_unknown_or_unsafe_values_are_not_copied_into_the_back_link(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects/5?page=2&next=https://evil.example&evil=1").get_data(as_text=True)
        back = re.search(r'href="([^"]*)"[^>]*>\s*← Back to projects', html).group(1)
        assert query(back) == {"page": "2"} and "evil" not in back

    # Back link: checks save without javascript returns with the same list position.
    def test_save_without_javascript_returns_with_the_same_list_position(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        response = c.post("/customer/projects/5/save?page=3&status=PAST")
        assert response.status_code == 302
        assert query(response.headers["Location"]) == {"page": "3", "status": "PAST"}

    # Back link: checks designer back link keeps keyword and status.
    @pytest.mark.parametrize("keyword", ["kitchen", "aLl"])
    def test_designer_back_link_keeps_keyword_and_status(self, web, keyword):
        d = client_for(web["app"], "designer", "dan@example.test")
        html = d.get(f"/designer/projects?q={keyword}&status=PAST").get_data(as_text=True)
        link = re.search(r'href="(/designer/projects/\d+\?[^"]+)"', html)
        expected = {"q": keyword, "status": "PAST"}
        assert link and query(link.group(1)) == expected
        detail = d.get(link.group(1).replace("&amp;", "&")).get_data(as_text=True)
        back = re.search(r'href="([^"]*)"[^>]*>\s*← Back to My Projects', detail).group(1)
        assert query(back) == expected


# ---------------------------------------------------------------- 2. one filter form on My projects
class TestMyProjectsSingleFilterForm:
    # Returns the HTML of the My Projects filter form.
    def _form(self, html):
        return re.search(r'<form class="project-filters[^"]*".*?</form>', html, re.S).group(0)

    # My Projects filter: checks one apply button clear all and hint.
    def test_one_apply_button_clear_all_and_hint(self, web):
        d = client_for(web["app"], "designer", "dan@example.test")
        form = self._form(d.get("/designer/projects").get_data(as_text=True))
        assert form.count('type="submit"') == 1 and "Apply Filters" in form
        assert "Clear All" in form and "Projects must match all selected filters." in form

    # My Projects filter: checks keyword and status alone or together.
    @pytest.mark.parametrize("url,expected", [
        ("/designer/projects?q=kitchen", 7),                  # keyword only (US31)
        ("/designer/projects?status=CURRENT", 12),            # status only (US28)
        ("/designer/projects?q=kitchen&status=CURRENT", 3),   # both together
        ("/designer/projects?q=&status=ALL", 35),             # neither: all projects, no error
    ])
    def test_keyword_and_status_alone_or_together(self, web, url, expected):
        d = client_for(web["app"], "designer", "dan@example.test")
        html = d.get(url).get_data(as_text=True)
        assert html.count('class="idp-row card"') == expected
        assert "Please enter a keyword." not in html

    # My Projects filter: checks the result messages for keyword, status and both.
    def test_messages(self, web):
        from html import unescape
        d = client_for(web["app"], "designer", "dan@example.test")
        text = lambda url: unescape(d.get(url).get_data(as_text=True))
        assert "3 current projects match 'kitchen'" in text("/designer/projects?q=kitchen&status=CURRENT")
        assert "None of your past projects match 'sofa'." in text("/designer/projects?q=sofa&status=PAST")
        assert "12 current projects" in text("/designer/projects?status=CURRENT")
        assert "7 projects match 'kitchen'" in text("/designer/projects?q=kitchen")


# ---------------------------------------------------------------- 3. choose a page
class TestChoosePage:
    # Keeps a literal keyword "all" through customer paging, jumping and opening a project.
    def test_customer_pagination_and_back_keep_literal_all_keyword(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects?keyword=aLl&status=PAST").get_data(as_text=True)
        next_page = re.search(r'rel="next" href="([^"]+)"', html).group(1)
        expected = {"page": "2", "keyword": "aLl", "status": "PAST"}
        assert query(next_page) == expected
        jump = re.search(r'<form class="page-jump".*?</form>', html, re.S).group(0)
        assert 'type="hidden" name="keyword" value="aLl"' in jump
        assert 'type="hidden" name="status" value="PAST"' in jump

        page_two = c.get(next_page.replace("&amp;", "&")).get_data(as_text=True)
        project = re.search(r'href="(/customer/projects/\d+\?[^"]+)"', page_two).group(1)
        assert query(project) == expected
        detail = c.get(project.replace("&amp;", "&")).get_data(as_text=True)
        back = re.search(r'href="([^"]*)"[^>]*>\s*← Back to projects', detail).group(1)
        assert query(back) == expected

    # Page picker: checks numbered pages and go to page.
    def test_numbered_pages_and_go_to_page(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects?status=PAST").get_data(as_text=True)  # 23 past projects across 2 pages.
        pages = {query(h).get("page") for h in re.findall(r'href="(/customer/projects\?[^"]*page=\d+[^"]*)"', html)}
        assert pages == {"2"}
        assert html.count('class="card project"') == 12
        go = re.search(r'<form class="page-jump".*?</form>', html, re.S)
        assert go, "no Go to page form"
        assert 'name="page"' in go.group(0) and 'max="2"' in go.group(0)
        assert 'name="status" value="PAST"' in go.group(0)  # filters kept when jumping

    # Page picker: checks current page marked and jump works.
    def test_current_page_marked_and_jump_works(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects?page=3").get_data(as_text=True)
        assert 'aria-current="page">3</span>' in html
        assert html.count('class="card project"') == 11

    # Page picker: checks page out of range shows message.
    def test_page_out_of_range_shows_message(self, web):
        c = client_for(web["app"], "customer", "amy@example.test")
        html = c.get("/customer/projects?page=9").get_data(as_text=True)
        assert "Page 9 does not exist. There are 3 pages." in html
