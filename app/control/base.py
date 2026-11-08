"""Common helpers shared by all Controllers.

Every Controller exposes ``execute(request) -> Result``. ``validateRequest`` stores the first
problem in ``self.error`` so ``invalidInputResult()`` can report it. Invalid input never
reaches the Entity layer.
"""
from app.common.result import Result


class Controller:
    error = "Please check the details you entered."

    # Remembers why a request is invalid and returns False (used inside validateRequest).
    def reject(self, message):
        """Used inside validateRequest(): remember why the request is invalid and return False."""
        self.error = message
        return False

    # The failure Result for invalid input, with the remembered reason.
    def invalidInputResult(self):
        return Result.fail("INVALID_INPUT", self.error)

    # The failure Result for an ended session.
    def sessionExpiredResult(self):
        return Result.fail("SESSION_EXPIRED", "Your session has expired. Please log in again.")
