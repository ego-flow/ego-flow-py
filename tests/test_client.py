import hashlib
import http.server
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.client import EgoFlowClient, UrllibTransport, _raise_for_http_error
from ego_flow.config import EgoFlowConfig
from ego_flow.errors import (
    EgoFlowAuthenticationError,
    EgoFlowBadRequestError,
    EgoFlowCapabilityError,
    EgoFlowConflictError,
    EgoFlowDownloadError,
    EgoFlowNotFoundError,
    EgoFlowPermissionError,
    EgoFlowServerError,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []
        self.download_calls = []
        self.responses = {}
        self.download_bytes = b""

    def request_json(self, method, url, *, headers, timeout):
        self.calls.append((method, url, dict(headers), timeout))
        response = self.responses.get((method, url))
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError("Unexpected request {}".format(url))
        return response

    def download(self, url, *, headers, destination, timeout, chunk_size=1024 * 1024):
        self.download_calls.append((url, dict(headers), destination, timeout))
        destination.write_bytes(self.download_bytes)


def make_client(transport: FakeTransport) -> EgoFlowClient:
    config = EgoFlowConfig.from_values(
        token="ef_0123456789abcdef",  # gitleaks:allow -- fake fixture
        server_endpoint="http://server.local",
    )
    return EgoFlowClient(config, transport=transport)


class ClientTestCase(unittest.TestCase):
    def test_http_statuses_map_to_specific_exception_types(self) -> None:
        mappings = [
            (400, EgoFlowBadRequestError),
            (401, EgoFlowAuthenticationError),
            (403, EgoFlowPermissionError),
            (404, EgoFlowNotFoundError),
            (409, EgoFlowConflictError),
            (500, EgoFlowServerError),
        ]

        for status, exception_type in mappings:
            with self.subTest(status=status):
                error = urllib.error.HTTPError(
                    "http://server.local/api/v1/resource",
                    status,
                    "HTTP failure",
                    {},
                    io.BytesIO(b'{"error":"LEGACY","message":"Request failed."}'),
                )
                with self.assertRaises(exception_type) as context:
                    _raise_for_http_error(error)
                self.assertEqual(context.exception.status_code, status)
                self.assertEqual(context.exception.error, "LEGACY")
                self.assertEqual(str(context.exception), "Request failed.")

    def test_malformed_error_body_falls_back_to_http_reason(self) -> None:
        error = urllib.error.HTTPError(
            "http://server.local/api/v1/resource",
            502,
            "Bad Gateway",
            {},
            io.BytesIO(b"not-json"),
        )

        with self.assertRaises(EgoFlowServerError) as context:
            _raise_for_http_error(error)

        self.assertEqual(str(context.exception), "Bad Gateway")
        self.assertIsNone(context.exception.error)
        self.assertIsNone(context.exception.details)

    def test_server_error_envelope_preserves_code_message_and_details(self) -> None:
        payload = {
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Invalid token.",
                "details": {"reason": "revoked"},
            }
        }
        error = urllib.error.HTTPError(
            "http://server.local/api/v1/auth/python/tokens/validate",
            401,
            "Unauthorized",
            {},
            io.BytesIO(json.dumps(payload).encode("utf-8")),
        )

        with self.assertRaises(EgoFlowAuthenticationError) as context:
            _raise_for_http_error(error)

        self.assertEqual(str(context.exception), "Invalid token.")
        self.assertEqual(context.exception.error, "UNAUTHORIZED")
        self.assertEqual(context.exception.details, {"reason": "revoked"})

    def test_resolve_repository_sends_auth_and_query(self) -> None:
        transport = FakeTransport()
        transport.responses[
            ("GET", "http://server.local/api/v1/repositories/resolve?slug=alice%2Fdaily")
        ] = {
            "repository": {
                "id": "repo",
                "name": "daily",
                "owner_id": "alice",
                "visibility": "private",
                "description": None,
                "tags": ["kitchen", "egocentric"],
                "my_role": "read",
                "created_at": "2026-04-24T00:00:00.000Z",
                "updated_at": "2026-04-24T00:00:00.000Z",
            }
        }
        repo = make_client(transport).resolve_repository("alice/daily")
        self.assertEqual(repo.slug, "alice/daily")
        self.assertEqual(repo.tags, ["kitchen", "egocentric"])
        self.assertEqual(transport.calls[0][2]["Authorization"], "Bearer ef_0123456789abcdef")

    def test_resolve_repository_401_remains_authentication_error(self) -> None:
        transport = FakeTransport()
        transport.responses[
            ("GET", "http://server.local/api/v1/repositories/resolve?slug=alice%2Fdaily")
        ] = EgoFlowAuthenticationError("Authentication is required.", status_code=401)
        with self.assertRaises(EgoFlowAuthenticationError):
            make_client(transport).resolve_repository("alice/daily")

    def test_manifest_iteration_stops_on_has_next_false(self) -> None:
        transport = FakeTransport()
        transport.responses[
            ("GET", "http://server.local/api/v1/repositories/repo/manifest?page=1&limit=200")
        ] = {
            "manifest_version": "1",
            "repository": {
                "id": "repo",
                "owner_id": "alice",
                "name": "daily",
                "visibility": "private",
                "my_role": "read",
            },
            "default_artifact": "vlm_video",
            "pagination": {"total": 0, "page": 1, "limit": 200, "has_next": False},
            "videos": [],
        }
        pages = list(make_client(transport).iter_manifest("repo"))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].repository.id, "repo")

    def test_download_artifact_verifies_sha256(self) -> None:
        transport = FakeTransport()
        transport.download_bytes = b"video-bytes"
        expected = hashlib.sha256(transport.download_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "video.mp4"
            make_client(transport).download_artifact(
                "/api/v1/repositories/repo/videos/video/download",
                path,
                expected_sha256=expected,
            )
            self.assertEqual(path.read_bytes(), b"video-bytes")
            self.assertEqual(
                transport.download_calls[0][0],
                "http://server.local/api/v1/repositories/repo/videos/video/download",
            )

    def test_download_artifact_removes_temp_file_on_hash_mismatch(self) -> None:
        transport = FakeTransport()
        transport.download_bytes = b"wrong-bytes"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "video.mp4"
            with self.assertRaises(EgoFlowDownloadError):
                make_client(transport).download_artifact(
                    "/api/v1/repositories/repo/videos/video/download",
                    path,
                    expected_sha256="0" * 64,
                )
            self.assertFalse(path.exists())
            self.assertFalse(path.with_name("video.mp4.tmp").exists())

    def test_download_artifact_rejects_empty_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(EgoFlowDownloadError):
                make_client(FakeTransport()).download_artifact("", Path(tmpdir) / "video.mp4")

    def test_external_artifact_url_does_not_receive_server_token(self) -> None:
        transport = FakeTransport()
        transport.download_bytes = b"video"

        with tempfile.TemporaryDirectory() as tmpdir:
            make_client(transport).download_artifact(
                "https://cdn.example.com/signed/video.mp4",
                Path(tmpdir) / "video.mp4",
            )

        self.assertNotIn("Authorization", transport.download_calls[0][1])

    def test_cross_origin_redirect_strips_server_token(self) -> None:
        received_authorization = []

        class ArtifactHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                received_authorization.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"video")

            def log_message(self, _format, *args) -> None:
                del args

        artifact_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ArtifactHandler)
        artifact_thread = threading.Thread(target=artifact_server.serve_forever, daemon=True)
        artifact_thread.start()

        artifact_url = "http://127.0.0.1:{}/video.mp4".format(artifact_server.server_port)

        class RedirectHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(307)
                self.send_header("Location", artifact_url)
                self.end_headers()

            def log_message(self, _format, *args) -> None:
                del args

        redirect_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        redirect_thread = threading.Thread(target=redirect_server.serve_forever, daemon=True)
        redirect_thread.start()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                UrllibTransport().download(
                    "http://127.0.0.1:{}/download".format(redirect_server.server_port),
                    headers={"Authorization": "Bearer ef_private"},
                    destination=Path(tmpdir) / "video.mp4",
                    timeout=5,
                )
        finally:
            redirect_server.shutdown()
            redirect_server.server_close()
            redirect_thread.join()
            artifact_server.shutdown()
            artifact_server.server_close()
            artifact_thread.join()

        self.assertEqual(received_authorization, [None])

    def test_bad_request_is_not_retried(self) -> None:
        transport = FakeTransport()
        transport.responses[
            ("GET", "http://server.local/api/v1/repositories/resolve?slug=bad")
        ] = EgoFlowBadRequestError("Invalid slug.", status_code=400)
        with self.assertRaises(EgoFlowBadRequestError):
            make_client(transport).resolve_repository("bad")
        self.assertEqual(len(transport.calls), 1)

    def test_transient_server_errors_retry_up_to_configured_limit(self) -> None:
        class FlakyTransport(FakeTransport):
            def request_json(self, method, url, *, headers, timeout):
                self.calls.append((method, url, dict(headers), timeout))
                if len(self.calls) < 3:
                    raise EgoFlowServerError("temporary")
                return {"status": "ok"}

        transport = FlakyTransport()

        with patch("ego_flow.client.time.sleep") as sleep:
            health = make_client(transport).health()

        self.assertEqual(health, {"status": "ok"})
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.25, 0.5])

    def test_failed_download_removes_temp_file_and_preserves_destination(self) -> None:
        class FailingDownloadTransport(FakeTransport):
            def download(self, url, *, headers, destination, timeout, chunk_size=1024 * 1024):
                del url, headers, timeout, chunk_size
                destination.write_bytes(b"partial")
                raise EgoFlowDownloadError("connection lost")

        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "video.mp4"
            destination.write_bytes(b"existing")

            with self.assertRaisesRegex(EgoFlowDownloadError, "connection lost"):
                make_client(FailingDownloadTransport()).download_artifact(
                    "/files/video.mp4",
                    destination,
                )

            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse(destination.with_name("video.mp4.tmp").exists())

    def test_same_origin_absolute_and_files_urls_receive_server_token(self) -> None:
        transport = FakeTransport()
        transport.download_bytes = b"video"

        with tempfile.TemporaryDirectory() as tmpdir:
            client = make_client(transport)
            client.download_artifact(
                "http://server.local/api/v1/files/first.mp4",
                Path(tmpdir) / "first.mp4",
            )
            client.download_artifact(
                "/files/second.mp4",
                Path(tmpdir) / "second.mp4",
            )

        self.assertEqual(
            [call[0] for call in transport.download_calls],
            [
                "http://server.local/api/v1/files/first.mp4",
                "http://server.local/files/second.mp4",
            ],
        )
        self.assertTrue(all("Authorization" in call[1] for call in transport.download_calls))

    def test_path_segments_are_encoded(self) -> None:
        transport = FakeTransport()
        transport.download_bytes = b"thumbnail"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "thumb.jpg"
            make_client(transport).download_thumbnail("repo/one", "video two", path)
        self.assertEqual(
            transport.download_calls[0][0],
            "http://server.local/api/v1/repositories/repo%2Fone/videos/video%20two/thumbnail",
        )

    def test_list_live_streams_uses_canonical_endpoint(self) -> None:
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
        streams = make_client(transport).list_live_streams()
        self.assertEqual(streams[0].recording_session_id, "rec")
        self.assertEqual(streams[0].stream_path, "live/daily/rec")
        self.assertTrue(streams[0].playback_available)
        self.assertEqual(transport.calls[0][0], "GET")

    def test_list_live_streams_parses_http_upload_progress(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/live-streams")] = {
            "streams": [
                {
                    "recording_session_id": "rec-http",
                    "repository_id": "repo",
                    "repository_name": "daily",
                    "user_id": "alice",
                    "device_type": "meta_glasses_android",
                    "ingest_type": "HTTP",
                    "stream_path": "live/daily/rec-http",
                    "status": "live",
                    "playback_available": False,
                    "bytes_received": 8192,
                    "last_sequence": 7,
                    "last_chunk_at": "2026-05-29T01:02:03.000Z",
                }
            ]
        }

        stream = make_client(transport).list_live_streams()[0]

        self.assertEqual(stream.bytes_received, 8192)
        self.assertEqual(stream.last_sequence, 7)
        self.assertEqual(stream.last_chunk_at, "2026-05-29T01:02:03.000Z")

    def test_build_live_hls_url_uses_fixed_direct_port(self) -> None:
        client = make_client(FakeTransport())
        self.assertEqual(
            client.build_live_hls_url("live/daily/rec", "pt_hls"),
            "http://server.local:8888/live/daily/rec/index.m3u8?ticket=pt_hls",
        )

    def test_build_live_hls_url_encodes_ticket_and_supports_ipv6(self) -> None:
        config = EgoFlowConfig.from_values(
            token="ef_0123456789abcdef",  # gitleaks:allow -- fake fixture
            server_endpoint="https://[2001:db8::1]:8443",
        )
        client = EgoFlowClient(config, transport=FakeTransport())

        self.assertEqual(
            client.build_live_hls_url("/live/camera one/rec/", "ticket + slash/"),
            "http://[2001:db8::1]:8888/live/camera%20one/rec/index.m3u8?ticket=ticket+%2B+slash%2F",
        )

        with self.assertRaisesRegex(EgoFlowServerError, "stream_path"):
            client.build_live_hls_url("///", "ticket")

    def test_get_live_stream_detail_parses_nullable_http_progress(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/live-streams/rec")] = {
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

        stream = make_client(transport).get_live_stream_detail("rec")

        self.assertEqual(stream.ingest_type, "HTTP")
        self.assertEqual(stream.bytes_received, 8192)
        self.assertEqual(stream.last_sequence, 7)
        self.assertEqual(stream.last_chunk_at, "2026-04-24T00:01:00.000Z")

    def test_python_token_validate_and_playback_ticket_helpers(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/auth/python/tokens/validate")] = {
            "valid": True,
            "user": {"id": "viewer-1", "role": "user", "display_name": "Viewer"},
        }
        transport.responses[("POST", "http://server.local/api/v1/live-streams/rec/playback-ticket")] = {
            "playback_ticket": "pt_hls",
        }
        client = make_client(transport)

        self.assertEqual(client.python_user_id(), "viewer-1")
        self.assertEqual(client.python_user_id(), "viewer-1")
        self.assertEqual(client.issue_live_stream_playback_ticket("rec"), "pt_hls")
        self.assertEqual(
            [call[0:2] for call in transport.calls],
            [
                ("GET", "http://server.local/api/v1/auth/python/tokens/validate"),
                ("POST", "http://server.local/api/v1/live-streams/rec/playback-ticket"),
            ],
        )

    def test_missing_user_and_playback_ticket_fields_raise_server_errors(self) -> None:
        transport = FakeTransport()
        transport.responses[("GET", "http://server.local/api/v1/auth/python/tokens/validate")] = {
            "valid": True,
            "user": {},
        }
        transport.responses[("POST", "http://server.local/api/v1/live-streams/rec/playback-ticket")] = {}
        client = make_client(transport)

        with self.assertRaisesRegex(EgoFlowServerError, "user.id"):
            client.python_user_id()
        with self.assertRaisesRegex(EgoFlowServerError, "playback_ticket"):
            client.issue_live_stream_playback_ticket("rec")

    def test_list_repositories_is_not_a_python_token_endpoint(self) -> None:
        transport = FakeTransport()
        with self.assertRaises(EgoFlowCapabilityError):
            make_client(transport).list_repositories()
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
