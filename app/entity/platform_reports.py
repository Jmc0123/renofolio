"""US57–US59: read the four platform activity counts for one calendar period."""
from app.entity.database import DatabaseConnection


class PlatformReports:
    # Connects the report reader to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # US57-US59: counts new accounts, new projects, views and new saves in one read.
    def generate(self, start, end):
        # US57–US59: one SELECT gives all metrics the same SQLite snapshot.
        # Every account role counts. A save is counted at saved_at even after US22 removes it.
        # US30 removes a deleted project's activity. Exclude legacy soft-deleted projects as well.
        summary = self.db.query_one(
            """
            SELECT
              (SELECT COUNT(*) FROM user_accounts
               WHERE created_at >= :start AND created_at < :end) AS newAccounts,
              (SELECT COUNT(*) FROM interior_design_projects
               WHERE removed_at IS NULL AND created_at >= :start AND created_at < :end) AS newProjects,
              (SELECT COUNT(*) FROM project_views v
               JOIN interior_design_projects p ON p.idp_id = v.idp_id
               WHERE p.removed_at IS NULL AND v.viewed_at >= :start AND v.viewed_at < :end) AS projectViews,
              (SELECT COUNT(*) FROM favourites f
               JOIN interior_design_projects p ON p.idp_id = f.idp_id
               WHERE p.removed_at IS NULL AND f.saved_at >= :start AND f.saved_at < :end) AS newSaves
            """,
            {"start": start, "end": end},
        )
        return {"summary": summary}
