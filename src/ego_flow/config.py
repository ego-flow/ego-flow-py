"""Configuration loading for EgoFlow clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Union
from urllib.parse import urlsplit, urlunsplit

from ._version import __version__
from .errors import EgoFlowConfigError

DEFAULT_API_PATH = "/api/v1"
DEFAULT_USER_AGENT = "ego-flow-python/{}".format(__version__)


def _require_non_empty(name: str, value: Optional[Union[str, int]]) -> str:
    if value is None:
        raise EgoFlowConfigError(
            "{} is required. Set the environment variable or pass it explicitly.".format(name)
        )
    normalized = str(value).strip()
    if not normalized:
        raise EgoFlowConfigError(
            "{} is required. Set the environment variable or pass it explicitly.".format(name)
        )
    return normalized


def _ensure_scheme(endpoint: str) -> str:
    if "://" not in endpoint:
        return "http://{}".format(endpoint)
    return endpoint


def build_api_base_url(
    server_endpoint: Union[str, int],
    *,
    api_path: str = DEFAULT_API_PATH,
) -> str:
    """Normalize an endpoint into a final API base URL."""

    endpoint = _ensure_scheme(str(server_endpoint).strip().rstrip("/"))
    parts = urlsplit(endpoint)
    if not parts.scheme or not parts.netloc:
        raise EgoFlowConfigError("EF_SERVER_ENDPOINT must be a host or URL.")

    netloc = parts.netloc
    try:
        parts.port
    except ValueError as error:
        raise EgoFlowConfigError("EF_SERVER_ENDPOINT contains an invalid port.") from error

    path = parts.path.rstrip("/")
    normalized_api_path = "/" + api_path.strip("/")
    if path.endswith(normalized_api_path):
        final_path = path
    else:
        final_path = "{}{}".format(path, normalized_api_path) if path else normalized_api_path

    return urlunsplit((parts.scheme, netloc, final_path, "", "")).rstrip("/")


@dataclass(frozen=True)
class EgoFlowConfig:
    """Runtime configuration for an EgoFlow server connection."""

    token: str
    server_endpoint: str
    api_base_url: str
    timeout: float = 30.0
    max_retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        *,
        token: Optional[str] = None,
        server_endpoint: Optional[Union[str, int]] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> "EgoFlowConfig":
        source = os.environ if env is None else env
        final_token = _require_non_empty("EF_TOKEN", token if token is not None else source.get("EF_TOKEN"))
        final_endpoint = _require_non_empty(
            "EF_SERVER_ENDPOINT",
            server_endpoint if server_endpoint is not None else source.get("EF_SERVER_ENDPOINT"),
        )
        return cls.from_values(
            token=final_token,
            server_endpoint=final_endpoint,
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
        )

    @classmethod
    def from_values(
        cls,
        *,
        token: str,
        server_endpoint: Union[str, int],
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> "EgoFlowConfig":
        final_token = _require_non_empty("EF_TOKEN", token)
        final_endpoint = _require_non_empty("EF_SERVER_ENDPOINT", server_endpoint)
        api_base_url = build_api_base_url(final_endpoint)
        return cls(
            token=final_token,
            server_endpoint=final_endpoint,
            api_base_url=api_base_url,
            timeout=float(timeout),
            max_retries=int(max_retries),
            user_agent=user_agent,
        )

    @property
    def redacted_token(self) -> str:
        if len(self.token) <= 8:
            return "<redacted>"
        return "{}...{}".format(self.token[:4], self.token[-4:])

    def auth_headers(self) -> dict:
        return {
            "Authorization": "Bearer {}".format(self.token),
            "User-Agent": self.user_agent,
        }

    def __repr__(self) -> str:
        return "EgoFlowConfig(server_endpoint={!r}, api_base_url={!r}, token={!r})".format(
            self.server_endpoint,
            self.api_base_url,
            self.redacted_token,
        )
