"""Unified video frame interface for repository and live sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Literal, Optional

from .errors import EgoFlowDependencyError

FrameFormat = Literal["torch", "numpy", "native"]
SourceType = Literal["repository", "live"]


@dataclass(frozen=True)
class VideoFrame:
    data: Any
    pts_seconds: Optional[float]
    index: Optional[int]
    source_type: SourceType
    source_id: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class FrameBatch:
    data: Any
    pts_seconds: List[Optional[float]]
    source_type: SourceType
    source_id: str
    metadata: Dict[str, Any]


def _validate_frame_format(frame_format: str) -> None:
    if frame_format not in {"torch", "numpy", "native"}:
        raise ValueError("format must be one of 'torch', 'numpy', or 'native'.")


def _require_av() -> Any:
    try:
        import av  # type: ignore
    except Exception as error:
        raise EgoFlowDependencyError(
            "Frame decoding requires PyAV, which is included in the default ego-flow install. "
            "Reinstall ego-flow to restore the missing dependency."
        ) from error
    return av


def _frame_to_data(frame: Any, frame_format: FrameFormat) -> Any:
    _validate_frame_format(frame_format)
    if frame_format == "native":
        return frame

    array = frame.to_ndarray(format="rgb24")
    if frame_format == "numpy":
        return array

    if frame_format == "torch":
        try:
            import torch  # type: ignore
        except Exception as error:
            raise EgoFlowDependencyError(
                "format='torch' requires PyTorch, which is included in the default ego-flow install. "
                "Reinstall ego-flow to restore the missing dependency, or pass format='numpy'."
            ) from error
        return torch.from_numpy(array).permute(2, 0, 1).contiguous()


def _stack_batch(frames: List[Any], frame_format: FrameFormat) -> Any:
    _validate_frame_format(frame_format)
    if frame_format == "native":
        return frames
    if frame_format == "numpy":
        try:
            import numpy as np  # type: ignore
        except Exception as error:
            raise EgoFlowDependencyError("format='numpy' batching requires NumPy.") from error
        return np.stack(frames, axis=0)
    if frame_format == "torch":
        try:
            import torch  # type: ignore
        except Exception as error:
            raise EgoFlowDependencyError("format='torch' batching requires PyTorch.") from error
        return torch.stack(frames, dim=0)


class PyAVVideoSource:
    """Video source backed by PyAV."""

    def __init__(
        self,
        source: str,
        *,
        source_type: SourceType,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        format: FrameFormat = "torch",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        _validate_frame_format(format)
        self.source = source
        self.source_type = source_type
        self.source_id = source_id
        self.metadata = dict(metadata or {})
        self.format = format
        self.headers = headers or {}
        self._container = None

    def _open(self) -> Any:
        av = _require_av()
        options: Dict[str, str] = {}
        if self.headers:
            header_lines = ["{}: {}".format(key, value) for key, value in self.headers.items()]
            options["headers"] = "\r\n".join(header_lines) + "\r\n"
        self._container = av.open(self.source, options=options)
        return self._container

    def close(self) -> None:
        if self._container is not None:
            self._container.close()
            self._container = None

    def iter_frames(
        self,
        *,
        fps: Optional[float] = None,
        limit: Optional[int] = None,
        start_seconds: Optional[float] = None,
        end_seconds: Optional[float] = None,
    ) -> Generator[VideoFrame, None, None]:
        if limit is not None and limit <= 0:
            return

        container = self._open()
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            self.close()
            return

        emitted = 0
        decoded_index = 0
        last_pts: Optional[float] = None
        min_delta = 1.0 / fps if fps and fps > 0 else None
        try:
            for frame in container.decode(video_stream):
                pts_seconds = frame.time
                if start_seconds is not None and pts_seconds is not None and pts_seconds < start_seconds:
                    decoded_index += 1
                    continue
                if end_seconds is not None and pts_seconds is not None and pts_seconds > end_seconds:
                    break
                if min_delta is not None and pts_seconds is not None and last_pts is not None:
                    if pts_seconds - last_pts < min_delta:
                        decoded_index += 1
                        continue

                data = _frame_to_data(frame, self.format)
                last_pts = pts_seconds
                yield VideoFrame(
                    data=data,
                    pts_seconds=pts_seconds,
                    index=decoded_index,
                    source_type=self.source_type,
                    source_id=self.source_id,
                    metadata=dict(self.metadata),
                )
                emitted += 1
                decoded_index += 1
                if limit is not None and emitted >= limit:
                    break
        finally:
            self.close()

    def iter_batches(
        self,
        *,
        batch_size: int,
        fps: Optional[float] = None,
        limit: Optional[int] = None,
        start_seconds: Optional[float] = None,
        end_seconds: Optional[float] = None,
    ) -> Generator[FrameBatch, None, None]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        frames: List[Any] = []
        pts: List[Optional[float]] = []
        for frame in self.iter_frames(
            fps=fps,
            limit=limit,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        ):
            frames.append(frame.data)
            pts.append(frame.pts_seconds)
            if len(frames) == batch_size:
                yield FrameBatch(
                    data=_stack_batch(frames, self.format),
                    pts_seconds=pts,
                    source_type=self.source_type,
                    source_id=self.source_id,
                    metadata=dict(self.metadata),
                )
                frames = []
                pts = []

        if frames:
            yield FrameBatch(
                data=_stack_batch(frames, self.format),
                pts_seconds=pts,
                source_type=self.source_type,
                source_id=self.source_id,
                metadata=dict(self.metadata),
            )


class RepositoryVideoSource(PyAVVideoSource):
    def __init__(
        self,
        path: str,
        *,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        format: FrameFormat = "torch",
    ) -> None:
        super().__init__(
            path,
            source_type="repository",
            source_id=source_id or Path(path).stem,
            metadata=metadata,
            format=format,
        )


def open_video(
    row_or_path: Any,
    *,
    format: FrameFormat = "torch",
) -> RepositoryVideoSource:
    """Open a repository dataset row or local video path as a frame source."""

    metadata: Dict[str, Any] = {}
    source_id: Optional[str] = None
    if isinstance(row_or_path, dict):
        path = row_or_path.get("video_path") or row_or_path.get("video")
        source_id = row_or_path.get("video_id")
        metadata = dict(row_or_path)
    else:
        path = row_or_path

    if isinstance(path, dict):
        path = path.get("path") or path.get("filename")
    if not path:
        raise ValueError("open_video requires a dataset row with video_path/video or a path string.")
    return RepositoryVideoSource(str(path), source_id=source_id, metadata=metadata, format=format)


def ensure_batches(source: PyAVVideoSource, *, batch_size: int) -> Iterable[FrameBatch]:
    return source.iter_batches(batch_size=batch_size)
