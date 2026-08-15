"""Typed data models for EgoFlow API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _expect_dict(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("{} must be an object".format(name))
    return value


@dataclass(frozen=True)
class ServerCapabilities:
    dataset_manifest: bool
    video_download: bool
    thumbnail_download: bool
    live_streams: bool
    python_tokens: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerCapabilities":
        return cls(
            dataset_manifest=bool(data.get("dataset_manifest", False)),
            video_download=bool(data.get("video_download", False)),
            thumbnail_download=bool(data.get("thumbnail_download", False)),
            live_streams=bool(data.get("live_streams", False)),
            python_tokens=bool(data.get("python_tokens", False)),
        )


@dataclass(frozen=True)
class ServerInfo:
    api_version: str
    server_version: str
    capabilities: ServerCapabilities

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerInfo":
        return cls(
            api_version=str(data.get("api_version", "")),
            server_version=str(data.get("server_version", "")),
            capabilities=ServerCapabilities.from_dict(_expect_dict(data.get("capabilities", {}), "capabilities")),
        )


@dataclass(frozen=True)
class RepositoryInfo:
    id: str
    name: str
    owner_id: str
    visibility: Optional[str] = None
    my_role: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def slug(self) -> str:
        return "{}/{}".format(self.owner_id, self.name)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepositoryInfo":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            owner_id=str(data.get("owner_id") or data.get("ownerId") or ""),
            visibility=data.get("visibility"),
            my_role=data.get("my_role"),
            description=data.get("description"),
            tags=[str(tag) for tag in data.get("tags", []) if isinstance(tag, str)],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(frozen=True)
class VideoArtifact:
    download_url: str
    size_bytes: Optional[int]
    sha256: Optional[str]
    content_type: Optional[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoArtifact":
        size = data.get("size_bytes")
        return cls(
            download_url=str(data.get("download_url", "")),
            size_bytes=int(size) if size is not None else None,
            sha256=data.get("sha256"),
            content_type=data.get("content_type"),
        )


@dataclass(frozen=True)
class ThumbnailArtifact:
    download_url: str
    content_type: Optional[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThumbnailArtifact":
        return cls(download_url=str(data.get("download_url", "")), content_type=data.get("content_type"))


@dataclass(frozen=True)
class ManifestVideo:
    video_id: str
    recorded_at: Optional[str]
    duration_sec: Optional[float]
    resolution_width: Optional[int]
    resolution_height: Optional[int]
    fps: Optional[float]
    codec: Optional[str]
    scene_summary: Optional[str]
    clip_segments: Any
    semantic_metadata: Dict[str, Any]
    artifact: VideoArtifact
    thumbnail: Optional[ThumbnailArtifact]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestVideo":
        artifacts = _expect_dict(data.get("artifacts", {}), "artifacts")
        thumbnail_raw = artifacts.get("thumbnail")
        raw_semantic_metadata = data.get("semantic_metadata")
        semantic_metadata = dict(raw_semantic_metadata) if isinstance(raw_semantic_metadata, dict) else {}
        return cls(
            video_id=str(data.get("video_id", "")),
            recorded_at=data.get("recorded_at"),
            duration_sec=float(data["duration_sec"]) if data.get("duration_sec") is not None else None,
            resolution_width=int(data["resolution_width"]) if data.get("resolution_width") is not None else None,
            resolution_height=int(data["resolution_height"]) if data.get("resolution_height") is not None else None,
            fps=float(data["fps"]) if data.get("fps") is not None else None,
            codec=data.get("codec"),
            scene_summary=data.get("scene_summary"),
            clip_segments=data.get("clip_segments"),
            semantic_metadata=semantic_metadata,
            artifact=VideoArtifact.from_dict(_expect_dict(artifacts.get("vlm_video", {}), "vlm_video")),
            thumbnail=ThumbnailArtifact.from_dict(thumbnail_raw) if isinstance(thumbnail_raw, dict) else None,
        )


@dataclass(frozen=True)
class ManifestPagination:
    total: int
    page: int
    limit: int
    has_next: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestPagination":
        return cls(
            total=int(data.get("total", 0)),
            page=int(data.get("page", 1)),
            limit=int(data.get("limit", 50)),
            has_next=bool(data.get("has_next", False)),
        )


@dataclass(frozen=True)
class ManifestPage:
    manifest_version: str
    repository: RepositoryInfo
    default_artifact: str
    pagination: ManifestPagination
    videos: List[ManifestVideo]
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestPage":
        return cls(
            manifest_version=str(data.get("manifest_version", "")),
            repository=RepositoryInfo.from_dict(_expect_dict(data.get("repository", {}), "repository")),
            default_artifact=str(data.get("default_artifact", "")),
            pagination=ManifestPagination.from_dict(_expect_dict(data.get("pagination", {}), "pagination")),
            videos=[ManifestVideo.from_dict(item) for item in data.get("videos", [])],
            raw=data,
        )


@dataclass(frozen=True)
class LiveStreamInfo:
    recording_session_id: str
    repository_id: str
    repository_name: str
    user_id: str
    device_type: Optional[str]
    ingest_type: str
    playback_available: bool
    status: str = "live"
    stream_path: Optional[str] = None
    owner_id: str = ""
    registered_at: str = ""
    playback_ready: Optional[bool] = None
    bytes_received: Optional[int] = None
    last_sequence: Optional[int] = None
    last_chunk_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LiveStreamInfo":
        return cls(
            recording_session_id=str(data.get("recording_session_id", "")),
            repository_id=str(data.get("repository_id", "")),
            repository_name=str(data.get("repository_name", "")),
            user_id=str(data.get("user_id", "")),
            device_type=data.get("device_type"),
            ingest_type=str(data.get("ingest_type", "")),
            playback_available=bool(data.get("playback_available", False)),
            status=str(data.get("status", "live")),
            stream_path=data.get("stream_path"),
            owner_id=str(data.get("owner_id", "")),
            registered_at=str(data.get("registered_at", "")),
            playback_ready=data.get("playback_ready"),
            bytes_received=int(data["bytes_received"]) if data.get("bytes_received") is not None else None,
            last_sequence=int(data["last_sequence"]) if data.get("last_sequence") is not None else None,
            last_chunk_at=data.get("last_chunk_at"),
        )
