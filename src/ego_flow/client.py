"""HTTP client for the EgoFlow server API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Generator, Mapping, Optional, Tuple

from .config import EgoFlowConfig
from .errors import (
    EgoFlowAuthenticationError,
    EgoFlowBadRequestError,
    EgoFlowCapabilityError,
    EgoFlowConflictError,
    EgoFlowDownloadError,
    EgoFlowHTTPError,
    EgoFlowNotFoundError,
    EgoFlowPermissionError,
    EgoFlowServerError,
)
from .models import LiveStreamInfo, ManifestPage, RepositoryInfo, ServerInfo

_ABSOLUTE_URL_PREFIXES = ("http://", "https://")
_ORIGIN_RELATIVE_PREFIXES = ("/api/", "/files/")
_DIRECT_HLS_PORT = 8888


def _url_origin(url: str) -> Tuple[str, str, Optional[int]]:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    default_port = {"http": 80, "https": 443}.get(scheme)
    return scheme, (parts.hostname or "").lower(), parts.port or default_port


def _same_origin(first: str, second: str) -> bool:
    try:
        return _url_origin(first) == _url_origin(second)
    except ValueError:
        return False


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent server credentials from crossing an HTTP redirect origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and not _same_origin(req.full_url, newurl):
            redirected.remove_header("Authorization")
            redirected.remove_header("Proxy-Authorization")
        return redirected


def _json_from_bytes(data: bytes) -> Dict[str, Any]:
    if not data:
        return {}
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _raise_for_http_error(error: urllib.error.HTTPError) -> None:
    payload = _json_from_bytes(error.read())
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        error_code = error_payload.get("code")
        message = str(error_payload.get("message") or error.reason or "HTTP request failed.")
        details = error_payload.get("details")
    else:
        error_code = error_payload
        message = str(payload.get("message") or error.reason or "HTTP request failed.")
        details = payload.get("details")
    code = int(error.code)
    error_name = str(error_code) if error_code is not None else None
    if code == 400:
        raise EgoFlowBadRequestError(message, status_code=code, error=error_name, details=details)
    if code == 401:
        raise EgoFlowAuthenticationError(message, status_code=code, error=error_name, details=details)
    if code == 403:
        raise EgoFlowPermissionError(message, status_code=code, error=error_name, details=details)
    if code == 404:
        raise EgoFlowNotFoundError(message, status_code=code, error=error_name, details=details)
    if code == 409:
        raise EgoFlowConflictError(message, status_code=code, error=error_name, details=details)
    raise EgoFlowServerError(message, status_code=code, error=error_name, details=details)


class UrllibTransport:
    """Small sync transport wrapper using Python's standard library."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_SameOriginRedirectHandler())

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers=dict(headers), method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return _json_from_bytes(response.read())
        except urllib.error.HTTPError as error:
            _raise_for_http_error(error)
        except urllib.error.URLError as error:
            raise EgoFlowServerError("Could not reach EgoFlow server: {}".format(error.reason)) from error
        raise EgoFlowServerError("Unexpected empty HTTP response.")

    def download(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        destination: Path,
        timeout: float,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                with destination.open("wb") as handle:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
        except urllib.error.HTTPError as error:
            _raise_for_http_error(error)
        except urllib.error.URLError as error:
            raise EgoFlowDownloadError("Could not download artifact: {}".format(error.reason)) from error


class EgoFlowClient:
    """Synchronous API client for EgoFlow."""

    def __init__(self, config: EgoFlowConfig, *, transport: Optional[Any] = None) -> None:
        self.config = config
        self.transport = transport or UrllibTransport()
        self._python_user_id: Optional[str] = None

    @classmethod
    def from_env(
        cls,
        *,
        token: Optional[str] = None,
        server_endpoint: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: Optional[str] = None,
        transport: Optional[Any] = None,
    ) -> "EgoFlowClient":
        kwargs: Dict[str, Any] = {
            "token": token,
            "server_endpoint": server_endpoint,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if user_agent is not None:
            kwargs["user_agent"] = user_agent
        return cls(EgoFlowConfig.from_env(**kwargs), transport=transport)

    def _absolute_url(self, path_or_url: str, params: Optional[Mapping[str, Any]] = None) -> str:
        base = self.config.api_base_url.rstrip("/") + "/"
        url = urllib.parse.urljoin(base, path_or_url.lstrip("/"))
        if params:
            clean_params = {
                key: value
                for key, value in params.items()
                if value is not None
            }
            if clean_params:
                separator = "&" if urllib.parse.urlsplit(url).query else "?"
                url = "{}{}{}".format(url, separator, urllib.parse.urlencode(clean_params))
        return url

    @staticmethod
    def _path_segment(value: str) -> str:
        return urllib.parse.quote(str(value), safe="")

    def _origin_url(self) -> str:
        parts = urllib.parse.urlsplit(self.config.api_base_url)
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")

    def _absolute_any_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(_ABSOLUTE_URL_PREFIXES):
            return path_or_url
        if path_or_url.startswith("/"):
            parts = urllib.parse.urlsplit(self.config.api_base_url)
            origin = self._origin_url()
            api_path = parts.path.rstrip("/")
            if api_path and path_or_url.startswith(api_path + "/"):
                return urllib.parse.urljoin(origin + "/", path_or_url.lstrip("/"))
            if path_or_url.startswith(_ORIGIN_RELATIVE_PREFIXES):
                return urllib.parse.urljoin(origin + "/", path_or_url.lstrip("/"))
            return self._absolute_url(path_or_url)
        return self._absolute_url(path_or_url)

    def build_live_hls_url(self, stream_path: str, playback_ticket: str) -> str:
        """Build the direct MediaMTX HLS URL for a live stream."""

        normalized_stream_path = stream_path.strip("/")
        if not normalized_stream_path:
            raise EgoFlowServerError("Live stream response did not include a stream_path.")

        parts = urllib.parse.urlsplit(self.config.api_base_url)
        host = parts.hostname
        if not host:
            raise EgoFlowServerError("Could not determine EgoFlow server host for HLS playback.")
        if ":" in host and not host.startswith("["):
            host = "[{}]".format(host)

        query = urllib.parse.urlencode({"ticket": playback_ticket})
        path = "/{}/index.m3u8".format(urllib.parse.quote(normalized_stream_path, safe="/"))
        return urllib.parse.urlunsplit(
            (
                "http",
                "{}:{}".format(host, _DIRECT_HLS_PORT),
                path,
                query,
                "",
            )
        )

    def _headers(self, *, auth: bool = True, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": self.config.user_agent}
        if auth:
            headers["Authorization"] = "Bearer {}".format(self.config.token)
        if extra:
            headers.update(extra)
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        url = self._absolute_url(path, params)
        last_error: Optional[Exception] = None
        attempts = max(1, self.config.max_retries + 1)
        for attempt in range(attempts):
            try:
                return self.transport.request_json(
                    method,
                    url,
                    headers=self._headers(auth=auth),
                    timeout=self.config.timeout,
                )
            except (
                EgoFlowBadRequestError,
                EgoFlowAuthenticationError,
                EgoFlowPermissionError,
                EgoFlowNotFoundError,
                EgoFlowConflictError,
            ):
                raise
            except EgoFlowServerError as error:
                last_error = error
                if attempt + 1 >= attempts:
                    break
                time.sleep(min(0.25 * (2 ** attempt), 2.0))
            except EgoFlowHTTPError:
                raise
        if last_error:
            raise last_error
        raise EgoFlowServerError("HTTP request failed.")

    def health(self) -> Dict[str, Any]:
        return self._request_json("GET", "/health", auth=False)

    def info(self) -> ServerInfo:
        return ServerInfo.from_dict(self._request_json("GET", "/info", auth=False))

    def validate_python_token(self) -> Dict[str, Any]:
        return self._request_json("GET", "/auth/python/tokens/validate", auth=True)

    def validate_token(self) -> Dict[str, Any]:
        return self.validate_python_token()

    def python_user_id(self) -> str:
        if self._python_user_id is not None:
            return self._python_user_id
        payload = self.validate_python_token()
        user = payload.get("user")
        if not isinstance(user, dict) or not user.get("id"):
            raise EgoFlowServerError("Python token validation response did not include user.id.")
        self._python_user_id = str(user["id"])
        return self._python_user_id

    def resolve_repository(self, slug: str) -> RepositoryInfo:
        payload = self._request_json("GET", "/repositories/resolve", params={"slug": slug}, auth=True)
        repository = payload.get("repository")
        if not isinstance(repository, dict):
            raise EgoFlowServerError("Repository resolve response did not contain a repository object.")
        return RepositoryInfo.from_dict(repository)

    def list_repositories(self) -> list[RepositoryInfo]:
        raise EgoFlowCapabilityError(
            "The current EgoFlow server does not expose repository listing to Python tokens. "
            "Use resolve_repository('owner/name') for Python-library workflows."
        )

    def get_manifest_page(self, repo_id: str, *, page: int = 1, limit: int = 200) -> ManifestPage:
        payload = self._request_json(
            "GET",
            "/repositories/{}/manifest".format(self._path_segment(repo_id)),
            params={"page": int(page), "limit": int(limit)},
            auth=True,
        )
        return ManifestPage.from_dict(payload)

    def iter_manifest(self, repo_id: str, *, page_size: int = 200) -> Generator[ManifestPage, None, None]:
        page = 1
        while True:
            manifest = self.get_manifest_page(repo_id, page=page, limit=page_size)
            yield manifest
            if not manifest.pagination.has_next:
                break
            page += 1

    def download_artifact(
        self,
        download_url: str,
        destination: Path,
        *,
        expected_sha256: Optional[str] = None,
    ) -> Path:
        from .cache import sha256_file

        if not download_url:
            raise EgoFlowDownloadError("Artifact download URL is empty.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_name("{}.tmp".format(destination.name))
        if tmp_path.exists():
            tmp_path.unlink()

        url = self._absolute_any_url(download_url)
        try:
            self.transport.download(
                url,
                headers=self._headers(auth=_same_origin(url, self.config.api_base_url)),
                destination=tmp_path,
                timeout=self.config.timeout,
            )
            if expected_sha256:
                actual_sha = sha256_file(tmp_path)
                if actual_sha.lower() != expected_sha256.lower():
                    raise EgoFlowDownloadError(
                        "Downloaded artifact hash mismatch: expected {}, got {}".format(
                            expected_sha256,
                            actual_sha,
                        )
                    )
            tmp_path.replace(destination)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return destination

    def download_video(
        self,
        repo_id: str,
        video_id: str,
        destination: Path,
        *,
        expected_sha256: Optional[str] = None,
        download_url: Optional[str] = None,
    ) -> Path:
        url = download_url or "/repositories/{}/videos/{}/download".format(
            self._path_segment(repo_id),
            self._path_segment(video_id),
        )
        return self.download_artifact(url, destination, expected_sha256=expected_sha256)

    def download_thumbnail(
        self,
        repo_id: str,
        video_id: str,
        destination: Path,
        *,
        download_url: Optional[str] = None,
    ) -> Path:
        url = download_url or "/repositories/{}/videos/{}/thumbnail".format(
            self._path_segment(repo_id),
            self._path_segment(video_id),
        )
        return self.download_artifact(url, destination)

    def list_live_streams(self) -> list[LiveStreamInfo]:
        payload = self._request_json("GET", "/live-streams", auth=True)
        streams = payload.get("streams", [])
        return [LiveStreamInfo.from_dict(item) for item in streams]

    def get_live_stream_detail(self, recording_session_id: str) -> LiveStreamInfo:
        payload = self._request_json(
            "GET",
            "/live-streams/{}".format(self._path_segment(recording_session_id)),
            auth=True,
        )
        return LiveStreamInfo.from_dict(payload)

    def issue_live_stream_playback_ticket(self, recording_session_id: str) -> str:
        payload = self._request_json(
            "POST",
            "/live-streams/{}/playback-ticket".format(self._path_segment(recording_session_id)),
            auth=True,
        )
        ticket = payload.get("playback_ticket")
        if not ticket:
            raise EgoFlowServerError("Playback ticket response did not include playback_ticket.")
        return str(ticket)
