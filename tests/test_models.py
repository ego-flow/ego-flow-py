import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.models import LiveStreamInfo, ManifestPage, RepositoryInfo, ServerInfo


class ModelsTestCase(unittest.TestCase):
    def test_server_info_parses_capabilities(self) -> None:
        info = ServerInfo.from_dict(
            {
                "api_version": "v1",
                "server_version": "0.1.0",
                "capabilities": {
                    "dataset_manifest": True,
                    "video_download": True,
                    "thumbnail_download": True,
                    "live_streams": False,
                    "python_tokens": True,
                },
            }
        )
        self.assertTrue(info.capabilities.dataset_manifest)
        self.assertFalse(info.capabilities.live_streams)

    def test_manifest_page_parses_video_artifacts(self) -> None:
        page = ManifestPage.from_dict(
            {
                "manifest_version": "1",
                "repository": {
                    "id": "repo-1",
                    "owner_id": "alice",
                    "name": "daily_kitchen",
                    "visibility": "private",
                    "my_role": "read",
                },
                "default_artifact": "vlm_video",
                "pagination": {"total": 1, "page": 1, "limit": 200, "has_next": False},
                "videos": [
                    {
                        "video_id": "video-1",
                        "recorded_at": None,
                        "duration_sec": 1.5,
                        "resolution_width": 640,
                        "resolution_height": 480,
                        "fps": 30,
                        "codec": "h264",
                        "scene_summary": "kitchen",
                        "clip_segments": [{"start": 0, "end": 1}],
                        "artifacts": {
                            "vlm_video": {
                                "download_url": "/api/v1/repositories/repo-1/videos/video-1/download",
                                "size_bytes": 10,
                                "sha256": "abc",
                                "content_type": "video/mp4",
                            },
                            "thumbnail": {
                                "download_url": "/api/v1/repositories/repo-1/videos/video-1/thumbnail",
                                "content_type": "image/jpeg",
                            },
                        },
                    }
                ],
            }
        )
        self.assertEqual(page.repository.slug, "alice/daily_kitchen")
        self.assertEqual(page.videos[0].artifact.content_type, "video/mp4")
        self.assertIsNotNone(page.videos[0].thumbnail)
        self.assertEqual(page.videos[0].semantic_metadata, {})

    def test_repository_info_parses_tags_from_resolve_response(self) -> None:
        repository = RepositoryInfo.from_dict(
            {
                "id": "repo",
                "owner_id": "alice",
                "name": "daily",
                "visibility": "private",
                "description": None,
                "tags": ["kitchen", "egocentric"],
                "my_role": "read",
                "created_at": "2026-04-24T00:00:00.000Z",
                "updated_at": "2026-04-24T00:00:00.000Z",
            }
        )

        self.assertEqual(repository.tags, ["kitchen", "egocentric"])

    def test_live_stream_info_parses_current_live_shape(self) -> None:
        stream = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "owner_id": "alice",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "HTTP",
                "stream_path": "live/daily/rec",
                "registered_at": "2026-04-24T00:00:00.000Z",
                "status": "live",
                "playback_available": False,
                "playback_ready": False,
                "bytes_received": 8192,
                "last_sequence": 7,
                "last_chunk_at": "2026-04-24T00:01:00.000Z",
            }
        )
        self.assertEqual(stream.recording_session_id, "rec")
        self.assertEqual(stream.ingest_type, "HTTP")
        self.assertFalse(stream.playback_available)
        self.assertEqual(stream.bytes_received, 8192)
        self.assertEqual(stream.last_sequence, 7)

    def test_live_stream_info_does_not_fallback_stream_path(self) -> None:
        stream = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "MEDIAMTX",
                "status": "live",
                "playback_available": True,
            }
        )

        self.assertIsNone(stream.stream_path)


if __name__ == "__main__":
    unittest.main()
