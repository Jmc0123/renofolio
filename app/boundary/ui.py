"""Shared Boundary helpers: the login session cookie, page rendering and the role guard.

The browser only holds a signed cookie with the random session ID; the sessions table
is the source of truth (30-minute inactivity timeout, deleted on log out).
"""
from functools import wraps

from flask import session, render_template, redirect, url_for, flash, g, make_response

from app.common.request_types import SessionRequest, UnreadMessagesRequest
from app.control.consultation_controller import CountUnreadMessagesController
from app.control.login_controllers import AccessGuardController
from app.entity.database import CUSTOMER, INTERIOR_DESIGNER, USER_ADMIN, PLATFORM_MANAGER

ROLE_AREAS = {
    CUSTOMER: {"prefix": "customer", "label": "Customer", "login": "customer_login"},
    INTERIOR_DESIGNER: {"prefix": "designer", "label": "Interior Designer", "login": "designer_login"},
    USER_ADMIN: {"prefix": "admin", "label": "User Admin", "login": "admin_login"},
    PLATFORM_MANAGER: {"prefix": "pm", "label": "Platform Manager", "login": "pm_login"},
}
# The two roles that have Messages (US62-US64), by page prefix.
MESSAGE_ROLES = {"customer": CUSTOMER, "designer": INTERIOR_DESIGNER}


# Returns the session ID stored in the signed browser cookie.
def current_session_id():
    return session.get("sid")


# Saves the new session's ID, account, role and name in the browser cookie after login.
def start_login_session(data):
    session.clear()
    session["sid"] = data["sessionId"]
    session["aid"] = data["accountId"]
    session["role"] = data["roleCode"]
    session["name"] = data["name"]


# Clears the browser cookie when the user logs out or the session ends.
def end_login_session():
    session.clear()


# Shows a page template, always passing the logged-in user for the header.
def render(template, **context):
    user = context.setdefault("user", getattr(g, "user", None))
    # 9 November: the Messages button and menu link show how many conversations have unread messages.
    context.setdefault("unread_messages", unread_message_count(user))
    return render_template(template, **context)


# Counts the logged-in Customer's or Interior Designer's conversations with unread messages (0 for anyone else).
def unread_message_count(user):
    role = MESSAGE_ROLES.get(user["area"]["prefix"]) if user else None
    if role is None:
        return 0
    result = CountUnreadMessagesController().execute(UnreadMessagesRequest(user["accountId"], role))
    return result.data["count"] if result.ok else 0


# Shows a Result's message as a green (success) or red (error) banner.
def show_result(result, success_category="success"):
    """Flash a Result's message as a banner (green for success, red for errors)."""
    if result.message:
        flash(result.message, success_category if result.ok else "error")


# Route decorator: only lets users with the given role and a live session open the page.
def requires_role(role):
    """Route decorator: run the shared access guard before the boundary method."""
    # Wraps one route function with the access check.
    def decorator(view):
        # Runs the access guard, then the page; otherwise returns to the login page with the reason.
        @wraps(view)
        def wrapper(*args, **kwargs):
            result = AccessGuardController().execute(SessionRequest(current_session_id(), session.get("aid")), role)
            if not result.ok:
                if result.code in ("SESSION_EXPIRED", "SUSPENDED"):
                    end_login_session()
                flash(result.message, "error")
                return redirect(url_for(ROLE_AREAS[role]["login"]))
            g.user = dict(result.data, area=ROLE_AREAS[role])
            response = make_response(view(*args, **kwargs))
            response.headers["Cache-Control"] = "no-store, private"
            return response
        return wrapper
    return decorator


# Sends the user to their login page when a controller reports an ended session.
def handle_expired(result, role):
    """If a controller reports an expired session, send the user to their login page."""
    if result.code in ("SESSION_EXPIRED", "SUSPENDED", "FORBIDDEN"):
        end_login_session()
        flash(result.message, "error")
        return redirect(url_for(ROLE_AREAS[role]["login"]))
    return None


CUSTOMER_LIST_KEYS = ("keyword", "categoryId", "status", "minBudget", "maxBudget", "page")
DESIGNER_LIST_KEYS = ("q", "status")


# Keeps only safe list filters and the page number, for the Back link after opening an item.
def list_position(args, keys):
    """The list page and filters to return to after opening an item ("Back" keeps your place).

    Only the named keys are copied, short values only, and blanks/defaults are dropped, so the
    Back link can only ever point to the list page with ordinary filter values.
    """
    position = {}
    for key in keys:
        value = (args.get(key) or "").strip()
        # A search keyword can be "all" even when a selection uses "ALL" as its default.
        is_default = (key in ("categoryId", "status") and value.upper() == "ALL") or (key == "page" and value == "1")
        if not value or len(value) > 100 or is_default:
            continue
        position[key] = value
    return position


STAFF_PAGE_SIZE = 20


# Cuts a staff list into pages of 20 and returns the rows, the page links data and any page error.
def paginate(items, page_text, size=STAFF_PAGE_SIZE):
    """Staff lists (8 November): show 20 rows per page with page numbers, like the customer project list.

    Returns (rows for this page, pager data for the "pager" macro, error message or None).
    """
    total = len(items)
    pages = max(1, -(-total // size))
    text = str(page_text or "1").strip()
    if not text.isdigit() or int(text) < 1:
        return items[:size], {"page": 1, "pages": pages, "total": total}, "Invalid page number."
    page = int(text)
    if page > pages:
        noun = "page" if pages == 1 else "pages"
        return (items[:size], {"page": 1, "pages": pages, "total": total},
                f"Page {page} does not exist. There {'is' if pages == 1 else 'are'} {pages} {noun}.")
    start = (page - 1) * size
    return items[start:start + size], {"page": page, "pages": pages, "total": total}, None
