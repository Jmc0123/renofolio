"""Company (record) and Companies (persistent collection). Table: companies (US23-US25, US33).

One company record per Interior Designer (companies.designer_id is UNIQUE). Company name, contact
email and contact number are required; the Controller's validateRequest() checks them before create()
and update() are called.
"""
import sqlite3
from dataclasses import dataclass, asdict

from app.common import clock
from app.common.result import Result
from app.entity.database import DatabaseConnection


@dataclass
class Company:
    companyId: int
    designerId: int
    companyName: str
    description: str
    address: str
    contactEmail: str
    contactNumber: str
    website: str
    updatedAt: str
    designerName: str = ""

    # Builds a Company record from a database row.
    @classmethod
    def from_row(cls, row):
        return cls(row["company_id"], row["designer_id"], row["company_name"], row["description"] or "",
                   row["address"] or "", row["contact_email"] or "", row["contact_number"] or "",
                   row["website"] or "", row["updated_at"], row.get("designer_name", ""))

    # Returns the company as a plain dictionary for the pages.
    def to_dict(self):
        return asdict(self)


class Companies:
    # Connects the collection to the database.
    def __init__(self):
        self.db = DatabaseConnection()

    # US23: True when the designer already has company information.
    def hasCompany(self, designerId):
        """US23 Check Existing Company Information."""
        return self.db.scalar("SELECT COUNT(*) FROM companies WHERE designer_id = ?", (designerId,)) > 0

    # US23: saves the designer's company information (one record per designer).
    def create(self, designerId, request):
        stamp = clock.now_text()
        try:
            self.db.execute(
                "INSERT INTO companies (designer_id, company_name, description, address, contact_email, "
                "contact_number, website, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (designerId, *self._values(request), stamp, stamp))
        except sqlite3.IntegrityError:  # UNIQUE designer_id: a second record is never stored
            return Result.fail("COMPANY_EXISTS", "Company information already exists. Use Edit instead.")
        return Result.succeed("CREATED", "Company information saved.", self.findByDesigner(designerId).data)

    # US24/US33: returns the designer's company information, or a 'not added yet' failure.
    def findByDesigner(self, designerId):
        """US24 and US33: the designer's company information."""
        row = self.db.query_one(
            "SELECT c.*, a.name AS designer_name FROM companies c "
            "JOIN user_accounts a ON a.account_id = c.designer_id WHERE c.designer_id = ?", (designerId,))
        if row is None:
            return Result.fail("NO_COMPANY", "No company information.")
        return Result.succeed("FOUND", "", Company.from_row(row).to_dict())

    # US25: saves the changed company information in one statement.
    def update(self, designerId, request):
        """US25: one UPDATE statement, so the change is saved completely or not at all."""
        changed = self.db.execute(
            "UPDATE companies SET company_name = ?, description = ?, address = ?, contact_email = ?, "
            "contact_number = ?, website = ?, updated_at = ? WHERE designer_id = ?",
            (*self._values(request), clock.now_text(), designerId))
        if changed == 0:
            return Result.fail("NO_COMPANY", "You have not added company information yet. "
                                             "Please create it first.")
        return Result.succeed("UPDATED", "Company information updated.", self.findByDesigner(designerId).data)

    # Returns the trimmed company fields in the order the SQL expects.
    @staticmethod
    def _values(request):
        return (request.companyName.strip(), (request.description or "").strip(), (request.address or "").strip(),
                request.contactEmail.strip(), request.contactNumber.strip(), (request.website or "").strip())
