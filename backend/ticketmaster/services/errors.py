from __future__ import annotations


class TicketMasterError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(TicketMasterError):
    status_code = 404


class PermissionDenied(TicketMasterError):
    status_code = 403


class ValidationError(TicketMasterError):
    status_code = 400


class ConflictError(TicketMasterError):
    status_code = 409
