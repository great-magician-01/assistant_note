"""Application business exceptions.

Mapping to HTTP status codes is handled by exception handlers in main.py:
  - BusinessError  -> 400 (business rule violation, e.g. duplicate name)
  - NotFoundError  -> 404 (resource does not exist)
  - Any other uncaught Exception -> 500 (unexpected code error)
"""


class BusinessError(Exception):
    """A business rule was violated. Maps to HTTP 400."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(BusinessError):
    """A requested resource does not exist. Maps to HTTP 404."""

    pass
