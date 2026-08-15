import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.video import PyAVVideoSource, RepositoryVideoSource, _frame_to_data, ensure_batches, open_video


class FakeFrame:
    def __init__(self, time, value):
        self.time = time
        self.value = value


class FakeContainer:
    def __init__(self, frames):
        self.streams = [SimpleNamespace(type="video")]
        self.frames = frames
        self.closed = False

    def decode(self, _stream):
        yield from self.frames

    def close(self):
        self.closed = True


class VideoTestCase(unittest.TestCase):
    def test_zero_frame_limit_does_not_decode_or_emit_frames(self) -> None:
        container = FakeContainer([FakeFrame(0.0, "first")])
        opened = []

        def open_container(_source, options):
            opened.append(options)
            return container

        fake_av = SimpleNamespace(open=open_container)
        source = PyAVVideoSource(
            "video.mp4",
            source_type="repository",
            source_id="video",
            format="native",
        )

        with patch("ego_flow.video._require_av", return_value=fake_av):
            frames = list(source.iter_frames(limit=0))

        self.assertEqual(frames, [])
        self.assertEqual(opened, [])

    def test_frame_iteration_applies_time_window_fps_and_closes_container(self) -> None:
        container = FakeContainer(
            [
                FakeFrame(0.0, "before"),
                FakeFrame(0.1, "first"),
                FakeFrame(0.4, "too-close"),
                FakeFrame(0.7, "second"),
                FakeFrame(1.1, "after"),
            ]
        )
        fake_av = SimpleNamespace(open=lambda _source, options: container)
        source = PyAVVideoSource(
            "video.mp4",
            source_type="repository",
            source_id="video",
            metadata={"repository_id": "repo"},
            format="native",
        )

        with patch("ego_flow.video._require_av", return_value=fake_av):
            frames = list(source.iter_frames(fps=2, start_seconds=0.05, end_seconds=1.0))

        self.assertEqual([frame.data.value for frame in frames], ["first", "second"])
        self.assertEqual([frame.index for frame in frames], [1, 3])
        self.assertEqual(frames[0].metadata, {"repository_id": "repo"})
        self.assertTrue(container.closed)

    def test_frame_limit_closes_container_after_requested_count(self) -> None:
        container = FakeContainer([FakeFrame(0.0, "first"), FakeFrame(1.0, "second")])
        fake_av = SimpleNamespace(open=lambda _source, options: container)
        source = PyAVVideoSource(
            "video.mp4",
            source_type="repository",
            source_id="video",
            format="native",
        )

        with patch("ego_flow.video._require_av", return_value=fake_av):
            frames = list(source.iter_frames(limit=1))

        self.assertEqual([frame.data.value for frame in frames], ["first"])
        self.assertTrue(container.closed)

    def test_frame_iteration_without_video_stream_closes_container(self) -> None:
        container = FakeContainer([])
        container.streams = [SimpleNamespace(type="audio")]
        fake_av = SimpleNamespace(open=lambda _source, options: container)
        source = PyAVVideoSource(
            "audio-only.mp4",
            source_type="repository",
            source_id="video",
            format="native",
        )

        with patch("ego_flow.video._require_av", return_value=fake_av):
            frames = list(source.iter_frames())

        self.assertEqual(frames, [])
        self.assertTrue(container.closed)

    def test_native_batches_include_full_and_partial_batch(self) -> None:
        container = FakeContainer(
            [FakeFrame(0.0, "first"), FakeFrame(1.0, "second"), FakeFrame(2.0, "third")]
        )
        fake_av = SimpleNamespace(open=lambda _source, options: container)
        source = PyAVVideoSource(
            "video.mp4",
            source_type="repository",
            source_id="video",
            format="native",
        )

        with patch("ego_flow.video._require_av", return_value=fake_av):
            batches = list(ensure_batches(source, batch_size=2))

        self.assertEqual([[frame.value for frame in batch.data] for batch in batches], [["first", "second"], ["third"]])
        self.assertEqual([batch.pts_seconds for batch in batches], [[0.0, 1.0], [2.0]])

    def test_batches_reject_non_positive_batch_size(self) -> None:
        source = PyAVVideoSource(
            "video.mp4",
            source_type="repository",
            source_id="video",
            format="native",
        )

        with self.assertRaisesRegex(ValueError, "batch_size must be positive"):
            list(source.iter_batches(batch_size=0))

    def test_frame_conversion_rejects_unknown_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "format must be one of"):
            _frame_to_data(FakeFrame(0.0, "frame"), "unknown")

    def test_video_source_rejects_unknown_format_at_construction(self) -> None:
        with self.assertRaisesRegex(ValueError, "format must be one of"):
            PyAVVideoSource(
                "video.mp4",
                source_type="repository",
                source_id="video",
                format="unknown",
            )

    def test_open_video_accepts_dataset_row(self) -> None:
        source = open_video(
            {
                "video_id": "video",
                "video_path": "/tmp/video.mp4",
                "repository_id": "repo",
            },
            format="numpy",
        )

        self.assertIsInstance(source, RepositoryVideoSource)
        self.assertEqual(source.source, "/tmp/video.mp4")
        self.assertEqual(source.source_id, "video")
        self.assertEqual(source.metadata["repository_id"], "repo")
        self.assertEqual(source.format, "numpy")

    def test_open_video_accepts_hf_video_cell_shape(self) -> None:
        source = open_video({"video_id": "video", "video": {"path": "/tmp/video.mp4"}})

        self.assertEqual(source.source, "/tmp/video.mp4")
        self.assertEqual(source.source_id, "video")

    def test_open_video_accepts_hf_filename_and_rejects_missing_path(self) -> None:
        source = open_video({"video": {"filename": "/tmp/fallback.mp4"}})

        self.assertEqual(source.source, "/tmp/fallback.mp4")
        self.assertEqual(source.source_id, "fallback")

        with self.assertRaisesRegex(ValueError, "requires a dataset row"):
            open_video({"video_id": "missing"})


if __name__ == "__main__":
    unittest.main()
