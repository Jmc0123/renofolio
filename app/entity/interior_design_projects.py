"""InteriorDesignProject (record) and InteriorDesignProjects (collection). Table: interior_design_projects.

Customer-side methods (US13-US18) return only available projects (not removed, designer account and
profile active). Designer-side methods (US26-US31) always filter by designer_id, which the Controller
takes from the session, so a designer can only read or change their own IDPs.

US30 Delete IDP removes the project together with its project_views and favourites rows in one
transaction (the US23-US31 relational model: ON DELETE CASCADE). removed_at is kept only so rows hidden
by the earlier soft-delete version stay hidden in upgraded databases; nothing sets it any more.
"""
import sqlite3
from dataclasses import dataclass, asdict

from app.common import clock
from app.common.result import Result
from app.common.text import plural
from app.common.validators import PAGE_SIZE, contains_pattern
from app.entity.database import DatabaseConnection

PROJECT_FROM = (
    " FROM interior_design_projects p "
    "JOIN project_categories c ON c.category_id = p.category_id "
    "JOIN user_accounts a ON a.account_id = p.designer_id "
    "LEFT JOIN companies ci ON ci.designer_id = p.designer_id"
)
PROJECT_SELECT = "SELECT p.*, c.name AS category_name, a.name AS designer_name, ci.company_name" + PROJECT_FROM
PUBLIC_WHERE = (
    " WHERE p.removed_at IS NULL AND a.status = 'ACTIVE'"
    " AND EXISTS (SELECT 1 FROM user_profiles up WHERE up.profile_id = a.profile_id"
    " AND up.status = 'ACTIVE' AND up.role_code = 'INTERIOR_DESIGNER')"
)
BRIEF_ROOM_WHERE = PUBLIC_WHERE + " AND c.name LIKE ? ESCAPE '!' AND p.budget >= 0"


@dataclass
class InteriorDesignProject:
    idpId: int
    designerId: int
    title: str
    description: str
    categoryId: int
    categoryName: str
    projectStatus: str
    budget: float
    photoUrl: str
    createdAt: str
    designerName: str = ""
    companyName: str = ""

    # Builds a project record from a database row.
    @classmethod
    def from_row(cls, row):
        return cls(row["idp_id"], row["designer_id"], row["title"], row["description"] or "",
                   row["category_id"], row["category_name"], row["project_status"], row["budget"] or 0,
                   row["photo_url"] or "", row["created_at"], row["designer_name"], row["company_name"] or "")

    # Returns the project as a plain dictionary for the pages.
    def to_dict(self):
        return asdict(self)


class InteriorDesignProjects:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # ----- helpers -----
    # Returns one page of the customer project list with the total count and status message.
    def _page(self, where, params, page, empty_message):
        total = self.db.scalar(
            "SELECT COUNT(*) FROM interior_design_projects p JOIN user_accounts a ON a.account_id = p.designer_id"
            + where, params)
        pages = max(1, -(-total // PAGE_SIZE))
        if total and page > pages:
            there = f"There {'is' if pages == 1 else 'are'} {plural(pages, 'page')}."
            return Result.fail("INVALID_PAGE", f"Page {page} does not exist. {there}")
        rows = self.db.query(PROJECT_SELECT + where + " ORDER BY p.created_at DESC, p.idp_id DESC LIMIT ? OFFSET ?",
                             list(params) + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
        data = {"items": [InteriorDesignProject.from_row(r).to_dict() for r in rows],
                "total": total, "page": page, "pages": pages}
        if total == 0:
            return Result.succeed("EMPTY", empty_message, data)
        return Result.succeed("FOUND", f"{plural(total, 'project')} found.", data)

    # ----- Customer side (Member 2) -----
    # US13-US17: one page of visible projects matching every filled-in filter.
    def searchAndFilter(self, request):
        where, params, active = PUBLIC_WHERE, [], []
        if request.keyword:
            like = contains_pattern(request.keyword)
            where += " AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')"
            params += [like, like]
            active.append(f"No projects match '{request.keyword}'.")
        if request.categoryId is not None:
            if not self.db.scalar("SELECT COUNT(*) FROM project_categories WHERE category_id = ?", (request.categoryId,)):
                return Result.fail("CATEGORY_NOT_FOUND", "This category no longer exists.")
            where += " AND p.category_id = ?"
            params.append(request.categoryId)
            active.append("No projects in this category.")
        if request.status:
            where += " AND p.project_status = ?"
            params.append(request.status)
            active.append("No projects with this status.")
        if request.minBudget is not None:
            where += " AND p.budget BETWEEN ? AND ?"
            params += [request.minBudget, request.maxBudget]
            active.append("No projects in this budget range.")
        message = ("No projects match all selected filters." if len(active) > 1 else
                   active[0] if active else "No projects to show yet.")
        return self._page(where, params, request.page, message)

    # US13: one page of all visible projects.
    def browse(self, request):
        return self._page(PUBLIC_WHERE, [], int(request.page), "No projects to show yet.")

    # US14: visible projects whose title or description contains the keyword.
    def search(self, request):
        like = contains_pattern(request.keyword)
        return self._page(PUBLIC_WHERE + " AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')", [like, like],
                          int(request.page), f"No projects match '{request.keyword.strip()}'.")

    # US15: visible projects in one category.
    def filterByCategory(self, request):
        if not self.db.scalar("SELECT COUNT(*) FROM project_categories WHERE category_id = ?", (request.categoryId,)):
            return Result.fail("CATEGORY_NOT_FOUND", "This category no longer exists.")
        return self._page(PUBLIC_WHERE + " AND p.category_id = ?", [int(request.categoryId)], int(request.page),
                          "No projects in this category.")

    # US16: visible Current or Past projects.
    def filterByStatus(self, request):
        return self._page(PUBLIC_WHERE + " AND p.project_status = ?", [request.status.upper()], int(request.page),
                          "No projects with this status.")

    # US17: visible projects with a budget inside the range.
    def filterByBudget(self, request):
        return self._page(PUBLIC_WHERE + " AND p.budget BETWEEN ? AND ?",
                          [float(request.minBudget), float(request.maxBudget)], int(request.page),
                          "No projects in this budget range.")

    # Returns visible projects in the chosen room whose published budget is within the limit.
    def findForBrief(self, room, budget):
        rows = self.db.query(
            PROJECT_SELECT + BRIEF_ROOM_WHERE + " AND p.budget <= ?",
            (contains_pattern(room), budget),
        )
        return [InteriorDesignProject.from_row(row).to_dict() for row in rows]

    # Looks up the lowest published budget using the same room and visibility rules as matching.
    def lowestBudgetForRoom(self, room):
        return self.db.scalar("SELECT MIN(p.budget)" + PROJECT_FROM + BRIEF_ROOM_WHERE, (contains_pattern(room),))

    # US18: one visible project with its category and designer.
    def find(self, request):
        row = self.db.query_one(PROJECT_SELECT + PUBLIC_WHERE + " AND p.idp_id = ?", (int(request.idpId),))
        if row is None:
            return Result.fail("NOT_FOUND", "This project is no longer available.")
        return Result.succeed("FOUND", "", InteriorDesignProject.from_row(row).to_dict())

    # US32: a designer's visible projects, Current first.
    def findByDesignerPublic(self, designerId):
        rows = self.db.query(PROJECT_SELECT + PUBLIC_WHERE + " AND p.designer_id = ? "
                             "ORDER BY p.project_status, p.created_at DESC", (designerId,))
        return [InteriorDesignProject.from_row(r).to_dict() for r in rows]

    # ----- Designer side (US26-US31) -----
    OWN_WHERE = " WHERE p.removed_at IS NULL AND p.designer_id = ?"
    OWN_ORDER = " ORDER BY p.created_at DESC, p.idp_id DESC"

    # Runs a query limited to one designer's own projects.
    def _own(self, designerId, extra="", params=()):
        rows = self.db.query(PROJECT_SELECT + self.OWN_WHERE + extra + self.OWN_ORDER, (designerId, *params))
        return [InteriorDesignProject.from_row(r).to_dict() for r in rows]

    # US26: saves a new project for the designer.
    def create(self, designerId, request):
        """US26: saves the new project linked to the designer, with the creation time."""
        stamp = clock.now_text()
        new_id = self.db.execute(
            "INSERT INTO interior_design_projects (designer_id, title, description, category_id, project_status, "
            "budget, photo_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (designerId, request.title.strip(), (request.description or "").strip(), int(request.categoryId),
             request.projectStatus.upper(), float(request.budget), (request.photoUrl or "").strip(), stamp, stamp))
        return Result.succeed("CREATED", "Project created successfully.", {"idpId": new_id})

    # US27: all of the designer's projects, newest first.
    def findByDesigner(self, designerId):
        """US27 (and US32, US36-US40): all of the designer's projects, newest first."""
        return Result.succeed("FOUND", "", self._own(designerId))

    # US27: one project, only if it belongs to the designer.
    def findOwned(self, designerId, idpId):
        """US27: one project, only if it belongs to the designer."""
        items = self._own(designerId, " AND p.idp_id = ?", (idpId,))
        if not items:
            return Result.fail("NOT_OWNER", "This project is not available.")
        return Result.succeed("FOUND", "", items[0])

    # US28: the designer's Current or Past projects.
    def filterMineByStatus(self, designerId, status):
        """US28: the designer's projects with status CURRENT or PAST."""
        return Result.succeed("FOUND", "", self._own(designerId, " AND p.project_status = ?", (status.upper(),)))

    # US31: the designer's projects matching a keyword.
    def searchMine(self, designerId, keyword):
        """US31: the designer's projects whose title or description contains the keyword (case-insensitive)."""
        like = contains_pattern(keyword)
        return Result.succeed("FOUND", "", self._own(
            designerId, " AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')", (like, like)))

    # US28 + US31: the designer's projects matching the keyword and the status.
    def searchAndFilterMine(self, designerId, keyword, status):
        """US28 + US31 together: the designer's projects matching the keyword AND the status."""
        like = contains_pattern(keyword)
        return Result.succeed("FOUND", "", self._own(
            designerId, " AND p.project_status = ? AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')",
            (status.upper(), like, like)))

    # True when the project belongs to the designer.
    def isOwner(self, designerId, idpId):
        """US29, US30, US34, US35 Check Project Ownership."""
        return self.db.scalar("SELECT COUNT(*) FROM interior_design_projects WHERE idp_id = ? AND designer_id = ? "
                              "AND removed_at IS NULL", (idpId, designerId)) > 0

    # Checks whether a stored preview is still referenced by any project.
    def hasPhotoReference(self, photo_url, conn=None):
        sql = "SELECT 1 FROM interior_design_projects WHERE photo_url = ? LIMIT 1"
        if conn is not None:
            return conn.execute(sql, (photo_url,)).fetchone() is not None
        return self.db.scalar(sql, (photo_url,)) is not None

    # US29: saves the changed project and identifies the previous upload for cleanup.
    def update(self, request):
        """US29: the Controller has already checked ownership with isOwner()."""
        photo_url = (request.photoUrl or "").strip()
        with self.db.transaction() as conn:
            # Serialize the read and write so concurrent replacements each clean up the right file.
            conn.execute("BEGIN IMMEDIATE")
            before = conn.execute(
                "SELECT photo_url FROM interior_design_projects WHERE idp_id = ? AND removed_at IS NULL",
                (request.idpId,),
            ).fetchone()
            if before is None:
                return Result.fail("NOT_OWNER", "This project is no longer available.")
            changed = conn.execute(
                "UPDATE interior_design_projects SET title = ?, description = ?, category_id = ?, project_status = ?, "
                "budget = ?, photo_url = COALESCE(NULLIF(?, ''), photo_url), updated_at = ? "
                "WHERE idp_id = ? AND removed_at IS NULL",
                (request.title.strip(), (request.description or "").strip(), int(request.categoryId),
                 request.projectStatus.upper(), float(request.budget), photo_url, clock.now_text(), int(request.idpId)),
            ).rowcount
            if not changed:
                return Result.fail("NOT_OWNER", "This project is no longer available.")
            old_photo = before["photo_url"] if photo_url else ""
            unused_photo = old_photo if old_photo and not self.hasPhotoReference(old_photo, conn) else ""
        return Result.succeed("UPDATED", "Project updated.", {"unusedPhotoUrl": unused_photo})

    # US30: deletes the project with its views and favourites in one transaction.
    def delete(self, idpId):
        """US30: delete the project with its views and favourites in one transaction (all or nothing).

        The child rows are deleted explicitly as well as by ON DELETE CASCADE, so databases created
        before the cascade was added behave the same.
        """
        try:
            with self.db.transaction() as conn:
                conn.execute("BEGIN IMMEDIATE")
                before = conn.execute(
                    "SELECT photo_url FROM interior_design_projects WHERE idp_id = ? AND removed_at IS NULL",
                    (idpId,),
                ).fetchone()
                if before is None:
                    raise LookupError("project already gone")
                conn.execute("DELETE FROM project_views WHERE idp_id = ?", (idpId,))
                conn.execute("DELETE FROM favourites WHERE idp_id = ?", (idpId,))
                deleted = conn.execute("DELETE FROM interior_design_projects WHERE idp_id = ?", (idpId,)).rowcount
                if deleted == 0:
                    raise LookupError("project already gone")
                old_photo = before["photo_url"]
                unused_photo = old_photo if old_photo and not self.hasPhotoReference(old_photo, conn) else ""
        except LookupError:
            return Result.fail("NOT_OWNER", "This project is no longer available.")
        except sqlite3.DatabaseError:
            return Result.fail("DELETE_FAILED", "The project could not be deleted. Nothing was changed.")
        return Result.succeed("DELETED", "Project deleted.", {"unusedPhotoUrl": unused_photo})
