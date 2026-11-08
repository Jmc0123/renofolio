"""Small wording helpers so counts and dates read naturally on every page (8 November review)."""
from datetime import datetime

from app.common.clock import TIME_FORMAT

# Words whose plural is not just "word + s".
IRREGULAR_PLURALS = {"category": "categories"}


# Returns "1 account" or "3 accounts": a count with the right singular or plural noun.
def plural(count, word):
    noun = word if count == 1 else IRREGULAR_PLURALS.get(word, word + "s")
    return f"{count} {noun}"


# Returns "1 account matches 'tan'" or "2 accounts match 'tan'" for a search result line.
def matches(count, word, keyword):
    verb = "matches" if count == 1 else "match"
    return f"{plural(count, word)} {verb} '{keyword.strip()}'"


# Turns a stored timestamp or date into "9 Jun 2026"; anything else is returned unchanged.
def friendly_date(value):
    moment = _parse(value)
    return f"{moment.day} {moment:%b %Y}" if moment else (value or "")


# Turns a stored timestamp into "9 Jun 2026, 1:59 PM"; date-only values give just the date.
def friendly_datetime(value):
    moment = _parse(value)
    if moment is None:
        return value or ""
    if len((value or "").strip()) <= 10:
        return friendly_date(value)
    hour = moment.hour % 12 or 12
    return f"{moment.day} {moment:%b %Y}, {hour}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'}"


# Reads "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" text; returns None when it is neither.
def _parse(value):
    text = (value or "").strip() if isinstance(value, str) else ""
    for pattern in (TIME_FORMAT, "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None
