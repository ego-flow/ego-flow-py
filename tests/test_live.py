import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.client import EgoFlowClient
from ego_flow.config import EgoFlowConfig
from ego_flow.errors import EgoFlowCapabilityError, EgoFlowNotFoundError, EgoFlowStreamError
from ego_flow.live import LiveStream, filter_live_streams, list_live_streams, open_live_stream
from ego_flow.models import LiveStreamInfo


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []
        self.responses = {}

    def request_json(self, method, url, *, headers, timeout):
        self.calls.append((method, url, dict(headers), timeout))
        response = self.responses.get((method, url))
        if response is None:
            raise AssertionError("Unexpected request {}".format(url))
        return response


def make_client(transport: FakeTransport) -> EgoFlowClient:
    config = EgoFlowConfig.from_values(
        token="ef_0123456789abcdef",  # gitleaks:allow -- fake fixture
        server_endpoint="http://server.local",
    )
    return EgoFlowClient(config, transport=transport)


class LiveTestCase(unittest.TestCase):
    def test_open_live_stream_uses_playback_ticket_direct_hls_url(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/live-streams")] = {
            "streams": [
                {
                    "recording_session_id": "rec",
                    "repository_id": "repo",
                    "repository_name": "daily",
                    "user_id": "alice",
                    "device_type": None,
                    "ingest_type": "MEDIAMTX",
                    "stream_path": "live/daily/rec",
                    "status": "live",
                    "playback_available": True,
                }
            ]
        }
        transport.responses[("GET", "http://server.local/api/v1/live-streams/rec")] = {
            "recording_session_id": "rec",
            "repository_id": "repo",
            "repository_name": "daily",
            "owner_id": "alice",
            "user_id": "alice",
            "device_type": None,
            "ingest_type": "MEDIAMTX",
            "stream_path": "live/daily/rec",
            "registered_at": "2026-04-24T00:00:00.000Z",
            "status": "live",
            "playback_available": True,
            "playback_ready": True,
            "bytes_received": None,
            "last_sequence": None,
            "last_chunk_at": None,
        }
        transport.responses[("POST", "http://server.local/api/v1/live-streams/rec/playback-ticket")] = {
            "playback_ticket": "pt_hls",
        }

        stream = open_live_stream("live/daily/rec", client=make_client(transport), check_capability=False)

        self.assertEqual(
            stream.source,
            "http://server.local:8888/live/daily/rec/index.m3u8?ticket=pt_hls",
        )
        self.assertEqual(stream.headers, {})
        self.assertEqual(stream.metadata["stream_path"], "live/daily/rec")
        self.assertEqual(stream.metadata["recording_session_id"], "rec")
        self.assertNotIn(
            ("GET", "http://server.local/api/v1/auth/python/tokens/validate"),
            [(method, url) for method, url, _headers, _body in transport.calls],
        )

    def test_live_stream_rejects_http_upload_streams(self) -> None:
        transport = FakeTransport()
        stream_info = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "owner_id": "alice",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "HTTP",
                "registered_at": "2026-04-24T00:00:00.000Z",
                "status": "live",
                "stream_path": "live/daily/rec",
                "playback_available": False,
                "playback_ready": False,
            }
        )

        with self.assertRaises(EgoFlowStreamError):
            LiveStream(stream_info, client=make_client(transport))

    def test_live_stream_rejects_not_ready_playback(self) -> None:
        stream_info = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "owner_id": "alice",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "MEDIAMTX",
                "registered_at": "2026-04-24T00:00:00.000Z",
                "status": "live",
                "stream_path": "live/daily/rec",
                "playback_available": True,
                "playback_ready": False,
            }
        )

        with self.assertRaises(EgoFlowStreamError):
            LiveStream(stream_info, client=make_client(FakeTransport()))

    def test_filter_live_streams_filters_client_side(self) -> None:
        mediamtx_stream = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rtmp-rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "MEDIAMTX",
                "stream_path": "live/daily/rtmp-rec",
                "status": "live",
                "playback_available": True,
            }
        )
        http_stream = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "http-rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "HTTP",
                "stream_path": "live/daily/http-rec",
                "status": "live",
                "playback_available": False,
            }
        )

        self.assertEqual(filter_live_streams([mediamtx_stream, http_stream], ingest_type="MEDIAMTX"), [mediamtx_stream])
        self.assertEqual(filter_live_streams([mediamtx_stream, http_stream], playback_available=False), [http_stream])
        self.assertEqual(
            filter_live_streams(
                [mediamtx_stream, http_stream],
                repository_id="repo",
                repository_name="daily",
            ),
            [mediamtx_stream, http_stream],
        )
        self.assertEqual(filter_live_streams([mediamtx_stream], repository_name="other"), [])

    def test_list_live_streams_rejects_server_without_capability(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/info")] = {
            "api_version": "v1",
            "server_version": "0.0.1",
            "capabilities": {
                "dataset_manifest": True,
                "video_download": True,
                "thumbnail_download": True,
                "live_streams": False,
                "python_tokens": True,
            },
        }

        with self.assertRaisesRegex(EgoFlowCapabilityError, "live_streams=false"):
            list_live_streams(client=make_client(transport))

        self.assertEqual([call[1] for call in transport.calls], ["http://server.local/api/v1/info"])

    def test_open_live_stream_reports_empty_and_ambiguous_lists(self) -> None:
        transport = FakeTransport()
        endpoint = ("GET", "http://server.local/api/v1/live-streams")
        transport.responses[endpoint] = {"streams": []}

        with self.assertRaises(EgoFlowNotFoundError):
            open_live_stream(client=make_client(transport), check_capability=False)

        stream = {
            "repository_id": "repo",
            "repository_name": "daily",
            "user_id": "alice",
            "device_type": None,
            "ingest_type": "MEDIAMTX",
            "status": "live",
            "playback_available": True,
        }
        transport.responses[endpoint] = {
            "streams": [
                dict(stream, recording_session_id="first", stream_path="live/daily/first"),
                dict(stream, recording_session_id="second", stream_path="live/daily/second"),
            ]
        }

        with self.assertRaisesRegex(ValueError, "Multiple live streams"):
            open_live_stream(client=make_client(transport), check_capability=False)

    def test_live_stream_requires_stream_path_after_detail_is_ready(self) -> None:
        stream_info = LiveStreamInfo.from_dict(
            {
                "recording_session_id": "rec",
                "repository_id": "repo",
                "repository_name": "daily",
                "owner_id": "alice",
                "user_id": "alice",
                "device_type": None,
                "ingest_type": "MEDIAMTX",
                "stream_path": None,
                "status": "live",
                "playback_available": True,
                "playback_ready": True,
            }
        )

        with self.assertRaisesRegex(EgoFlowStreamError, "stream_path"):
            LiveStream(stream_info, client=make_client(FakeTransport()))


if __name__ == "__main__":
    unittest.main()
