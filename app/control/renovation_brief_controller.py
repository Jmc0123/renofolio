"""Matches a customer's renovation brief against the public catalogue."""
import re

from app.common.result import Result
from app.common.sample_photos import SAMPLE_PHOTOS
from app.common.validators import (BUDGET_RANGE_MESSAGE, MAX_BUDGET, PROJECT_STATUSES, round_budget,
                                   to_non_negative_number, to_positive_int)
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.database import CUSTOMER
from app.entity.interior_design_projects import InteriorDesignProjects


FEATURED_STYLES = {
    "Japandi": "Pale wood, warm whites, clean lines",
    "Scandinavian": "Light timber, soft textiles, bright spaces",
    "Industrial": "Exposed brick, dark metal, raw finishes",
    "Minimalist": "Muted colours, simple forms, open surfaces",
    "Contemporary": "Current shapes, mixed textures, bold accents",
    "Modern Luxe": "Rich fabrics, polished stone, warm metals",
}
MORE_STYLES = {
    "Coastal": "Sandy tones, sea blues, natural fibres",
    "Peranakan": "Patterned tiles, carved timber, vivid colours",
    "Bohemian": "Layered textiles, earthy tones, collected pieces",
    "Wabi-Sabi": "Weathered wood, handmade finishes, soft neutrals",
    "Mediterranean": "Terracotta, plaster walls, warm sunlight",
}
STYLE_CHOICES = (*FEATURED_STYLES, *MORE_STYLES)
RESULT_STEP = 6


class MatchRenovationBriefController(Controller):
    # Connects the matcher to the public catalogue and the Customer access guard.
    def __init__(self):
        self.projects = InteriorDesignProjects()
        self.accessGuard = AccessGuardController()

    # Filters by room and budget, then separates full matches from other eligible projects.
    def execute(self, request):
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        if not self.validateRequest(request):
            return self.invalidInputResult()
        projects = self.projects.findForBrief(request.room, request.budget)
        if not projects:
            lowest = self.projects.lowestBudgetForRoom(request.room)
            return Result.succeed("EMPTY", "No projects match this room and budget.", {"lowestBudget": lowest})

        style = re.compile(rf"\b{re.escape(request.style)}\b", re.IGNORECASE) if request.style else None
        preference_count = bool(style) + bool(request.status)
        best_count = 0
        for project in projects:
            # The category describes the chosen design style. Free text can mention alternatives.
            project["styleMatch"] = bool(style and style.search(project["categoryName"]))
            project["statusMatch"] = bool(request.status and project["projectStatus"] == request.status)
            project["budgetGap"] = round(request.budget - project["budget"], 2)
            if preference_count and project["styleMatch"] + project["statusMatch"] == preference_count:
                best_count += 1
        # Full matches sort first, then partial matches, then lower budgets within each score.
        projects.sort(key=lambda p: (-(p["styleMatch"] + p["statusMatch"]), p["budget"], p["idpId"]))
        limit = max(RESULT_STEP, to_positive_int(request.shown) or RESULT_STEP)
        has_more = limit < len(projects)
        return Result.succeed("MATCHED", data={
            "best": projects[:min(best_count, limit)],
            "other": projects[best_count:limit],
            "total": len(projects),
            "limit": limit,
            "nextLimit": limit + RESULT_STEP if has_more else None,
            "nextProjectId": projects[limit]["idpId"] if has_more else None,
        })

    # Validates the questionnaire choices and the inclusive budget limit.
    def validateRequest(self, request):
        if request.room not in SAMPLE_PHOTOS:
            return self.reject("Choose a room type.")
        budget = to_non_negative_number(request.budget)
        if budget is None or budget > MAX_BUDGET:
            return self.reject(BUDGET_RANGE_MESSAGE)
        if request.style and request.style not in STYLE_CHOICES:
            return self.reject("Choose one of the listed styles.")
        if request.status and request.status not in PROJECT_STATUSES:
            return self.reject("Choose a listed project status.")
        request.budget = round_budget(budget)
        return True
