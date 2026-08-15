"""Artifact cache helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from .models import ManifestPage, ManifestVideo, RepositoryInfo


def default_cache_dir() -> Path:
    configured = os.environ.get("EGO_FLOW_CACHE")
    if configured:
        return Path(configured).expanduser()
    try:
        from platformdirs import user_cache_dir  # type: ignore

        return Path(user_cache_dir("ego-flow"))
    except Exception:
        return Path.home() / ".cache" / "ego-flow"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned or "unknown"


def _extension(content_type: Optional[str], fallback: str) -> str:
    if content_type == "video/mp4":
        return ".mp4"
    if content_type == "image/jpeg":
        return ".jpg"
    return fallback


class CacheManager:
    """Filesystem cache for server-scoped repository artifacts."""

    def __init__(self, root: Optional[Path], *, api_base_url: str) -> None:
        self.root = Path(root).expanduser() if root is not None else default_cache_dir()
        self.api_base_url = api_base_url
        self.server_root = self.root / "servers" / self._server_fingerprint(api_base_url)

    @staticmethod
    def _server_fingerprint(api_base_url: str) -> str:
        digest = hashlib.sha1(api_base_url.encode("utf-8")).hexdigest()[:12]
        host_hint = re.sub(r"^https?://", "", api_base_url).split("/")[0]
        return "{}-{}".format(_safe_part(host_hint), digest)

    def repository_dir(self, repository: RepositoryInfo) -> Path:
        return (
            self.server_root
            / "repositories"
            / _safe_part(repository.owner_id)
            / _safe_part(repository.name)
        )

    def manifest_path(self, repository: RepositoryInfo) -> Path:
        return self.repository_dir(repository) / "manifest.json"

    def video_path(self, repository: RepositoryInfo, video: ManifestVideo) -> Path:
        sha = video.artifact.sha256 or "unknown"
        filename = "{}-{}{}".format(
            _safe_part(video.video_id),
            _safe_part(sha[:12]),
            _extension(video.artifact.content_type, ".mp4"),
        )
        return self.repository_dir(repository) / "videos" / filename

    def thumbnail_path(self, repository: RepositoryInfo, video: ManifestVideo) -> Path:
        return self.repository_dir(repository) / "thumbnails" / "{}.jpg".format(_safe_part(video.video_id))

    def has_valid_file(self, path: Path, expected_sha256: Optional[str] = None) -> bool:
        if not path.exists() or not path.is_file():
            return False
        if expected_sha256:
            return sha256_file(path).lower() == expected_sha256.lower()
        return True

    def write_manifest(self, repository: RepositoryInfo, pages: list) -> None:
        manifest_path = self.manifest_path(repository)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [page.raw if isinstance(page, ManifestPage) else page for page in pages]
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def ensure_video(
        self,
        client: Any,
        repository: RepositoryInfo,
        video: ManifestVideo,
        *,
        download_mode: str = "reuse_cache_if_exists",
    ) -> Path:
        path = self.video_path(repository, video)
        expected_sha = video.artifact.sha256
        if download_mode != "force_redownload" and self.has_valid_file(path, expected_sha):
            return path
        return client.download_video(
            repository.id,
            video.video_id,
            path,
            expected_sha256=expected_sha,
            download_url=video.artifact.download_url,
        )

    def ensure_thumbnail(
        self,
        client: Any,
        repository: RepositoryInfo,
        video: ManifestVideo,
        *,
        download_mode: str = "reuse_cache_if_exists",
    ) -> Optional[Path]:
        if video.thumbnail is None:
            return None
        path = self.thumbnail_path(repository, video)
        if download_mode != "force_redownload" and self.has_valid_file(path):
            return path
        return client.download_thumbnail(
            repository.id,
            video.video_id,
            path,
            download_url=video.thumbnail.download_url,
        )
