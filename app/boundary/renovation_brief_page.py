"""The Customer's Find My Style questionnaire."""
from app.boundary.ui import current_session_id, handle_expired, render
from app.common.request_types import RenovationBriefRequest
from app.common.sample_photos import SAMPLE_PHOTOS
from app.common.validators import MAX_BUDGET
from app.control.renovation_brief_controller import FEATURED_STYLES, MORE_STYLES, MatchRenovationBriefController
from app.entity.database import CUSTOMER

BRIEF_ANSWER_KEYS = ("room", "budget", "style", "status")


class RenovationBriefPage:
    # Shows the questionnaire and submits the answers to the matcher when requested.
    def show(self, answers, submitted, shown=None):
        result = None
        if submitted:
            request = RenovationBriefRequest(current_session_id(), shown=shown, **answers)
            result = MatchRenovationBriefController().execute(request)
            expired = handle_expired(result, CUSTOMER)
            if expired:
                return expired
        return render("customer/renovation_brief.html", rooms=SAMPLE_PHOTOS, styles=FEATURED_STYLES,
                      more_styles=MORE_STYLES, answers=answers, result=result, max_budget=MAX_BUDGET)
