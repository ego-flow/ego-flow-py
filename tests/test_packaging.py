import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


class PackagingTestCase(unittest.TestCase):
    def test_build_metadata_uses_the_runtime_version_source(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib is not available on this Python version")

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))

        self.assertNotIn("version", metadata["project"])
        self.assertIn("version", metadata["project"]["dynamic"])
        self.assertEqual(
            metadata["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "ego_flow._version.__version__",
        )

    def test_release_metadata_and_files_are_present(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib is not available on this Python version")

        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["license"], "MIT")
        self.assertEqual(metadata["project"]["license-files"], ["LICENSE"])
        self.assertEqual(
            metadata["project"]["urls"]["Repository"],
            "https://github.com/ego-flow/ego-flow-py",
        )
        self.assertTrue((root / "LICENSE").is_file())
        self.assertTrue((root / "CHANGELOG.md").is_file())
        self.assertTrue((root / "CODE_OF_CONDUCT.md").is_file())
        self.assertTrue((root / "CONTRIBUTING.md").is_file())

        manifest_entries = (root / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        self.assertIn("include CHANGELOG.md", manifest_entries)
        self.assertIn("include CODE_OF_CONDUCT.md", manifest_entries)
        self.assertIn("include CONTRIBUTING.md", manifest_entries)

        self.assertEqual(
            metadata["project"]["urls"]["Code of Conduct"],
            "https://github.com/ego-flow/ego-flow-py/blob/main/CODE_OF_CONDUCT.md",
        )
        self.assertEqual(
            metadata["project"]["urls"]["Contributing"],
            "https://github.com/ego-flow/ego-flow-py/blob/main/CONTRIBUTING.md",
        )

        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("[Code of Conduct](./CODE_OF_CONDUCT.md)", readme)
        self.assertIn("[Contributing guide](./CONTRIBUTING.md)", readme)
        self.assertIn("[MIT License](./LICENSE)", readme)

    def test_default_install_includes_video_and_torch_dependencies(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib is not available on this Python version")

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        dependencies = metadata["project"]["dependencies"]
        optional_dependencies = metadata["project"].get("optional-dependencies", {})

        self.assertIn("av>=12.0", dependencies)
        self.assertIn("numpy>=1.23", dependencies)
        self.assertIn("torch>=2.0", dependencies)
        self.assertNotIn("video", optional_dependencies)
        self.assertNotIn("torch", optional_dependencies)


if __name__ == "__main__":
    unittest.main()
