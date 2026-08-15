"""Live stream listing and opening helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from .client import EgoFlowClient
from .errors import EgoFlowCapabilityError, EgoFlowNotFoundError, EgoFlowStreamError
from .models import LiveStreamInfo
from .video import FrameFormat, PyAVVideoSource

LiveIngestType = Literal["MEDIAMTX", "HTTP"]


class LiveStream(PyAVVideoSource):
    """Frame source for a server-provided HLS live stream."""

    def __init__(
        self,
        stream: LiveStreamInfo,
        *,
        client: EgoFlowClient,
        format: FrameFormat = "torch",
    ) -> None:
        if stream.playback_ready is None:
            stream = client.get_live_stream_detail(stream.recording_session_id)
        if stream.ingest_type != "MEDIAMTX" or not stream.playback_available:
            raise EgoFlowStreamError("Only MediaMTX live streams can be opened for HLS playback.")
        if stream.playback_ready is not True:
            raise EgoFlowStreamError("Live stream playback is not ready.")
        if not stream.stream_path:
            raise EgoFlowStreamError("Live stream response did not include a stream_path.")

        playback_ticket = client.issue_live_stream_playback_ticket(stream.recording_session_id)
        hls_url = client.build_live_hls_url(stream.stream_path, playback_ticket)

        self.stream = stream
        self.client = client
        metadata: Dict[str, Any] = {
            "recording_session_id": stream.recording_session_id,
            "repository_id": stream.repository_id,
            "repository_name": stream.repository_name,
            "owner_id": stream.owner_id,
            "user_id": stream.user_id,
            "device_type": stream.device_type,
            "ingest_type": stream.ingest_type,
            "stream_path": stream.stream_path,
            "status": stream.status,
            "playback_available": stream.playback_available,
            "playback_ready": stream.playback_ready,
            "registered_at": stream.registered_at,
            "bytes_received": stream.bytes_received,
            "last_sequence": stream.last_sequence,
            "last_chunk_at": stream.last_chunk_at,
            "hls_url": hls_url,
            "source_type": "live",
        }
        super().__init__(
            hls_url,
            source_type="live",
            source_id=stream.recording_session_id,
            metadata=metadata,
            format=format,
            headers={},
        )


def _client_from_args(
    *,
    client: Optional[EgoFlowClient],
    token: Optional[str],
    server_endpoint: Optional[str],
    timeout: float,
    max_retries: int,
) -> EgoFlowClient:
    if client is not None:
        return client
    return EgoFlowClient.from_env(
        token=token,
        server_endpoint=server_endpoint,
        timeout=timeout,
        max_retries=max_retries,
    )


def filter_live_streams(
    streams: List[LiveStreamInfo],
    *,
    ingest_type: Optional[LiveIngestType] = None,
    playback_available: Optional[bool] = None,
    repository_id: Optional[str] = None,
    repository_name: Optional[str] = None,
) -> List[LiveStreamInfo]:
    """Filter live stream summaries client-side."""

    filtered = streams
    if ingest_type is not None:
        filtered = [stream for stream in filtered if stream.ingest_type == ingest_type]
    if playback_available is not None:
        filtered = [stream for stream in filtered if stream.playback_available is playback_available]
    if repository_id is not None:
        filtered = [stream for stream in filtered if stream.repository_id == repository_id]
    if repository_name is not None:
        filtered = [stream for stream in filtered if stream.repository_name == repository_name]
    return filtered


def list_live_streams(
    *,
    client: Optional[EgoFlowClient] = None,
    token: Optional[str] = None,
    server_endpoint: Optional[str] = None,
    ingest_type: Optional[LiveIngestType] = None,
    playback_available: Optional[bool] = None,
    repository_id: Optional[str] = None,
    repository_name: Optional[str] = None,
    check_capability: bool = True,
    timeout: float = 30.0,
    max_retries: int = 2,
) -> List[LiveStreamInfo]:
    """List live streams visible to the current user."""

    ego_client = _client_from_args(
        client=client,
        token=token,
        server_endpoint=server_endpoint,
        timeout=timeout,
        max_retries=max_retries,
    )
    if check_capability:
        info = ego_client.info()
        if not info.capabilities.live_streams:
            raise EgoFlowCapabilityError(
                "This server reports live_streams=false. The current server code may need "
                "GET /api/v1/live-streams support for Python token auth."
            )
    return filter_live_streams(
        ego_client.list_live_streams(),
        ingest_type=ingest_type,
        playback_available=playback_available,
        repository_id=repository_id,
        repository_name=repository_name,
    )


def _select_stream(
    streams: List[LiveStreamInfo],
    selector: Optional[Union[LiveStreamInfo, str]],
) -> LiveStreamInfo:
    if isinstance(selector, LiveStreamInfo):
        return selector
    if selector is None:
        if len(streams) == 1:
            return streams[0]
        if not streams:
            raise EgoFlowNotFoundError("No live streams are currently available.", status_code=404)
        raise ValueError(
            "Multiple live streams are available; pass a LiveStreamInfo, recording_session_id, or stream_path."
        )
    for stream in streams:
        candidates = {stream.recording_session_id, stream.repository_name}
        if stream.stream_path:
            candidates.add(stream.stream_path)
        if selector in candidates:
            return stream
    raise EgoFlowNotFoundError("Live stream {!r} was not found.".format(selector), status_code=404)


def open_live_stream(
    stream: Optional[Union[LiveStreamInfo, str]] = None,
    *,
    client: Optional[EgoFlowClient] = None,
    token: Optional[str] = None,
    server_endpoint: Optional[str] = None,
    check_capability: bool = True,
    format: FrameFormat = "torch",
    timeout: float = 30.0,
    max_retries: int = 2,
) -> LiveStream:
    """Open a live stream as a frame source."""

    ego_client = _client_from_args(
        client=client,
        token=token,
        server_endpoint=server_endpoint,
        timeout=timeout,
        max_retries=max_retries,
    )
    if isinstance(stream, LiveStreamInfo):
        selected = stream
    else:
        selected = _select_stream(
            list_live_streams(client=ego_client, check_capability=check_capability),
            stream,
        )
    return LiveStream(
        selected,
        client=ego_client,
        format=format,
    )
