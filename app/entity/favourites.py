"""Favourite (record) and Favourites (collection). Table: favourites.

A Customer has at most one *current* favourite per project (partial unique index).
Removing a favourite (US22) sets removed_at, so new-save statistics (US40) stay correct. Rows are
deleted only together with their project (US30).
"""
import sqlite3
from dataclasses import dataclass

from app.common import clock
from app.common.result import Result
from app.common.text import plural, matches
from app.common.validators import contains_pattern
from app.entity.database import DatabaseConnection
from app.entity.interior_design_projects import PUBLIC_WHERE

FAVOURITE_SELECT = (
    "SELECT f.favourite_id, f.saved_at, p.idp_id, p.title, p.description, p.project_status, p.budget, "
    "p.photo_url, c.name AS category_name, a.name AS designer_name "
    "FROM favourites f JOIN interior_design_projects p ON p.idp_id = f.idp_id "
    "JOIN project_categories c ON c.category_id = p.category_id "
    "JOIN user_accounts a ON a.account_id = p.designer_id "
    + PUBLIC_WHERE + " AND f.customer_id = ? AND f.removed_at IS NULL"
)


@dataclass
class Favourite:
    favouriteId: int
    customerId: int
    idpId: int
    savedAt: str
    removedAt: str = None


# Turns a favourites query row into the dictionary the pages use.
def _to_dict(row):
    return {"favouriteId": row["favourite_id"], "savedAt": row["saved_at"], "idpId": row["idp_id"],
            "title": row["title"], "description": row["description"] or "", "projectStatus": row["project_status"],
            "budget": row["budget"] or 0, "photoUrl": row["photo_url"] or "", "categoryName": row["category_name"],
            "designerName": row["designer_name"]}


class Favourites:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # US19: True when the Customer currently has the project saved.
    def isSaved(self, customerId, idpId):
        return self.db.scalar("SELECT COUNT(*) FROM favourites WHERE customer_id = ? AND idp_id = ? "
                              "AND removed_at IS NULL", (customerId, idpId)) > 0

    # US19: saves a visible project to the Customer's favourites (once at a time).
    def add(self, customerId, idpId):
        available = self.db.scalar(
            "SELECT COUNT(*) FROM interior_design_projects p "
            "JOIN user_accounts a ON a.account_id = p.designer_id" + PUBLIC_WHERE + " AND p.idp_id = ?", (idpId,))
        if not available:
            return Result.fail("NOT_AVAILABLE", "This project is no longer available, so it cannot be saved.")
        try:
            self.db.execute("INSERT INTO favourites (customer_id, idp_id, saved_at) VALUES (?, ?, ?)",
                            (customerId, idpId, clock.now_text()))
        except sqlite3.IntegrityError:
            return Result.fail("ALREADY_SAVED", "This project is already in your favourites.")
        return Result.succeed("SAVED", "Saved to your favourites.")

    # US20: returns the Customer's visible saved projects and mentions hidden ones.
    def findByCustomer(self, customerId):
        rows = self.db.query(FAVOURITE_SELECT + " ORDER BY f.saved_at DESC, f.favourite_id DESC", (customerId,))
        items = [_to_dict(r) for r in rows]
        hidden = self.countUnavailable(customerId)
        if not items:
            if hidden:
                return Result.succeed("EMPTY", f"{plural(hidden, 'saved project')} "
                                               f"{'is' if hidden == 1 else 'are'} currently unavailable.", [])
            return Result.succeed("EMPTY", "You have no saved projects yet.", [])
        message = plural(len(items), "saved project")
        if hidden:
            message += f". {hidden} more {'is' if hidden == 1 else 'are'} currently unavailable."
        return Result.succeed("FOUND", message, items)

    # Counts saved projects that are hidden because their designer is suspended.
    def countUnavailable(self, customerId):
        """Bug 1 (8 November): saved projects hidden because their designer is suspended are counted, so the
        customer is told they exist instead of being told they have no saved projects."""
        return self.db.scalar(
            "SELECT COUNT(*) FROM favourites f WHERE f.customer_id = ? AND f.removed_at IS NULL AND f.idp_id NOT IN "
            "(SELECT p.idp_id FROM interior_design_projects p JOIN user_accounts a ON a.account_id = p.designer_id"
            + PUBLIC_WHERE + ")", (customerId,))

    # US21: returns saved projects whose title or description contains the keyword.
    def search(self, customerId, keyword):
        like = contains_pattern(keyword)
        rows = self.db.query(FAVOURITE_SELECT + " AND (p.title LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!') "
                             "ORDER BY f.saved_at DESC, f.favourite_id DESC", (customerId, like, like))
        items = [_to_dict(r) for r in rows]
        if not items:
            return Result.succeed("EMPTY", f"No saved projects match '{keyword.strip()}'.", [])
        return Result.succeed("FOUND", matches(len(items), "saved project", keyword), items)

    # US22: marks the favourite as removed, keeping its history for statistics.
    def remove(self, customerId, idpId):
        changed = self.db.execute("UPDATE favourites SET removed_at = ? WHERE customer_id = ? AND idp_id = ? "
                                  "AND removed_at IS NULL", (clock.now_text(), customerId, idpId))
        if changed == 0:
            return Result.fail("NOT_IN_FAVOURITES", "This project is not in your favourites.")
        return Result.succeed("REMOVED", "Removed from your favourites.")

    # ----- statistics for the Interior Designer (US35-US41) -----
    # US35: customers who currently have the project saved.
    def countCurrent(self, idpId):
        """US35: customers who currently have the project in their favourites (removed ones excluded)."""
        return self.db.scalar("SELECT COUNT(*) FROM favourites WHERE idp_id = ? AND removed_at IS NULL", (idpId,))

    # US36-US38: current shortlists per project for one designer.
    def countCurrentPerProject(self, designerId):
        """US36-US38: current shortlists for each of the designer's projects, as {idpId: count}."""
        rows = self.db.query(
            "SELECT p.idp_id, COUNT(f.favourite_id) AS n FROM interior_design_projects p "
            "LEFT JOIN favourites f ON f.idp_id = p.idp_id AND f.removed_at IS NULL "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL GROUP BY p.idp_id", (designerId,))
        return Result.succeed("FOUND", "", {r["idp_id"]: r["n"] for r in rows})

    # US40: new saves per project inside a period, including later-removed ones.
    def countSavesPerProjectBetween(self, designerId, start, end):
        """US40: successful saves with start <= saved_at < end, even if removed later, as {idpId: count}."""
        rows = self.db.query(
            "SELECT f.idp_id, COUNT(*) AS n FROM favourites f "
            "JOIN interior_design_projects p ON p.idp_id = f.idp_id "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL AND f.saved_at >= ? AND f.saved_at < ? "
            "GROUP BY f.idp_id", (designerId, start, end))
        return Result.succeed("FOUND", "", {r["idp_id"]: r["n"] for r in rows})

    # US41: current shortlists across all of one designer's projects.
    def countCurrentByDesigner(self, designerId):
        """US41: all current shortlist entries across the designer's projects."""
        return self.db.scalar(
            "SELECT COUNT(*) FROM favourites f JOIN interior_design_projects p ON p.idp_id = f.idp_id "
            "WHERE p.designer_id = ? AND p.removed_at IS NULL AND f.removed_at IS NULL", (designerId,))
