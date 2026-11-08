"""US13-US22: browse, search, filter, view details, favourites."""
import pytest

from app.common.request_types import (BrowseIDPsRequest, SearchIDPsRequest, FilterByCategoryRequest,
                                      FilterByStatusRequest, FilterByBudgetRequest, IDPIdRequest, FavouriteRequest,
                                      SessionRequest, SearchFavouritesRequest, DeleteIDPRequest)
from app.control.browse_controllers import (BrowseIDPsController, SearchIDPsController, FilterIDPsByCategoryController,
                                            FilterIDPsByStatusController, FilterIDPsByBudgetController,
                                            ViewIDPDetailsController)
from app.control.designer_controllers import DeleteIDPController
from app.control.favourite_controllers import (SaveFavouriteController, ViewFavouritesController,
                                               SearchFavouritesController, RemoveFavouriteController)
from app.entity.project_views import ProjectViews
from tests.conftest import make_customer, make_designer, make_category, make_project


# Builds a designer with kitchen and bedroom projects, both Current and Past.
@pytest.fixture
def catalogue():
    designer_session, designer_id = make_designer()
    kitchen, bedroom = make_category("Modern Kitchen"), make_category("Japandi Bedroom")
    ids = {
        "kitchen": make_project(designer_session, kitchen, "Bright Kitchen", "CURRENT", "20000"),
        "bedroom": make_project(designer_session, bedroom, "Calm Bedroom", "PAST", "45000", "Warm timber tones"),
        "loft": make_project(designer_session, kitchen, "Loft Kitchen", "PAST", "90000", "Industrial loft"),
    }
    return {"designer": designer_session, "kitchen": kitchen, "bedroom": bedroom, "ids": ids}


# ---------------------------------------------------------------- US13 browse
class TestBrowse:
    # US13: checks the normal flow works.
    def test_normal_flow(self, catalogue):
        result = BrowseIDPsController().execute(BrowseIDPsRequest(1))
        assert result.ok and result.data["total"] == 3

    # US13: checks a full page of twelve and the remaining projects on the last page.
    def test_paging_twelve_per_page(self, catalogue):
        for i in range(12):
            make_project(catalogue["designer"], catalogue["kitchen"], f"Extra {i}")
        page1 = BrowseIDPsController().execute(BrowseIDPsRequest(1))
        page2 = BrowseIDPsController().execute(BrowseIDPsRequest(2))
        assert len(page1.data["items"]) == 12
        assert page2.data["total"] == 15 and len(page2.data["items"]) == 3 and page2.data["pages"] == 2

    # US13: checks invalid page number.
    @pytest.mark.parametrize("page", ["0", "-1", "abc", "1.5"])
    def test_invalid_page_number(self, page):
        assert BrowseIDPsController().execute(BrowseIDPsRequest(page)).code == "INVALID_INPUT"

    # US13: checks page beyond last.
    def test_page_beyond_last(self, catalogue):
        assert BrowseIDPsController().execute(BrowseIDPsRequest(5)).code == "INVALID_PAGE"

    # US13: checks no projects yet.
    def test_no_projects_yet(self):
        result = BrowseIDPsController().execute(BrowseIDPsRequest(1))
        assert result.code == "EMPTY" and result.message == "No projects to show yet."

    # US13: checks deleted projects are hidden.
    def test_deleted_projects_are_hidden(self, catalogue):
        DeleteIDPController().execute(DeleteIDPRequest(catalogue["designer"], catalogue["ids"]["loft"]))
        assert BrowseIDPsController().execute(BrowseIDPsRequest(1)).data["total"] == 2


# ---------------------------------------------------------------- US14 search
class TestSearch:
    # US14: checks matches title or description ignoring case.
    def test_matches_title_or_description_ignoring_case(self, catalogue):
        assert SearchIDPsController().execute(SearchIDPsRequest("KITCHEN")).data["total"] == 2
        assert SearchIDPsController().execute(SearchIDPsRequest("timber")).data["total"] == 1

    # US14: checks a blank keyword is rejected.
    def test_empty_keyword(self):
        result = SearchIDPsController().execute(SearchIDPsRequest("   "))
        assert result.code == "INVALID_INPUT" and result.message == "Please enter a keyword."

    # US14: checks no matches gives the empty message.
    def test_no_matches(self, catalogue):
        result = SearchIDPsController().execute(SearchIDPsRequest("castle"))
        assert result.code == "EMPTY" and "castle" in result.message


# ---------------------------------------------------------------- US15-US17 filters
class TestFilters:
    # Checks projects are filtered by category.
    def test_by_category(self, catalogue):
        assert FilterIDPsByCategoryController().execute(FilterByCategoryRequest(catalogue["kitchen"])).data["total"] == 2

    # Checks category no longer exists.
    def test_category_no_longer_exists(self, catalogue):
        assert FilterIDPsByCategoryController().execute(FilterByCategoryRequest(999)).code == "CATEGORY_NOT_FOUND"

    # Checks no projects in category.
    def test_no_projects_in_category(self, catalogue):
        empty = make_category("Coastal Bathroom")
        result = FilterIDPsByCategoryController().execute(FilterByCategoryRequest(empty))
        assert result.code == "EMPTY" and result.message == "No projects in this category."

    # Checks projects are filtered by status.
    def test_by_status(self, catalogue):
        assert FilterIDPsByStatusController().execute(FilterByStatusRequest("past")).data["total"] == 2
        assert FilterIDPsByStatusController().execute(FilterByStatusRequest("CURRENT")).data["total"] == 1

    # Checks invalid status.
    def test_invalid_status(self):
        assert FilterIDPsByStatusController().execute(FilterByStatusRequest("ARCHIVED")).code == "INVALID_INPUT"

    # Checks by budget inclusive bounds.
    def test_by_budget_inclusive_bounds(self, catalogue):
        result = FilterIDPsByBudgetController().execute(FilterByBudgetRequest("20000", "45000"))
        assert result.data["total"] == 2

    # Checks budget min higher than max.
    def test_budget_min_higher_than_max(self):
        result = FilterIDPsByBudgetController().execute(FilterByBudgetRequest("5000", "1000"))
        assert result.message == "Minimum budget cannot be higher than maximum."

    # Checks budget empty or non numeric.
    @pytest.mark.parametrize("low,high", [("", "100"), ("abc", "100"), ("-5", "100")])
    def test_budget_empty_or_non_numeric(self, low, high):
        assert FilterIDPsByBudgetController().execute(FilterByBudgetRequest(low, high)).code == "INVALID_INPUT"

    # Checks no projects in budget range.
    def test_no_projects_in_budget_range(self, catalogue):
        result = FilterIDPsByBudgetController().execute(FilterByBudgetRequest("1", "100"))
        assert result.message == "No projects in this budget range."


# ---------------------------------------------------------------- US18 view details
class TestViewDetails:
    # US18: checks normal flow records exactly one view.
    def test_normal_flow_records_exactly_one_view(self, catalogue):
        session_id = make_customer()
        idp = catalogue["ids"]["kitchen"]
        result = ViewIDPDetailsController().execute(IDPIdRequest(idp, session_id))
        assert result.ok and result.data["title"] == "Bright Kitchen"
        assert ProjectViews().countByProject(idp) == 1

    # US18: checks project not found records no view.
    def test_project_not_found_records_no_view(self, catalogue):
        session_id = make_customer()
        result = ViewIDPDetailsController().execute(IDPIdRequest(999, session_id))
        assert result.message == "This project is no longer available."

    # US18: checks invalid project ID.
    def test_invalid_project_id(self):
        assert ViewIDPDetailsController().execute(IDPIdRequest("abc", "x")).code == "INVALID_INPUT"

    # US18: checks session expired records no view.
    def test_session_expired_records_no_view(self, catalogue):
        idp = catalogue["ids"]["kitchen"]
        assert ViewIDPDetailsController().execute(IDPIdRequest(idp, "expired")).code == "SESSION_EXPIRED"
        assert ProjectViews().countByProject(idp) == 0


# ---------------------------------------------------------------- US19-US22 favourites
class TestFavourites:
    # US19-US22: checks save then already saved.
    def test_save_then_already_saved(self, catalogue):
        session_id = make_customer()
        idp = catalogue["ids"]["kitchen"]
        assert SaveFavouriteController().execute(FavouriteRequest(session_id, idp)).message == "Saved to your favourites."
        again = SaveFavouriteController().execute(FavouriteRequest(session_id, idp))
        assert again.code == "ALREADY_SAVED"

    # US19-US22: checks save project no longer available.
    def test_save_project_no_longer_available(self, catalogue):
        session_id = make_customer()
        DeleteIDPController().execute(DeleteIDPRequest(catalogue["designer"], catalogue["ids"]["loft"]))
        result = SaveFavouriteController().execute(FavouriteRequest(session_id, catalogue["ids"]["loft"]))
        assert result.code == "NOT_AVAILABLE"

    # US19-US22: checks save session expired.
    def test_save_session_expired(self, catalogue):
        assert SaveFavouriteController().execute(FavouriteRequest("x", catalogue["ids"]["kitchen"])).code == \
            "SESSION_EXPIRED"

    # US19-US22: checks view favourites newest first and only own.
    def test_view_favourites_newest_first_and_only_own(self, catalogue, frozen_clock):
        from app.common import clock
        from datetime import timedelta
        amy, ben = make_customer(), make_customer("ben@example.test", "Ben")
        SaveFavouriteController().execute(FavouriteRequest(amy, catalogue["ids"]["kitchen"]))
        clock.freeze(frozen_clock + timedelta(minutes=5))
        SaveFavouriteController().execute(FavouriteRequest(amy, catalogue["ids"]["bedroom"]))
        SaveFavouriteController().execute(FavouriteRequest(ben, catalogue["ids"]["loft"]))
        titles = [f["title"] for f in ViewFavouritesController().execute(SessionRequest(amy)).data]
        assert titles == ["Calm Bedroom", "Bright Kitchen"]

    # US19-US22: checks view no favourites.
    def test_view_no_favourites(self):
        result = ViewFavouritesController().execute(SessionRequest(make_customer()))
        assert result.code == "EMPTY" and result.message == "You have no saved projects yet."

    # US19-US22: checks search favourites.
    def test_search_favourites(self, catalogue):
        session_id = make_customer()
        for idp in catalogue["ids"].values():
            SaveFavouriteController().execute(FavouriteRequest(session_id, idp))
        assert len(SearchFavouritesController().execute(SearchFavouritesRequest(session_id, "kitchen")).data) == 2
        assert SearchFavouritesController().execute(SearchFavouritesRequest(session_id, "")).code == "INVALID_INPUT"
        assert SearchFavouritesController().execute(SearchFavouritesRequest(session_id, "zzz")).code == "EMPTY"
        assert SearchFavouritesController().execute(SearchFavouritesRequest("x", "kitchen")).code == "SESSION_EXPIRED"

    # US19-US22: checks remove keeps history and allows resave.
    def test_remove_keeps_history_and_allows_resave(self, catalogue, fresh_db):
        session_id = make_customer()
        idp = catalogue["ids"]["kitchen"]
        SaveFavouriteController().execute(FavouriteRequest(session_id, idp))
        result = RemoveFavouriteController().execute(FavouriteRequest(session_id, idp))
        assert result.message == "Removed from your favourites."
        assert fresh_db.scalar("SELECT COUNT(*) FROM favourites WHERE removed_at IS NOT NULL") == 1
        assert ViewFavouritesController().execute(SessionRequest(session_id)).code == "EMPTY"
        assert SaveFavouriteController().execute(FavouriteRequest(session_id, idp)).ok

    # US19-US22: checks remove cancelled and already removed.
    def test_remove_cancelled_and_already_removed(self, catalogue):
        session_id = make_customer()
        idp = catalogue["ids"]["kitchen"]
        SaveFavouriteController().execute(FavouriteRequest(session_id, idp))
        assert RemoveFavouriteController().execute(FavouriteRequest(session_id, idp, confirmed=False)).code == \
            "CANCELLED"
        RemoveFavouriteController().execute(FavouriteRequest(session_id, idp))
        again = RemoveFavouriteController().execute(FavouriteRequest(session_id, idp))
        assert again.message == "This project is not in your favourites."
        assert RemoveFavouriteController().execute(FavouriteRequest("x", idp)).code == "SESSION_EXPIRED"
