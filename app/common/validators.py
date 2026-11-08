"""Small, pure validation helpers used by Controllers' validateRequest() methods."""
import math
import re
from decimal import Decimal, ROUND_HALF_UP

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_RE = re.compile(r"^\+?\d{8,15}$")

MIN_PASSWORD_LENGTH = 8
PAGE_SIZE = 12  # A full customer project page fills three rows on the four-column grid.
MAX_BUDGET = 10_000_000  # 8 November: the highest project budget (S$) a designer can enter or a customer can filter by.
BUDGET_RANGE_MESSAGE = "Budget must be between S$0 and S$10,000,000."
PROJECT_STATUSES = ("CURRENT", "PAST")


# True when a value is missing or only spaces.
def is_blank(value):
    return value is None or str(value).strip() == ""


# True when a value looks like an email address.
def valid_email(value):
    return not is_blank(value) and bool(EMAIL_RE.match(str(value).strip()))


# True when a contact number has 8 to 15 digits (spaces, dashes and a leading + allowed).
def valid_contact(value):
    if is_blank(value):
        return False
    return bool(CONTACT_RE.match(str(value).replace(" ", "").replace("-", "")))


# Returns a whole number of 1 or more that fits the database, or None.
def to_positive_int(value):
    """Return a positive integer that fits in a SQLite INTEGER."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 2**63 - 1 else None


# Returns a number of 0 or more, or None for text, negatives and infinity.
def to_non_negative_number(value):
    """Return value as a float >= 0, or None if it is not one."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


# Rounds a validated budget to the nearest cent before it is saved or used as a filter.
def round_budget(amount):
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# Builds a LIKE pattern that finds the keyword anywhere, treating % and _ as normal text.
def contains_pattern(value):
    """SQL LIKE pattern for a literal keyword, using ! as the escape character."""
    text = value.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{text}%"
