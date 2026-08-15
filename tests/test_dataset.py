import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.dataset import load_dataset
from ego_flow.errors import EgoFlowCapabilityError
from ego_flow.models import ManifestPage, RepositoryInfo


class FakeDataset:
    def __init__(self, rows):
        self.rows = rows

    def cast_column(self, _name, _feature):
        return self


class FakeIterableDataset:
    def __init__(self, generator):
        self.generator = generator

    def __iter__(self):
        return iter(self.generator())


class FakeDatasetsModule:
    class Dataset:
        @classmethod
        def from_list(cls, rows):
            return FakeDataset(rows)

    class Video:
        def __init__(self, *, decode):
            self.decode = decode

    class IterableDataset:
        @classmethod
        def from_generator(cls, generator):
            return FakeIterableDataset(generator)

    class DatasetDict(dict):
        pass

    class IterableDatasetDict(dict):
        pass


class FakeClient:
    def __init__(self) -> None:
        self.config = types.SimpleNamespace(api_base_url="http://server.local/api/v1")
        self.resolve_calls = []
        self.download_calls = []

    def info(self):
        capabilities = types.SimpleNamespace(
            python_tokens=True,
            dataset_manifest=True,
            video_download=True,
        )
        return types.SimpleNamespace(capabilities=capabilities)

    def resolve_repository(self, path):
        self.resolve_calls.append(path)
        return RepositoryInfo(id="repo", owner_id="alice", name="daily")

    def iter_manifest(self, _repo_id, *, page_size):
        del page_size
        yield ManifestPage.from_dict(
            {
                "manifest_version": "1",
                "repository": {
                    "id": "repo",
                    "owner_id": "alice",
                    "name": "daily",
                    "visibility": "private",
                    "my_role": "read",
                },
                "default_artifact": "vlm_video",
                "pagination": {"total": 1, "page": 1, "limit": 200, "has_next": False},
                "videos": [
                    {
                        "video_id": "video",
                        "recorded_at": None,
                        "duration_sec": 1.0,
                        "resolution_width": 640,
                        "resolution_height": 480,
                        "fps": 30,
                        "codec": "h264",
                        "scene_summary": None,
                        "clip_segments": None,
                        "artifacts": {
                            "vlm_video": {
                                "download_url": "/api/v1/repositories/repo/videos/video/download",
                                "size_bytes": 5,
                                "sha256": None,
                                "content_type": "video/mp4",
                            },
                            "thumbnail": None,
                        },
                    }
                ],
            }
        )

    def download_video(self, _repo_id, _video_id, destination, *, expected_sha256=None, download_url=None):
        del expected_sha256, download_url
        self.download_calls.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        return destination


class DatasetTestCase(unittest.TestCase):
    def test_invalid_path_split_and_download_mode_fail_before_server_calls(self) -> None:
        client = FakeClient()

        with self.assertRaisesRegex(ValueError, "owner/repository"):
            load_dataset("invalid", split="train", client=client)
        with self.assertRaisesRegex(ValueError, "only the 'train' split"):
            load_dataset("alice/daily", split="validation", client=client)
        with self.assertRaisesRegex(ValueError, "download_mode"):
            load_dataset("alice/daily", split="train", download_mode="never", client=client)

        self.assertEqual(client.resolve_calls, [])

    def test_missing_server_capabilities_report_the_specific_requirement(self) -> None:
        capability_names = ["python_tokens", "dataset_manifest", "video_download"]

        for missing in capability_names:
            with self.subTest(missing=missing):
                client = FakeClient()

                def info():
                    values = {name: name != missing for name in capability_names}
                    return types.SimpleNamespace(capabilities=types.SimpleNamespace(**values))

                client.info = info
                with self.assertRaises(EgoFlowCapabilityError) as context:
                    load_dataset("alice/daily", split="train", client=client)
                self.assertIn(missing.replace("_", " ").split()[0], str(context.exception).lower())

    def test_load_dataset_materializes_rows_with_fake_datasets_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(sys.modules, {"datasets": FakeDatasetsModule()}):
                dataset = load_dataset(
                    "alice/daily",
                    split="train",
                    cache_dir=Path(tmpdir),
                    client=FakeClient(),
                )

        self.assertEqual(len(dataset.rows), 1)
        self.assertEqual(dataset.rows[0]["video_id"], "video")
        self.assertEqual(dataset.rows[0]["repository_id"], "repo")
        self.assertEqual(dataset.rows[0]["semantic_metadata"], {})

    def test_repo_id_skips_slug_resolution(self) -> None:
        client = FakeClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(sys.modules, {"datasets": FakeDatasetsModule()}):
                dataset = load_dataset(
                    "alice/daily",
                    split="train",
                    repo_id="repo",
                    cache_dir=Path(tmpdir),
                    client=client,
                )

        self.assertEqual(client.resolve_calls, [])
        self.assertEqual(dataset.rows[0]["repository_id"], "repo")

    def test_streaming_dataset_defers_download_until_iteration(self) -> None:
        client = FakeClient()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(sys.modules, {"datasets": FakeDatasetsModule()}):
                dataset = load_dataset(
                    "alice/daily",
                    split="train",
                    streaming=True,
                    cache_dir=Path(tmpdir),
                    client=client,
                )
                self.assertEqual(client.download_calls, [])
                rows = list(dataset)

        self.assertEqual(len(client.download_calls), 1)
        self.assertEqual(rows[0]["video_id"], "video")

    def test_unspecified_split_returns_train_dataset_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(sys.modules, {"datasets": FakeDatasetsModule()}):
                datasets = load_dataset(
                    "alice/daily",
                    cache_dir=Path(tmpdir),
                    client=FakeClient(),
                )

        self.assertEqual(list(datasets), ["train"])
        self.assertEqual(datasets["train"].rows[0]["video_id"], "video")


if __name__ == "__main__":
    unittest.main()
