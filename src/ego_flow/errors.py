"""Exception hierarchy for ego-flow."""

from __future__ import annotations

from typing import Any, Optional


class EgoFlowError(Exception):
    """Base exception for all package errors."""


class EgoFlowConfigError(EgoFlowError):
    """Raised when client configuration is missing or invalid."""


class EgoFlowDependencyError(EgoFlowError):
    """Raised when a runtime dependency is required but unavailable."""


class EgoFlowCapabilityError(EgoFlowError):
    """Raised when the connected server does not advertise a required capability."""


class EgoFlowHTTPError(EgoFlowError):
    """Base class for HTTP errors returned by an EgoFlow server."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error: Optional[str] = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.details = details


class EgoFlowBadRequestError(EgoFlowHTTPError):
    """Raised for HTTP 400 responses."""


class EgoFlowAuthenticationError(EgoFlowHTTPError):
    """Raised for HTTP 401 responses."""


class EgoFlowPermissionError(EgoFlowHTTPError):
    """Raised for HTTP 403 responses."""


class EgoFlowNotFoundError(EgoFlowHTTPError):
    """Raised for HTTP 404 responses."""


class EgoFlowConflictError(EgoFlowHTTPError):
    """Raised for HTTP 409 responses."""


class EgoFlowServerError(EgoFlowHTTPError):
    """Raised for unexpected server or network errors."""


class EgoFlowDownloadError(EgoFlowError):
    """Raised when an artifact cannot be downloaded or verified."""


class EgoFlowStreamError(EgoFlowError):
    """Raised when a live stream cannot be opened or decoded."""
