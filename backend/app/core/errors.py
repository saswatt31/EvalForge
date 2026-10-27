class EvalForgeError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(EvalForgeError):
    status_code = 404
    code = "not_found"


class ConflictError(EvalForgeError):
    status_code = 409
    code = "conflict"


class InvalidDatasetError(EvalForgeError):
    status_code = 422
    code = "invalid_dataset"


class ReadOnlyError(EvalForgeError):
    status_code = 403
    code = "read_only"


class UnauthorizedError(EvalForgeError):
    status_code = 401
    code = "unauthorized"


class RunStateError(EvalForgeError):
    status_code = 409
    code = "invalid_run_state"


class ExternalServiceError(EvalForgeError):
    status_code = 502
    code = "external_service_error"
