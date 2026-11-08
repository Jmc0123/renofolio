"""Acceptance tests for the consultation inbox and the renovation questionnaire."""
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from app import create_app
from app.entity.database import DatabaseConnection
from tests.conftest import PASSWORD, make_category, make_customer, make_designer, make_project


# Builds a small catalogue with matches, near matches and excluded projects.
@pytest.fixture
def site(tmp_path):
    app = create_app(str(tmp_path / "features.db"), testing=True)
    designer, designer_id = make_designer()
    make_customer()
    japandi = make_category("Japandi Kitchen")
    industrial = make_category("Industrial Kitchen")
    bedroom = make_category("Japandi Bedroom")
    project = make_project(designer, japandi, "Cove Kitchen", "PAST", "35000")
    current = make_project(designer, japandi, "Maple Kitchen", "CURRENT", "32000")
    cheaper = make_project(designer, industrial, "Foundry Kitchen", "CURRENT", "27000", "Brick and steel")
    make_project(designer, japandi, "Luxury Kitchen", "PAST", "56000")
    make_project(designer, bedroom, "Quiet Bedroom", "PAST", "28000")
    return app, DatabaseConnection(), designer_id, project, current, cheaper


# Signs in through the same page a demo user uses.
def sign_in(app, role, email):
    client = app.test_client()
    result = client.post(f"/{role}/login", data={"email": email, "password": PASSWORD})
    assert result.status_code == 302
    return client


# Starts the consultation from a published project and returns the thread ID and URL.
def start(customer, project, message="Can we discuss a kitchen renovation?"):
    response = customer.post("/customer/messages", data={"projectId": project, "message": message})
    assert response.status_code == 303
    url = response.headers["Location"]
    thread = parse_qs(urlsplit(url).query)["threadId"][0]
    return thread, url


# Both participants can read the entire conversation after replies and reloads.
def test_consultation_from_project_to_inbox_and_history(site):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    designer = sign_in(app, "designer", "dan@example.test")
    detail = customer.get(f"/customer/projects/{project}")
    assert b"Contact Designer" in detail.data
    assert f"/customer/messages?projectId={project}".encode() in detail.data
    draft = customer.get("/customer/messages", query_string={"projectId": project},
                         headers={"X-Consultation-Fragment": "1"})
    assert draft.status_code == 200 and draft.headers["X-Consultation-Fragment"] == "1"
    assert b"Cove Kitchen" in draft.data and b"Send Message" in draft.data

    thread, customer_url = start(customer, project, "My budget is S$40,000 and I prefer <oak>.")
    inbox = designer.get("/designer/messages")
    assert b"Cove Kitchen" in inbox.data and b"New" in inbox.data
    reply = designer.post("/designer/messages", data={"threadId": thread, "message": "Yes, oak works well."})
    assert reply.status_code == 303
    history = customer.get(customer_url)
    assert b"Replied" in history.data and b"Yes, oak works well." in history.data
    assert b"&lt;oak&gt;" in history.data
    assert customer.post("/customer/messages", data={"threadId": thread, "message": "Great, when can we start?"}).status_code == 303
    designer_history = designer.get(f"/designer/messages?threadId={thread}")
    assert b"Great, when can we start?" in designer_history.data
    assert db.scalar("SELECT COUNT(*) FROM consultation_messages WHERE consultation_id = ?", (thread,)) == 3


# Retrying a first message opens its existing thread instead of posting a duplicate.
def test_retry_uses_existing_thread(site):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    first = start(customer, project)
    assert start(customer, project) == first
    assert db.scalar("SELECT COUNT(*) FROM consultations") == 1
    assert db.scalar("SELECT COUNT(*) FROM consultation_messages") == 1


# Other customers and designers cannot read, send to or close a thread they do not own.
def test_consultation_is_private_to_its_two_participants(site):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    thread, _ = start(customer, project, "Private renovation details")
    make_customer("other@example.test", "Other Customer")
    make_designer("other-designer@example.test", "Other Designer")
    for role, email in (("customer", "other@example.test"), ("designer", "other-designer@example.test")):
        stranger = sign_in(app, role, email)
        url = f"/{role}/messages"
        response = stranger.get(url, query_string={"threadId": thread})
        assert b"Private renovation details" not in response.data
        assert b"This conversation is unavailable." in response.data
        assert b"This conversation is unavailable." in stranger.post(
            url, data={"threadId": thread, "message": "Invalid sender"}).data
    assert db.scalar("SELECT COUNT(*) FROM consultation_messages") == 1


# Closed threads remain in history and reject later messages.
def test_designer_can_close_a_thread(site):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    designer = sign_in(app, "designer", "dan@example.test")
    thread, url = start(customer, project)
    assert b"Only the designer can close this conversation." in customer.post(
        "/customer/messages", data={"threadId": thread, "action": "close"}).data
    assert designer.post("/designer/messages", data={"threadId": thread, "action": "close"}).status_code == 303
    history = customer.get(url)
    assert b"Closed" in history.data and b"Can we discuss a kitchen renovation?" in history.data
    assert b"This conversation is closed." in customer.post(
        "/customer/messages", data={"threadId": thread, "message": "Try again"}).data
    assert db.scalar("SELECT COUNT(*) FROM consultation_messages") == 1


# Deleted projects leave a readable conversation and reject new messages.
def test_consultation_history_survives_project_deletion(site):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    thread, url = start(customer, project)
    db.execute("DELETE FROM interior_design_projects WHERE idp_id = ?", (project,))
    history = customer.get(url)
    assert b"Cove Kitchen" in history.data and b"Can we discuss a kitchen renovation?" in history.data
    assert b"Messages are unavailable for this conversation." in customer.post(
        "/customer/messages", data={"threadId": thread, "message": "Follow up"}).data


# Invalid messages leave the database untouched.
@pytest.mark.parametrize("message", ["   ", "a" * 2001])
def test_consultation_rejects_invalid_message_text(site, message):
    app, db, _, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    response = customer.post("/customer/messages", data={"projectId": project, "message": message})
    assert b"Enter a message of 1 to 2,000 characters." in response.data
    assert db.scalar("SELECT COUNT(*) FROM consultations") == 0


# All chosen preferences are required for the best group, with near matches ranked below it.
def test_matcher_filters_and_explains_preference_order(site):
    app, _, _, _, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    response = customer.get("/customer/find-my-style", query_string={
        "room": "Kitchen", "budget": "40000", "style": "Japandi", "status": "PAST",
    })
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    best, other = html.split("Other Options Within Budget", 1)
    assert "Best Matches" in best and "Cove Kitchen" in best
    assert "Maple Kitchen" not in best and "Foundry Kitchen" not in best
    assert "Maple Kitchen" in other and "Foundry Kitchen" in other
    assert html.index("Cove Kitchen") < html.index("Maple Kitchen") < html.index("Foundry Kitchen")
    assert "Luxury Kitchen" not in html and "Quiet Bedroom" not in html
    assert "Matches Your Style" in html and "Matches Your Project Status" in html
    assert "S$5,000 below your budget" in best
    assert "Show More" not in html


# Only a style in the project category counts, even when the description mentions another style.
def test_matcher_does_not_treat_style_mentions_as_category_matches(site):
    app, _, _, _, _, _ = site
    designer, _ = make_designer("lee@example.test")
    industrial = make_category("Textured Industrial Dining Room")
    project = make_project(designer, industrial, "Concrete Dining Room", "PAST", "28450.49",
                           "The client ruled out Japandi.")
    customer = sign_in(app, "customer", "amy@example.test")
    html = customer.get("/customer/find-my-style?room=Dining+Room&budget=60000&style=Japandi&status=PAST").get_data(as_text=True)
    best, other = html.split("Other Options Within Budget", 1)
    assert f'id="match-{project}"' not in best and f'id="match-{project}"' in other
    assert "Matches Your Style · Japandi" not in html
    industrial_matches = customer.get("/customer/find-my-style?room=Dining+Room&budget=60000&style=Industrial").data
    assert b"Matches Your Style" in industrial_matches


# A single preference is enough for the best group and blank preferences are optional.
def test_matcher_groups_only_the_preferences_the_customer_chose(site):
    app, _, _, _, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    url = "/customer/find-my-style?room=Kitchen&budget=35000"
    html = customer.get(url + "&style=Japandi").get_data(as_text=True)
    best, other = html.split("Other Options Within Budget", 1)
    assert "Cove Kitchen" in best and "Maple Kitchen" in best
    assert "Foundry Kitchen" in other and "At your budget limit" in best
    html = customer.get(url + "&style=Minimalist").get_data(as_text=True)
    assert "No projects match all your preferences" in html and "Foundry Kitchen" in html
    html = customer.get(url).get_data(as_text=True)
    assert "Projects Within Budget" in html and "Best Matches" not in html


# Expanding and opening a result preserves every answer and the number of projects shown.
def test_matcher_show_more_and_project_back_link(site):
    app, _, _, _, _, _ = site
    designer, _ = make_designer("lee@example.test")
    industrial = make_category("Steel Industrial Kitchen")
    for number in range(5):
        make_project(designer, industrial, f"Steel Kitchen {number + 1}", "CURRENT", "38000")
    customer = sign_in(app, "customer", "amy@example.test")
    answers = {"room": "Kitchen", "budget": "40000", "style": "Japandi", "status": "PAST"}
    html = customer.get("/customer/find-my-style", query_string=answers).get_data(as_text=True)
    assert html.count('class="card project brief-match"') == 6
    more = unescape(re.search(r'href="([^"]+)">Show More</a>', html)[1])
    more_args = parse_qs(urlsplit(more).query)
    assert more_args == {**{key: [value] for key, value in answers.items()}, "shown": ["12"]}
    expanded = customer.get(more).get_data(as_text=True)
    assert expanded.count('class="card project brief-match"') == 8
    assert "Steel Kitchen 5" in expanded and "Show More" not in expanded
    project_url = unescape(re.findall(r'href="([^"]+)">View Project</a>', expanded)[-1])
    detail = customer.get(project_url).get_data(as_text=True)
    back = unescape(re.search(r'href="([^"]+)">← Back to My Matches</a>', detail)[1])
    assert urlsplit(back).path == "/customer/find-my-style" and urlsplit(back).fragment == "matches"
    assert parse_qs(urlsplit(back).query) == more_args
    assert customer.get(back).get_data(as_text=True).count('class="card project brief-match"') == 8

    save_url = unescape(re.search(r'action="([^"]+)" data-save-favourite', detail)[1])
    saved = customer.post(save_url, follow_redirects=True).get_data(as_text=True)
    assert "Back to My Matches" in saved and "In Your Favourites" in saved


# Expanded styles use the same matching rules and reopen when selected.
def test_matcher_more_styles_are_described_and_match_projects(site):
    app, _, _, _, _, _ = site
    designer, _ = make_designer("lee@example.test")
    coastal = make_category("Coastal Kitchen")
    make_project(designer, coastal, "Sea Breeze Kitchen", "PAST", "31000")
    customer = sign_in(app, "customer", "amy@example.test")
    html = customer.get("/customer/find-my-style?room=Kitchen&budget=31000&style=Coastal").get_data(as_text=True)
    assert "More Styles" in html and "Peranakan" in html and "Pale wood, warm whites, clean lines" in html
    assert '<details class="brief-more-styles" open>' in html and 'value="Coastal" checked' in html
    best, _ = html.split("Other Options Within Budget", 1)
    assert "Sea Breeze Kitchen" in best and "Matches Your Style · Coastal" in best


# Empty matches and invalid budgets tell the customer how to revise the brief.
def test_matcher_empty_and_invalid_inputs(site):
    app, _, _, _, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    html = customer.get("/customer/find-my-style?room=Kitchen&budget=1").get_data(as_text=True)
    assert "No projects match this room and budget." in html
    assert "lowest published budget" in html and "S$27,000" in html
    assert 'href="#brief-budget">Edit Budget</a>' in html and 'value="1" placeholder=' in html
    assert b"Budget must be between S$0 and S$10,000,000." in customer.get(
        "/customer/find-my-style?room=Kitchen&budget=inf").data
    assert b"Choose a room type." in customer.get("/customer/find-my-style?room=Unknown&budget=50000").data


# Suspended designers' projects stay out of the matcher and cannot start a conversation.
def test_suspended_designer_is_hidden_from_matcher_and_consultation(site):
    app, db, designer, project, _, _ = site
    customer = sign_in(app, "customer", "amy@example.test")
    db.execute("UPDATE user_accounts SET status = 'SUSPENDED' WHERE account_id = ?", (designer,))
    matches = customer.get("/customer/find-my-style?room=Kitchen&budget=40000")
    assert b"Cove Kitchen" not in matches.data and b"No projects match this room and budget." in matches.data
    assert b"lowest published budget" not in matches.data
    response = customer.post("/customer/messages", data={"projectId": project, "message": "Hello"})
    assert b"This project is no longer available." in response.data
    assert db.scalar("SELECT COUNT(*) FROM consultations") == 0


# The new pages use the existing role login guards.
def test_feature_routes_require_a_role_login(site):
    app, _, _, _, _, _ = site
    visitor = app.test_client()
    for path in ("/customer/messages", "/customer/find-my-style"):
        assert visitor.get(path).headers["Location"] == "/customer/login"
    assert visitor.get("/designer/messages").headers["Location"] == "/designer/login"
