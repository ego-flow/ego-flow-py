"""Top-level package for ego-flow."""

from ._version import __version__
from .client import EgoFlowClient
from .config import EgoFlowConfig
from .dataset import load_dataset
from .errors import (
    EgoFlowAuthenticationError,
    EgoFlowBadRequestError,
    EgoFlowCapabilityError,
    EgoFlowConfigError,
    EgoFlowDependencyError,
    EgoFlowError,
    EgoFlowNotFoundError,
    EgoFlowPermissionError,
    EgoFlowStreamError,
)
from .live import LiveStream, filter_live_streams, list_live_streams, open_live_stream
from .models import (
    LiveStreamInfo,
    ManifestVideo,
    RepositoryInfo,
    ServerInfo,
)
from .video import FrameBatch, RepositoryVideoSource, VideoFrame, open_video

__all__ = [
    "__version__",
    "EgoFlowAuthenticationError",
    "EgoFlowBadRequestError",
    "EgoFlowCapabilityError",
    "EgoFlowClient",
    "EgoFlowConfig",
    "EgoFlowConfigError",
    "EgoFlowDependencyError",
    "EgoFlowError",
    "EgoFlowNotFoundError",
    "EgoFlowPermissionError",
    "EgoFlowStreamError",
    "FrameBatch",
    "LiveStream",
    "LiveStreamInfo",
    "ManifestVideo",
    "RepositoryInfo",
    "RepositoryVideoSource",
    "ServerInfo",
    "VideoFrame",
    "filter_live_streams",
    "list_live_streams",
    "load_dataset",
    "open_live_stream",
    "open_video",
]
