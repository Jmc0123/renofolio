"""ProjectView (record) and ProjectViews (collection). Table: project_views.

A view record stores only the project, the customer ID and the time (privacy NFR, US18).
"""
from dataclasses import dataclass

from app.common import clock
from app.common.result import Result
from app.entity.database import DatabaseConnection


@dataclass
class ProjectView:
    viewId: int
    idpId: int
    customerId: int
    viewedAt: str


class ProjectViews:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # US18: records one view of a project by a Customer.
    def recordView(self, idpId, customerId):
        return self.db.execute("INSERT INTO project_views (idp_id, customer_id, viewed_at) VALUES (?, ?, ?)",
                               (idpId, customerId, clock.now_text())) > 0

    # US34: total recorded views of one project.
    def countByProject(self, idpId):
        """US34: total recorded views of one project (every opening in US18 is one row)."""
        return self.db.scalar("SELECT COUNT(*) FROM project_views WHERE idp_id = ?", (idpId,))

    # ----- US34-US41 statistics (counts only the designer's existing projects) -----
    # US36-US38: views per project for one designer.
    def countPerProject(self, designerId):
        """US36-US38: total recorded views for each of the designer's projects, as {idpId: count}."""
        rows = self.db.query(
            "SELECT p.idp_id, COUNT(v.view_id) AS n FROM interior_design_projects p "
            "LEFT JOIN project_views v ON v.idp_id = p.idp_id "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL GROUP BY p.idp_id", (designerId,))
        return Result.succeed("FOUND", "", {r["idp_id"]: r["n"] for r in rows})

    # US39: views per project inside a period for one designer.
    def countPerProjectBetween(self, designerId, start, end):
        """US39: views with start <= viewed_at < end for each of the designer's projects, as {idpId: count}."""
        rows = self.db.query(
            "SELECT v.idp_id, COUNT(*) AS n FROM project_views v "
            "JOIN interior_design_projects p ON p.idp_id = v.idp_id "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL AND v.viewed_at >= ? AND v.viewed_at < ? "
            "GROUP BY v.idp_id", (designerId, start, end))
        return Result.succeed("FOUND", "", {r["idp_id"]: r["n"] for r in rows})

    # US41: total views across one designer's projects.
    def countByDesigner(self, designerId):
        """US41: all recorded views across the designer's projects."""
        return self.db.scalar(
            "SELECT COUNT(*) FROM project_views v JOIN interior_design_projects p ON p.idp_id = v.idp_id "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL", (designerId,))
