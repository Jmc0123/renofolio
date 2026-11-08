"""ProjectCategory (record) and ProjectCategories (collection). Table: project_categories (US52-US56)."""
import sqlite3
from dataclasses import dataclass

from app.common.result import Result
from app.common.text import plural, matches
from app.common.validators import contains_pattern
from app.entity.database import DatabaseConnection
from app.entity.interior_design_projects import PUBLIC_WHERE

# US52: the category count uses the same visibility predicate as the customer filter (US15).
CATEGORY_SELECT = (
    "SELECT c.category_id, c.name, "
    "(SELECT COUNT(*) FROM interior_design_projects p "
    "JOIN user_accounts a ON a.account_id = p.designer_id" + PUBLIC_WHERE + " AND p.category_id = c.category_id) "
    "AS project_count FROM project_categories c"
)


@dataclass
class ProjectCategory:
    categoryId: int
    name: str
    projectCount: int = 0

    # Builds a category record (with its visible project count) from a database row.
    @classmethod
    def from_row(cls, row):
        return cls(row["category_id"], row["name"], row.get("project_count", 0))


class ProjectCategories:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # US52: every category with its visible project count, by name.
    def listAll(self):
        return [ProjectCategory.from_row(r) for r in self.db.query(CATEGORY_SELECT + " ORDER BY c.name")]

    # True when the category ID exists.
    def exists(self, categoryId):
        return self.db.scalar("SELECT COUNT(*) FROM project_categories WHERE category_id = ?", (categoryId,)) > 0

    # Returns one category, or None.
    def findById(self, categoryId):
        row = self.db.query_one(CATEGORY_SELECT + " WHERE c.category_id = ?", (categoryId,))
        return ProjectCategory.from_row(row) if row else None

    # US53: saves a new category; a name already used (any case) is refused.
    def create(self, name):
        try:
            new_id = self.db.execute("INSERT INTO project_categories (name) VALUES (?)", (name.strip(),))
        except sqlite3.IntegrityError:
            return Result.fail("DUPLICATE", f"A category named '{name.strip()}' already exists.")
        return Result.succeed("CREATED", "Category created.", {"categoryId": new_id})

    # US54: renames a category; a name used by another category is refused.
    def update(self, categoryId, name):
        try:
            changed = self.db.execute("UPDATE project_categories SET name = ? WHERE category_id = ?",
                                      (name.strip(), categoryId))
        except sqlite3.IntegrityError:
            return Result.fail("DUPLICATE", f"A category named '{name.strip()}' already exists.")
        if changed == 0:
            return Result.fail("NOT_FOUND", "This category no longer exists.")
        return Result.succeed("UPDATED", "Category updated.")

    # US55: removes the category only when no project uses it.
    def remove(self, categoryId):
        with self.db.transaction() as conn:
            # US55: every referencing project blocks removal, including projects hidden from Customers.
            # The conditional DELETE checks usage and removes the category atomically.
            deleted = conn.execute(
                "DELETE FROM project_categories WHERE category_id = ? AND NOT EXISTS "
                "(SELECT 1 FROM interior_design_projects WHERE category_id = ?)", (categoryId, categoryId),
            ).rowcount
            if not deleted:
                category = conn.execute("SELECT name FROM project_categories WHERE category_id = ?",
                                        (categoryId,)).fetchone()
                if category is None:
                    return Result.fail("NOT_FOUND", "This category no longer exists.")
                in_use = conn.execute("SELECT COUNT(*) FROM interior_design_projects WHERE category_id = ?",
                                      (categoryId,)).fetchone()[0]
                return Result.fail("IN_USE", f"'{category['name']}' is used by {plural(in_use, 'project')} "
                                             "and cannot be removed.")
        return Result.succeed("REMOVED", "Category removed.")

    # US56: categories whose name contains the keyword.
    def search(self, keyword):
        rows = self.db.query(CATEGORY_SELECT + " WHERE c.name LIKE ? ESCAPE '!' ORDER BY c.name",
                             (contains_pattern(keyword),))
        items = [ProjectCategory.from_row(r) for r in rows]
        if not items:
            return Result.succeed("EMPTY", f"No categories match '{keyword.strip()}'.", [])
        return Result.succeed("FOUND", matches(len(items), "category", keyword), items)
