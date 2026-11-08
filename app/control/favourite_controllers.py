"""US19-US22 - Customer favourites. The customer is always taken from the session."""
from app.common.result import Result
from app.common.validators import is_blank, to_positive_int
from app.control.base import Controller
from app.control.login_controllers import AccessGuardController
from app.entity.database import CUSTOMER
from app.entity.favourites import Favourites


class _FavouriteController(Controller):
    # Sets up the controller with favourites and the access guard.
    def __init__(self):
        self.model = Favourites()
        self.accessGuard = AccessGuardController()

    # Checks the project ID is a whole number.
    def validateIdp(self, request):
        idp_id = to_positive_int(request.idpId)
        if idp_id is None:
            return self.reject("Invalid project ID.")
        request.idpId = idp_id
        return True


class SaveFavouriteController(_FavouriteController):
    """US19 Save IDP to Favourites."""

    # US19: saves the project to the logged-in Customer's favourites.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        customer_id = access.data["accountId"]
        if self.model.isSaved(customer_id, request.idpId):
            return self.alreadySavedResult()
        return self.model.add(customer_id, request.idpId)

    # Checks the project ID.
    def validateRequest(self, request):
        return self.validateIdp(request)

    # The failure when the project is already saved.
    def alreadySavedResult(self):
        return Result.fail("ALREADY_SAVED", "This project is already in your favourites.")


class ViewFavouritesController(_FavouriteController):
    """US20 View Favourites (newest first, removed ones left out)."""

    # US20: returns the logged-in Customer's saved projects.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        return self.model.findByCustomer(access.data["accountId"])

    # Checks a request was given.
    def validateRequest(self, request):
        return True if request is not None else self.reject("Invalid request.")


class SearchFavouritesController(_FavouriteController):
    """US21 Search Favourites by keyword."""

    # US21: returns saved projects matching a keyword.
    def execute(self, request):
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        return self.model.search(access.data["accountId"], request.keyword)

    # Checks a keyword of up to 100 characters.
    def validateRequest(self, request):
        if is_blank(request.keyword):
            return self.reject("Please enter a keyword.")
        if len(request.keyword.strip()) > 100:
            return self.reject("Keyword must be 100 characters or fewer.")
        return True


class RemoveFavouriteController(_FavouriteController):
    """US22 Remove IDP from Favourites (soft remove: keeps save time, sets removal time)."""

    # US22: removes a project from favourites after confirmation (history is kept).
    def execute(self, request):
        if not request.confirmed:
            return Result.fail("CANCELLED", "Nothing was removed.")
        if not self.validateRequest(request):
            return self.invalidInputResult()
        access = self.accessGuard.execute(request, CUSTOMER)
        if not access.ok:
            return access
        return self.model.remove(access.data["accountId"], request.idpId)

    # Checks the project ID.
    def validateRequest(self, request):
        return self.validateIdp(request)
