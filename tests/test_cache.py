import hashlib
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.cache import CacheManager
from ego_flow.models import ManifestPage, ManifestVideo, RepositoryInfo, ThumbnailArtifact, VideoArtifact


class FakeDownloadClient:
    def __init__(self) -> None:
        self.calls = []
        self.thumbnail_calls = []

    def download_video(self, repo_id, video_id, path, *, expected_sha256=None, download_url=None):
        self.calls.append((repo_id, video_id, path, expected_sha256, download_url))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"downloaded")
        return path

    def download_thumbnail(self, repo_id, video_id, path, *, download_url=None):
        self.thumbnail_calls.append((repo_id, video_id, path, download_url))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"thumbnail")
        return path


def make_repository() -> RepositoryInfo:
    return RepositoryInfo(id="repo", owner_id="alice", name="daily")


def make_video(content: bytes = b"video") -> ManifestVideo:
    return ManifestVideo(
        video_id="video",
        recorded_at=None,
        duration_sec=None,
        resolution_width=None,
        resolution_height=None,
        fps=None,
        codec=None,
        scene_summary=None,
        clip_segments=None,
        semantic_metadata={},
        artifact=VideoArtifact(
            download_url="/api/v1/repositories/repo/videos/video/download",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_type="video/mp4",
        ),
        thumbnail=None,
    )


class CacheTestCase(unittest.TestCase):
    def test_ensure_video_reuses_valid_cached_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir), api_base_url="http://server.local:3000/api/v1")
            repository = make_repository()
            video = make_video()
            cached_path = cache.video_path(repository, video)
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            cached_path.write_bytes(b"video")
            client = FakeDownloadClient()

            path = cache.ensure_video(client, repository, video)

            self.assertEqual(path, cached_path)
            self.assertEqual(client.calls, [])

    def test_ensure_video_downloads_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir), api_base_url="http://server.local:3000/api/v1")
            repository = make_repository()
            video = make_video()
            client = FakeDownloadClient()

            path = cache.ensure_video(client, repository, video)

            self.assertTrue(path.exists())
            self.assertEqual(client.calls[0][0], "repo")
            self.assertEqual(client.calls[0][1], "video")
            self.assertEqual(client.calls[0][4], "/api/v1/repositories/repo/videos/video/download")

    def test_invalid_cached_video_and_force_mode_trigger_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir), api_base_url="http://server.local:3000/api/v1")
            repository = make_repository()
            video = make_video()
            cached_path = cache.video_path(repository, video)
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            cached_path.write_bytes(b"corrupt")
            client = FakeDownloadClient()

            cache.ensure_video(client, repository, video)
            cache.ensure_video(client, repository, video, download_mode="force_redownload")

            self.assertEqual(len(client.calls), 2)

    def test_thumbnail_absence_reuse_and_force_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir), api_base_url="http://server.local:3000/api/v1")
            repository = make_repository()
            client = FakeDownloadClient()

            self.assertIsNone(cache.ensure_thumbnail(client, repository, make_video()))

            video = replace(
                make_video(),
                thumbnail=ThumbnailArtifact(
                    download_url="/api/v1/repositories/repo/videos/video/thumbnail",
                    content_type="image/jpeg",
                ),
            )
            thumbnail_path = cache.thumbnail_path(repository, video)
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail_path.write_bytes(b"cached")

            self.assertEqual(cache.ensure_thumbnail(client, repository, video), thumbnail_path)
            self.assertEqual(client.thumbnail_calls, [])

            cache.ensure_thumbnail(client, repository, video, download_mode="force_redownload")
            self.assertEqual(len(client.thumbnail_calls), 1)
            self.assertEqual(client.thumbnail_calls[0][3], video.thumbnail.download_url)

    def test_manifest_write_preserves_typed_page_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir), api_base_url="http://server.local:3000/api/v1")
            repository = make_repository()
            page = ManifestPage.from_dict(
                {
                    "manifest_version": "1",
                    "repository": {"id": "repo", "owner_id": "alice", "name": "daily"},
                    "default_artifact": "vlm_video",
                    "pagination": {"total": 0, "page": 1, "limit": 10, "has_next": False},
                    "videos": [],
                }
            )

            cache.write_manifest(repository, [page, {"extra": True}])

            payload = cache.manifest_path(repository).read_text(encoding="utf-8")
            self.assertIn('"manifest_version": "1"', payload)
            self.assertIn('"extra": true', payload)

    def test_cache_paths_sanitize_repository_and_video_identifiers(self) -> None:
        cache = CacheManager(Path("/tmp/cache"), api_base_url="https://server.local/api/v1")
        repository = RepositoryInfo(id="repo", owner_id="../alice", name="daily / kitchen")
        video = replace(make_video(), video_id="../video one")

        path = cache.video_path(repository, video)

        self.assertNotIn("..", path.relative_to(cache.root).parts)
        self.assertEqual(path.name.split("-")[0], ".._video_one")


if __name__ == "__main__":
    unittest.main()
