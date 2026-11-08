"""Result object returned by every Controller and most Entity methods.

Matches the design note: Result = { ok: bool, code: String, data: optional safe data, message: String }.
Member 1 diagrams use ``result.success``; it is provided as an alias of ``ok``.
"""


class Result:
    # Stores whether it worked, a short code, the message to show and any data.
    def __init__(self, ok, code, message="", data=None):
        self.ok = ok
        self.code = code
        self.message = message
        self.data = data

    # Same as ok; the Member 1 diagrams call it success.
    @property
    def success(self):
        return self.ok

    # Makes a successful Result.
    @classmethod
    def succeed(cls, code="OK", message="", data=None):
        return cls(True, code, message, data)

    # Makes a failed Result.
    @classmethod
    def fail(cls, code, message, data=None):
        return cls(False, code, message, data)

    # Short text form of a Result, used in test failure messages.
    def __repr__(self):
        return f"Result(ok={self.ok}, code={self.code!r}, message={self.message!r})"
