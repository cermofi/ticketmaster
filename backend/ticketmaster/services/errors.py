from __future__ import annotations


class TicketMasterError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, *, details: dict | list | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(TicketMasterError):
    status_code = 404
    code = "not_found"


class PermissionDenied(TicketMasterError):
    status_code = 403
    code = "permission_denied"


class ValidationError(TicketMasterError):
    status_code = 400
    code = "validation_error"


class ConflictError(TicketMasterError):
    status_code = 409
    code = "conflict"


class RateLimitError(TicketMasterError):
    status_code = 429
    code = "rate_limit_exceeded"
