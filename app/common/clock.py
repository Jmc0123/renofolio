"""Single source of the current time, so tests can freeze it."""
from datetime import datetime, timedelta, date

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_frozen = None


# Returns the current time (or the frozen time during tests), without microseconds.
def now():
    return _frozen if _frozen is not None else datetime.now().replace(microsecond=0)


# Returns the current time as stored text, 'YYYY-MM-DD HH:MM:SS'.
def now_text():
    return now().strftime(TIME_FORMAT)


# Test helper: stops the clock at a fixed time, or restarts it with None.
def freeze(moment):
    """Test helper: freeze the clock at ``moment`` (datetime) or unfreeze with None."""
    global _frozen
    _frozen = moment


# Turns stored time text back into a datetime.
def parse(text):
    return datetime.strptime(text, TIME_FORMAT)


# Gives the start, end and label of the day, week or month containing a date (end excluded).
def to_date_range(period, date_text):
    """US39/US40 and US57–US59: bounds for the calendar period containing a YYYY-MM-DD date.

    A day runs from midnight to midnight, a week from Monday to the next Monday, and a month from the
    1st to the 1st of the next month. The end bound is exclusive. Returns None for a missing/invalid
    period or date.
    """
    period = (period or "").strip().upper()
    try:
        day = datetime.strptime((date_text or "").strip(), "%Y-%m-%d")
        if period == "DAY":
            start, end, label = day, day + timedelta(days=1), day.strftime("%d %b %Y")
        elif period == "WEEK":
            start = day - timedelta(days=day.weekday())
            end = start + timedelta(days=7)
            last = end - timedelta(days=1)
            first_label = start.strftime("%d" if start.month == last.month else "%d %b")
            label = f"Week of {first_label}–{last.strftime('%d %b %Y')}"
        elif period == "MONTH":
            start = day.replace(day=1)
            end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
            label = start.strftime("%B %Y")
        else:
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    return start.strftime(TIME_FORMAT), end.strftime(TIME_FORMAT), label


# Gives the start, end and label for a report's Daily, Weekly or Monthly choice.
def period_bounds(period_type, period_value):
    """Return (start_text, end_text, label) for a DAY / WEEK / MONTH period, or None if invalid.

    DAY   'YYYY-MM-DD'
    WEEK  'YYYY-Www' (HTML week input) or any 'YYYY-MM-DD' inside the week (Mon-Sun)
    MONTH 'YYYY-MM'
    The end bound is exclusive.
    """
    value = (period_value or "").strip()
    period_type = (period_type or "").strip().upper()
    try:
        if period_type == "WEEK" and "-W" in value:
            year, week = value.split("-W")
            value = date.fromisocalendar(int(year), int(week), 1).isoformat()
        elif period_type == "MONTH":
            value = datetime.strptime(value, "%Y-%m").date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None
    return to_date_range(period_type, value)
