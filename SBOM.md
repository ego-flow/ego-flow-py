# EgoFlow Python Package SBOM

`sbom.cdx.json` is the canonical package-level software bill of materials for
the immutable PyPI release `ego-flow==0.0.1`. It uses CycloneDX JSON 1.6 and is
platform-neutral, matching the `py3-none-any` wheel metadata.

The current SBOM SHA-256 is:

```text
9e25723d4d6f220bd59e16730bc247b5cf73122cda2eeae6190ec71a3e3fb79b
```

## Published release identity

The generator downloads both artifacts from PyPI and fails unless the API
metadata and downloaded bytes match these frozen hashes:

| Artifact | SHA-256 |
|---|---|
| `ego_flow-0.0.1-py3-none-any.whl` | `32972180747908a54e9088569f62d5ea188a5f4d5274c7e51aae8092fd94ca10` |
| `ego_flow-0.0.1.tar.gz` | `68e8e4d5f7f90baeaff11a4c1135cdef6ba3ac85d807fd8ea353705f84fad392` |

The wheel declares MIT, Python `>=3.9`, and these five required runtime
dependency ranges:

| Dependency | Published requirement |
|---|---|
| PyAV | `av>=12.0` |
| Hugging Face Datasets | `datasets>=2.19` |
| NumPy | `numpy>=1.23` |
| platformdirs | `platformdirs>=4.0` |
| PyTorch | `torch>=2.0` |

The test and release extras (`pytest`, `build`, and `twine`) are development
inputs and are not part of the default runtime dependency graph.

## Recreate and validate

The checked generator requires network access to PyPI and the official
[CycloneDX CLI](https://github.com/CycloneDX/cyclonedx-cli). It was verified
with CycloneDX CLI `0.33.1`.

```bash
CYCLONEDX_BIN=/absolute/path/to/cyclonedx ./tools/generate-sbom.sh
```

The generator:

1. reads the PyPI `0.0.1` release record;
2. downloads and verifies the exact wheel and sdist bytes;
3. reads the wheel's authoritative `METADATA` rather than inferring package
   contents from the current worktree;
4. checks the project identity, MIT license expression, Python requirement, and
   five runtime dependency declarations;
5. creates a deterministic CycloneDX 1.6 document and runs official schema
   validation.

Two consecutive generations produced the same SBOM hash and serial number.
The timestamp is intentionally derived from the latest immutable PyPI artifact
upload rather than the local clock.

## Packaging boundary

`SBOM.md`, `sbom.cdx.json`, `tools/`, and the repository policy/CI files are
repository-only release evidence. A fresh wheel and sdist build was extracted
and compared with the published artifacts: member names and extracted contents
matched, and none of these repository-only files entered either distribution.
The rebuilt archive checksums differ because archive container timestamps are
not reproducible; the published hashes above remain canonical.

## Interpretation and known limits

- This is a library-package SBOM, not an installed-environment SBOM. Because
  `0.0.1` publishes version ranges rather than a lockfile, pip may select
  different transitive versions by Python version, operating system,
  architecture, index state, and install date.
- Each deployment should additionally generate and retain an environment SBOM
  after dependency resolution. That environment SBOM, not this package-level
  document, is the source for exact transitive versions and deployment-specific
  vulnerability review.
- Version ranges are stored as CycloneDX component properties and dependency
  relationships. They must not be read as claims that every permitted future
  version has been tested.
- Dependency license metadata is not a relicensing grant. Verify the exact
  installed environment's authoritative license terms before redistribution.
