import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow import (
    EgoFlowClient,
    FrameBatch,
    VideoFrame,
    __version__,
    filter_live_streams,
    list_live_streams,
    load_dataset,
    open_live_stream,
    open_video,
)


class ImportTestCase(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertEqual(__version__, "0.0.1")

    def test_public_api_exports(self) -> None:
        self.assertTrue(callable(load_dataset))
        self.assertTrue(callable(open_video))
        self.assertTrue(callable(filter_live_streams))
        self.assertTrue(callable(list_live_streams))
        self.assertTrue(callable(open_live_stream))
        self.assertIsNotNone(EgoFlowClient)
        self.assertIsNotNone(VideoFrame)
        self.assertIsNotNone(FrameBatch)


if __name__ == "__main__":
    unittest.main()
