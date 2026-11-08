"""US34-US41 - the Interior Designer tracks customer interest in their projects.

Names and steps follow the US34-US41 B-C-E and sequence diagrams (SoftwareAss.docx, 6 November).
All counts are limited to the logged-in designer's own existing projects. A view is one opening of a
project's details (US18); a current shortlist is a favourite that has not been removed (US19, US22);
a new save is any successful save in the period, even if removed later (US40).
"""
from app.common import clock
from app.common.result import Result
from app.common.validators import is_blank, to_positive_int
from app.control.designer_controllers import _DesignerController
from app.entity.favourites import Favourites
from app.entity.interior_design_projects import InteriorDesignProjects
from app.entity.project_views import ProjectViews


class _StatisticsController(_DesignerController):
    # Sets up the controller with projects, project views and favourites.
    def __init__(self):
        super().__init__()
        self.projects = InteriorDesignProjects()
        self.views = ProjectViews()
        self.favourites = Favourites()

    # Checks a request was given.
    def validateRequest(self, request):
        return True if request is not None else self.reject("Invalid request.")


# ================================================================== US34, US35 Project Statistics
class _ProjectStatController(_StatisticsController):
    # US34/US35: returns one count for one of the designer's own projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        if not self.projects.isOwner(designer_id, request.idpId):
            return self.notOwnerResult()
        return self.countResult(self.count(request.idpId))

    # Checks a project was chosen.
    def validateRequest(self, request):
        idp_id = to_positive_int(request.idpId)
        if idp_id is None:
            return self.reject("Please choose one of your projects.")
        request.idpId = idp_id
        return True

    # The failure when the project is not one of the designer's own.
    def notOwnerResult(self):
        return Result.fail("NOT_OWNER", "This project is not available.")


class ViewProjectViewCountController(_ProjectStatController):
    """US34 View Project View Count. A4: no views yet shows 0."""

    # US34: counts every recorded view of the project.
    def count(self, idpId):
        return self.views.countByProject(idpId)

    # Packs the view count into a Result.
    def countResult(self, count):
        return Result.succeed("FOUND", f"Total views: {count}", {"viewCount": count})


class ViewShortlistCountController(_ProjectStatController):
    """US35 View Current Shortlist Count. A4: not shortlisted yet shows 0."""

    # US35: counts customers who currently have the project saved.
    def count(self, idpId):
        return self.favourites.countCurrent(idpId)

    # Packs the shortlist count into a Result.
    def countResult(self, count):
        return Result.succeed("FOUND", f"Shortlisted now: {count}", {"shortlistCount": count})


# ================================================================== US36-US38 Project Interest Summary
class ViewInterestSummaryController(_StatisticsController):
    """US36 View Project Interest Summary: one row per project with views and current shortlists."""
    message = ""

    # US36: returns views and current shortlists for each of the designer's projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        projects = self.projects.findByDesigner(designer_id)
        if not projects.data:
            return Result.succeed("EMPTY", "You have no projects yet.", [])
        summary = self.buildSummary(projects, self.views.countPerProject(designer_id),
                                    self.favourites.countCurrentPerProject(designer_id))
        return self.arrange(summary)

    # Joins the view and shortlist counts into one row per project.
    def buildSummary(self, projects, viewCounts, shortlistCounts):
        """Build Interest Summary: combine the counts into one row per project (projects with none show 0)."""
        rows = [dict(p, viewCount=viewCounts.data.get(p["idpId"], 0),
                     shortlistCount=shortlistCounts.data.get(p["idpId"], 0)) for p in projects.data]
        return Result.succeed("FOUND", "", rows)

    # Adds the message (project count or sort order) to the summary.
    def arrange(self, summary):
        summary.message = self.message or f"{len(summary.data)} projects"
        return summary


class SortByViewCountController(ViewInterestSummaryController):
    """US37 Sort Projects by View Count: highest first; equal counts listed by title."""
    message = "Sorted by views, highest first"

    # US37: sorts the summary by views before adding the message.
    def arrange(self, summary):
        return super().arrange(self.sortByViewCount(summary))

    # Sorts rows by views, highest first; ties by title.
    def sortByViewCount(self, summary):
        summary.data.sort(key=lambda r: (-r["viewCount"], r["title"].casefold(), r["idpId"]))
        return summary


class SortByShortlistCountController(ViewInterestSummaryController):
    """US38 Sort Projects by Current Shortlist Count: highest first; equal counts listed by title."""
    message = "Sorted by current shortlists, highest first"

    # US38: sorts the summary by shortlists before adding the message.
    def arrange(self, summary):
        return super().arrange(self.sortByShortlistCount(summary))

    # Sorts rows by current shortlists, highest first; ties by title.
    def sortByShortlistCount(self, summary):
        summary.data.sort(key=lambda r: (-r["shortlistCount"], r["title"].casefold(), r["idpId"]))
        return summary


# ================================================================== US39, US40 Statistics for a Period
class _PeriodStatController(_StatisticsController):
    metric = ""

    # US39/US40: returns a count per project for the chosen day, week or month.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        start, end, label = self.toDateRange(request.period, request.date)
        projects = self.projects.findByDesigner(designer_id)
        if not projects.data:
            return Result.succeed("EMPTY", "You have no projects yet.",
                                  {"label": label, "rows": [], "total": 0, "metric": self.metric})
        return self.buildPeriodReport(projects, self.count(designer_id, start, end), label)

    # Checks a period and date were chosen and that the date is valid.
    def validateRequest(self, request):
        if (request.period or "").strip().upper() not in ("DAY", "WEEK", "MONTH") or is_blank(request.date):
            return self.reject("Please choose a period and a date.")
        if clock.to_date_range(request.period, request.date) is None:
            # Bug 8 (8 November): both were chosen, but the date does not exist or is out of range.
            return self.reject("Please choose a valid date.")
        request.period = request.period.strip().upper()
        return True

    # Turns the period and date into a start and end time.
    def toDateRange(self, period, date):
        """Convert Selected Period to Date Range: day = midnight to midnight, week = Monday to Monday,
        month = the 1st to the 1st of the next month (end exclusive)."""
        return clock.to_date_range(period, date)

    # Builds one row per project with its count, highest first, plus the total.
    def buildPeriodReport(self, projects, counts, label):
        rows = [dict(p, count=counts.data.get(p["idpId"], 0)) for p in projects.data]
        rows.sort(key=lambda r: (-r["count"], r["title"].casefold(), r["idpId"]))
        return Result.succeed("FOUND", label, {"label": label, "rows": rows, "metric": self.metric,
                                               "total": sum(r["count"] for r in rows)})


class ViewPeriodViewsController(_PeriodStatController):
    """US39 View Project Views for a Selected Period."""
    metric = "views"

    # US39: counts views per project inside the period.
    def count(self, designer_id, start, end):
        return self.views.countPerProjectBetween(designer_id, start, end)


class ViewPeriodSavesController(_PeriodStatController):
    """US40 View New Shortlists for a Selected Period."""
    metric = "saves"

    # US40: counts new saves per project inside the period (later removals still count).
    def count(self, designer_id, start, end):
        return self.favourites.countSavesPerProjectBetween(designer_id, start, end)


# ================================================================== US41 Portfolio Totals
class ViewPortfolioTotalsController(_StatisticsController):
    """US41 View Portfolio Totals: equal to the sums of the US36 per-project numbers."""

    # US41: returns total views and current shortlists across all the designer's projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        designer_id, error = self.designerFromSession(request)
        if error:
            return error
        return self.totalsResult(self.views.countByDesigner(designer_id),
                                 self.favourites.countCurrentByDesigner(designer_id))

    # Packs the two totals into a Result.
    def totalsResult(self, totalViews, totalShortlists):
        return Result.succeed("FOUND", "", {"totalViews": totalViews or 0, "totalShortlists": totalShortlists or 0})
