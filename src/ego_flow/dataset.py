"""HF Datasets style loading API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .cache import CacheManager
from .client import EgoFlowClient
from .errors import EgoFlowCapabilityError, EgoFlowDependencyError
from .models import ManifestPage, ManifestVideo, RepositoryInfo

VALID_DOWNLOAD_MODES = {
    "reuse_cache_if_exists",
    "force_redownload",
    "reuse_dataset_if_exists",
}


def _require_datasets() -> Any:
    try:
        import datasets  # type: ignore
    except Exception as error:
        raise EgoFlowDependencyError(
            "load_dataset requires the 'datasets' package, which is included in the default ego-flow install. "
            "Reinstall ego-flow to restore the missing dependency."
        ) from error
    return datasets


def _validate_split(split: Optional[str]) -> None:
    if split is not None and split != "train":
        raise ValueError("EgoFlow repositories currently expose only the 'train' split.")


def _validate_download_mode(download_mode: str) -> None:
    if download_mode not in VALID_DOWNLOAD_MODES:
        raise ValueError("download_mode must be one of {}".format(sorted(VALID_DOWNLOAD_MODES)))


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


def _check_dataset_capabilities(client: EgoFlowClient) -> None:
    info = client.info()
    capabilities = info.capabilities
    if not capabilities.python_tokens:
        raise EgoFlowCapabilityError("This server does not advertise Python token support.")
    if not capabilities.dataset_manifest:
        raise EgoFlowCapabilityError("This server does not advertise dataset manifest support.")
    if not capabilities.video_download:
        raise EgoFlowCapabilityError("This server does not advertise video download support.")


def _resolve_or_stub_repository(
    client: EgoFlowClient,
    path: str,
    *,
    repo_id: Optional[str],
) -> RepositoryInfo:
    if repo_id is None:
        return client.resolve_repository(path)
    owner, name = _split_slug(path)
    return RepositoryInfo(id=repo_id, owner_id=owner, name=name, visibility=None, my_role="read")


def _split_slug(path: str) -> Tuple[str, str]:
    parts = path.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Dataset path must be in 'owner/repository' format.")
    return parts[0], parts[1]


def _materialize_pages(client: EgoFlowClient, repository: RepositoryInfo, page_size: int) -> List[ManifestPage]:
    pages = list(client.iter_manifest(repository.id, page_size=page_size))
    if pages:
        return pages
    return []


def _row_from_video(
    repository: RepositoryInfo,
    video: ManifestVideo,
    *,
    video_path: Path,
    thumbnail_path: Optional[Path],
) -> Dict[str, Any]:
    return {
        "video_id": video.video_id,
        "repository_id": repository.id,
        "repository_name": repository.name,
        "owner_id": repository.owner_id,
        "video": str(video_path),
        "video_path": str(video_path),
        "duration_sec": video.duration_sec,
        "fps": video.fps,
        "resolution_width": video.resolution_width,
        "resolution_height": video.resolution_height,
        "codec": video.codec,
        "recorded_at": video.recorded_at,
        "scene_summary": video.scene_summary,
        "clip_segments": video.clip_segments,
        "semantic_metadata": video.semantic_metadata,
        "thumbnail_path": str(thumbnail_path) if thumbnail_path is not None else None,
        "artifact_size_bytes": video.artifact.size_bytes,
        "artifact_sha256": video.artifact.sha256,
        "source_type": "repository",
    }


def _make_hf_dataset(rows: List[Dict[str, Any]], *, decode: bool) -> Any:
    datasets = _require_datasets()
    dataset = datasets.Dataset.from_list(rows)
    if rows and hasattr(datasets, "Video"):
        try:
            dataset = dataset.cast_column("video", datasets.Video(decode=decode))
        except Exception:
            # Keep the path column intact if a datasets backend cannot cast video.
            pass
    return dataset


def _wrap_split(dataset: Any, split: Optional[str], *, streaming: bool = False) -> Any:
    if split == "train":
        return dataset
    datasets = _require_datasets()
    if streaming and hasattr(datasets, "IterableDatasetDict"):
        return datasets.IterableDatasetDict({"train": dataset})
    return datasets.DatasetDict({"train": dataset})


def _iter_streaming_rows(
    client: EgoFlowClient,
    repository: RepositoryInfo,
    cache: CacheManager,
    *,
    page_size: int,
    download_mode: str,
    with_thumbnails: bool,
) -> Iterable[Dict[str, Any]]:
    for page in client.iter_manifest(repository.id, page_size=page_size):
        repo = page.repository if page.repository.id else repository
        for video in page.videos:
            video_path = cache.ensure_video(client, repo, video, download_mode=download_mode)
            thumbnail_path = None
            if with_thumbnails:
                thumbnail_path = cache.ensure_thumbnail(client, repo, video, download_mode=download_mode)
            yield _row_from_video(repo, video, video_path=video_path, thumbnail_path=thumbnail_path)


def load_dataset(
    path: str,
    *,
    split: Optional[str] = None,
    streaming: bool = False,
    cache_dir: Optional[Path] = None,
    download_mode: str = "reuse_cache_if_exists",
    decode: bool = False,
    with_thumbnails: bool = False,
    page_size: int = 200,
    token: Optional[str] = None,
    server_endpoint: Optional[str] = None,
    repo_id: Optional[str] = None,
    client: Optional[EgoFlowClient] = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    **config_kwargs: Any,
) -> Any:
    """Load an EgoFlow repository as a Hugging Face Datasets object.

    `path` is normally `owner/repository`. The current server supports Python
    token authentication on repository slug resolve, manifests, and downloads.
    """

    del config_kwargs
    _validate_split(split)
    _validate_download_mode(download_mode)
    _split_slug(path)
    ego_client = _client_from_args(
        client=client,
        token=token,
        server_endpoint=server_endpoint,
        timeout=timeout,
        max_retries=max_retries,
    )
    _check_dataset_capabilities(ego_client)
    repository = _resolve_or_stub_repository(ego_client, path, repo_id=repo_id)
    cache = CacheManager(
        Path(cache_dir).expanduser() if cache_dir is not None else None,
        api_base_url=ego_client.config.api_base_url,
    )

    if streaming:
        datasets = _require_datasets()

        def generator() -> Iterable[Dict[str, Any]]:
            yield from _iter_streaming_rows(
                ego_client,
                repository,
                cache,
                page_size=page_size,
                download_mode=download_mode,
                with_thumbnails=with_thumbnails,
            )

        iterable = datasets.IterableDataset.from_generator(generator)
        return _wrap_split(iterable, split, streaming=True)

    pages = _materialize_pages(ego_client, repository, page_size)
    if pages:
        repository = pages[0].repository
    rows: List[Dict[str, Any]] = []
    for page in pages:
        for video in page.videos:
            video_path = cache.ensure_video(ego_client, repository, video, download_mode=download_mode)
            thumbnail_path = None
            if with_thumbnails:
                thumbnail_path = cache.ensure_thumbnail(ego_client, repository, video, download_mode=download_mode)
            rows.append(_row_from_video(repository, video, video_path=video_path, thumbnail_path=thumbnail_path))
    cache.write_manifest(repository, pages)
    return _wrap_split(_make_hf_dataset(rows, decode=decode), split)
