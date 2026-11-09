"""Request objects passed from Boundary to Controller (``execute(request)``).

Names follow the B-C-E class diagrams (RegistrationRequest, LoginRequest, BrowseIDPsRequest,
CreateAccountRequest, ...). They hold raw user input only; Controllers validate them.
"""
from dataclasses import dataclass
from typing import Optional


# ---------- Member 1: accounts, login, sessions (US01-US12) ----------
@dataclass
class RegistrationRequest:
    name: str = ""
    email: str = ""
    password: str = ""
    contactNumber: str = ""


@dataclass
class LoginRequest:
    email: str = ""
    password: str = ""


@dataclass
class SessionRequest:
    sessionId: Optional[str] = None
    accountId: Optional[int] = None  # From the signed cookie; only used to explain a suspension (bug 2).


@dataclass
class UpdateDetailsRequest:
    sessionId: Optional[str] = None
    name: str = ""
    contactNumber: str = ""


# ---------- Member 2: customer browsing and favourites (US13-US22) ----------
@dataclass
class ProjectFiltersRequest:
    """One query combines the optional US14-US17 criteria with AND."""
    keyword: str = ""
    categoryId: object = None
    status: str = ""
    minBudget: object = None
    maxBudget: object = None
    page: object = 1
    mode: str = "browse"  # Required field on legacy single-filter URLs only.


@dataclass
class BrowseIDPsRequest:
    page: object = 1


@dataclass
class SearchIDPsRequest:
    keyword: str = ""
    page: object = 1


@dataclass
class FilterByCategoryRequest:
    categoryId: object = None
    page: object = 1


@dataclass
class FilterByStatusRequest:
    status: str = ""
    page: object = 1


@dataclass
class FilterByBudgetRequest:
    minBudget: object = None
    maxBudget: object = None
    page: object = 1


@dataclass
class IDPIdRequest:
    idpId: object = None
    sessionId: Optional[str] = None


@dataclass
class FavouriteRequest:
    sessionId: Optional[str] = None
    idpId: object = None
    confirmed: bool = True


@dataclass
class SearchFavouritesRequest:
    sessionId: Optional[str] = None
    keyword: str = ""


@dataclass
class ConsultationRequest:
    sessionId: Optional[str] = None
    threadId: object = None
    projectId: object = None
    message: str = ""


@dataclass
class UnreadMessagesRequest:
    accountId: object = None
    role: str = ""


@dataclass
class RenovationBriefRequest:
    sessionId: Optional[str] = None
    room: str = ""
    budget: object = None
    style: str = ""
    status: str = ""
    shown: object = None


# ---------- Interior Designer: company info, portfolio, statistics (US23-US41) ----------
# Names follow the US23-US41 B-C-E class diagrams in SoftwareAss.docx (6 November version).
@dataclass
class CompanyInfoRequest:
    """US23 Create Company Information."""
    sessionId: Optional[str] = None
    companyName: str = ""
    description: str = ""
    address: str = ""
    contactEmail: str = ""
    contactNumber: str = ""
    website: str = ""


@dataclass
class UpdateCompanyInfoRequest(CompanyInfoRequest):
    """US25 Update Company Information (same fields as US23)."""


@dataclass
class ViewCompanyInfoRequest:
    """US24 View Company Information."""
    sessionId: Optional[str] = None


@dataclass
class CreateIDPRequest:
    """US26 Create IDP."""
    sessionId: Optional[str] = None
    title: str = ""
    description: str = ""
    categoryId: object = None
    projectStatus: str = ""
    budget: object = None
    photoUrl: str = ""


@dataclass
class UpdateIDPRequest:
    """US29 Update IDP."""
    sessionId: Optional[str] = None
    idpId: object = None
    title: str = ""
    description: str = ""
    categoryId: object = None
    projectStatus: str = ""
    budget: object = None
    photoUrl: str = ""


@dataclass
class ViewMyIDPsRequest:
    """US27 View My IDPs. Without idpId: the list; with idpId: that project's details."""
    sessionId: Optional[str] = None
    idpId: object = None


@dataclass
class FilterMyIDPsRequest:
    """US28 Filter My IDPs by Current or Past Status."""
    sessionId: Optional[str] = None
    status: str = ""


@dataclass
class DeleteIDPRequest:
    """US30 Delete IDP. confirmed=False models the designer pressing Cancel (A1)."""
    sessionId: Optional[str] = None
    idpId: object = None
    confirmed: bool = True


@dataclass
class SearchMyIDPsRequest:
    """US31 Search My IDPs."""
    sessionId: Optional[str] = None
    keyword: str = ""


@dataclass
class MyIDPsFiltersRequest:
    """US28 + US31 together: keyword search and Current/Past status applied at the same time."""
    sessionId: Optional[str] = None
    keyword: str = ""
    status: str = ""


@dataclass
class DesignerIdRequest:
    """US32 / US33: the Customer opens a designer's portfolio or company information."""
    designerId: object = None


@dataclass
class ProjectStatRequest:
    """US34 / US35: one of the designer's projects."""
    sessionId: Optional[str] = None
    idpId: object = None


@dataclass
class InterestSummaryRequest:
    """US36 / US37 / US38."""
    sessionId: Optional[str] = None


@dataclass
class PeriodStatRequest:
    """US39 / US40: period is DAY, WEEK or MONTH; date is any YYYY-MM-DD inside that period."""
    sessionId: Optional[str] = None
    period: str = ""
    date: str = ""


@dataclass
class PortfolioTotalsRequest:
    """US41."""
    sessionId: Optional[str] = None


# ---------- Member 5: user accounts and profiles (US42-US51) ----------
@dataclass
class CreateAccountRequest:
    displayName: str = ""
    email: str = ""
    password: str = ""
    profileId: object = None
    contactNumber: str = ""


@dataclass
class AccountIdRequest:
    accountId: object = None
    actorAccountId: Optional[int] = None  # US45: set from the validated admin session at the route.


@dataclass
class UpdateAccountRequest:
    accountId: object = None
    displayName: str = ""
    email: str = ""
    contactNumber: str = ""


@dataclass
class SearchAccountsRequest:
    keyword: str = ""
    profileId: object = None


@dataclass
class CreateProfileRequest:
    displayName: str = ""
    description: str = ""
    basedOn: str = ""  # USER_ADMIN or PLATFORM_MANAGER: the role whose pages this profile's accounts use.


@dataclass
class ProfileIdRequest:
    profileId: object = None
    actorAccountId: Optional[int] = None  # US50: set from the validated admin session at the route.


@dataclass
class UpdateProfileRequest:
    profileId: object = None
    description: str = ""


@dataclass
class SearchProfilesRequest:
    keyword: str = ""


# ---------- Member 6: categories and reports (US52-US59) ----------
@dataclass
class CategoryRequest:
    categoryId: object = None
    name: str = ""


@dataclass
class SearchCategoriesRequest:
    keyword: str = ""


@dataclass
class ReportRequest:
    periodValue: str = ""
