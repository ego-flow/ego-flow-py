#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import urllib.request
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path


PACKAGE_NAME = "ego-flow"
PACKAGE_VERSION = "0.0.1"
PYPI_API = f"https://pypi.org/pypi/{PACKAGE_NAME}/{PACKAGE_VERSION}/json"
EXPECTED_ARTIFACTS = {
    "ego_flow-0.0.1-py3-none-any.whl": (
        "bdist_wheel",
        "32972180747908a54e9088569f62d5ea188a5f4d5274c7e51aae8092fd94ca10",
    ),
    "ego_flow-0.0.1.tar.gz": (
        "sdist",
        "68e8e4d5f7f90baeaff11a4c1135cdef6ba3ac85d807fd8ea353705f84fad392",
    ),
}
EXPECTED_RUNTIME_REQUIREMENTS = {
    "av>=12.0",
    "datasets>=2.19",
    "numpy>=1.23",
    "platformdirs>=4.0",
    "torch>=2.0",
}
USER_AGENT = "ego-flow-py-sbom-generator/1"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_parts(requirement: str) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)(.*)", requirement)
    if not match:
        raise ValueError(f"Unsupported dependency specifier: {requirement}")
    return normalize_name(match.group(1)), match.group(2)


def main() -> int:
    output_path = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "sbom.cdx.json"
    )

    release = json.loads(fetch(PYPI_API))
    info = release["info"]
    if normalize_name(info["name"]) != PACKAGE_NAME or info["version"] != PACKAGE_VERSION:
        raise ValueError("PyPI returned an unexpected project identity")

    artifact_entries = {item["filename"]: item for item in release["urls"]}
    verified_artifacts: list[tuple[dict[str, object], bytes]] = []
    for filename, (package_type, expected_sha256) in EXPECTED_ARTIFACTS.items():
        entry = artifact_entries.get(filename)
        if entry is None or entry["packagetype"] != package_type:
            raise ValueError(f"Missing expected PyPI artifact: {filename}")
        if entry["digests"]["sha256"] != expected_sha256:
            raise ValueError(f"PyPI metadata hash changed for: {filename}")
        artifact_bytes = fetch(entry["url"])
        actual_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(f"Downloaded artifact hash mismatch for: {filename}")
        verified_artifacts.append((entry, artifact_bytes))

    wheel_entry, wheel_bytes = next(
        item for item in verified_artifacts if item[0]["packagetype"] == "bdist_wheel"
    )
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        metadata_name = next(
            name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(wheel.read(metadata_name))

    runtime_requirements = {
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if ";" not in requirement
    }
    if runtime_requirements != EXPECTED_RUNTIME_REQUIREMENTS:
        raise ValueError(
            "Published runtime requirements changed: "
            f"expected {sorted(EXPECTED_RUNTIME_REQUIREMENTS)}, "
            f"found {sorted(runtime_requirements)}"
        )
    if metadata["Name"] != PACKAGE_NAME or metadata["Version"] != PACKAGE_VERSION:
        raise ValueError("Wheel METADATA has an unexpected project identity")
    if metadata["License-Expression"] != "MIT":
        raise ValueError("Wheel METADATA has an unexpected license expression")

    root_ref = f"pkg:pypi/{PACKAGE_NAME}@{PACKAGE_VERSION}"
    dependency_components = []
    dependency_refs = []
    for requirement in sorted(runtime_requirements):
        name, version_range = requirement_parts(requirement)
        component_ref = f"dependency:{requirement}"
        dependency_refs.append(component_ref)
        dependency_components.append(
            {
                "type": "library",
                "bom-ref": component_ref,
                "name": name,
                "scope": "required",
                "purl": f"pkg:pypi/{name}",
                "properties": [
                    {
                        "name": "io.egoflow.python.requirement",
                        "value": requirement,
                    },
                    {
                        "name": "io.egoflow.python.version-range",
                        "value": version_range,
                    },
                ],
            }
        )

    distribution_references = []
    for entry, _ in sorted(verified_artifacts, key=lambda item: item[0]["filename"]):
        distribution_references.append(
            {
                "type": "distribution",
                "url": entry["url"],
                "comment": entry["filename"],
                "hashes": [
                    {
                        "alg": "SHA-256",
                        "content": entry["digests"]["sha256"],
                    }
                ],
            }
        )

    identity_material = "\n".join(
        [
            root_ref,
            *(EXPECTED_ARTIFACTS[name][1] for name in sorted(EXPECTED_ARTIFACTS)),
            *sorted(runtime_requirements),
        ]
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, identity_material)
    latest_upload = max(entry["upload_time_iso_8601"] for entry, _ in verified_artifacts)

    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": latest_upload,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "author": "EgoFlow",
                        "name": "ego-flow-py-sbom-generator",
                        "version": "1",
                    }
                ]
            },
            "component": {
                "type": "library",
                "bom-ref": root_ref,
                "supplier": {"name": "EgoFlow"},
                "name": PACKAGE_NAME,
                "version": PACKAGE_VERSION,
                "description": metadata["Summary"],
                "licenses": [{"license": {"id": "MIT"}}],
                "purl": root_ref,
                "externalReferences": [
                    {
                        "type": "website",
                        "url": f"https://pypi.org/project/{PACKAGE_NAME}/{PACKAGE_VERSION}/",
                    },
                    {
                        "type": "vcs",
                        "url": "https://github.com/ego-flow/ego-flow-py",
                    },
                    *distribution_references,
                ],
                "properties": [
                    {
                        "name": "io.egoflow.python.dependency-model",
                        "value": "published-direct-runtime-requirements",
                    },
                    {
                        "name": "io.egoflow.python.requires-python",
                        "value": metadata["Requires-Python"],
                    },
                    {
                        "name": "io.egoflow.sbom.reproducible-timestamp-source",
                        "value": "latest-pypi-artifact-upload",
                    },
                ],
            },
        },
        "components": dependency_components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": dependency_refs},
            *({"ref": ref, "dependsOn": []} for ref in dependency_refs),
        ],
    }

    output_path.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {output_path}")
    print(f"SHA-256 {hashlib.sha256(output_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
