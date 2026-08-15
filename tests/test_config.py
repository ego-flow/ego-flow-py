import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ego_flow.config import EgoFlowConfig, build_api_base_url
from ego_flow.errors import EgoFlowConfigError


class ConfigTestCase(unittest.TestCase):
    def test_build_api_base_url_adds_scheme_and_api_path(self) -> None:
        self.assertEqual(
            build_api_base_url("127.0.0.1"),
            "http://127.0.0.1/api/v1",
        )

    def test_build_api_base_url_does_not_duplicate_api_path(self) -> None:
        self.assertEqual(
            build_api_base_url("https://example.com:8443/api/v1"),
            "https://example.com:8443/api/v1",
        )

    def test_build_api_base_url_rejects_invalid_endpoint(self) -> None:
        with self.assertRaises(EgoFlowConfigError):
            build_api_base_url("https://example.com:bad")

    def test_from_env_reads_expected_variables(self) -> None:
        config = EgoFlowConfig.from_env(
            {
                "EF_TOKEN": "ef_0123456789abcdef",  # gitleaks:allow -- fake fixture
                "EF_SERVER_ENDPOINT": "localhost",
            }
        )
        self.assertEqual(config.api_base_url, "http://localhost/api/v1")
        self.assertEqual(config.user_agent, "ego-flow-python/0.0.1")
        self.assertIn("Authorization", config.auth_headers())

    def test_missing_env_is_clear(self) -> None:
        with self.assertRaises(EgoFlowConfigError):
            EgoFlowConfig.from_env({})

    def test_repr_redacts_token(self) -> None:
        config = EgoFlowConfig.from_values(
            token="ef_0123456789abcdef",  # gitleaks:allow -- fake fixture
            server_endpoint="localhost",
        )
        self.assertNotIn("0123456789abcdef", repr(config))
        self.assertIn("ef_0...cdef", repr(config))


if __name__ == "__main__":
    unittest.main()
