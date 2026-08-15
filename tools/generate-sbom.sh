#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/.." && pwd)"
cyclonedx_bin="${CYCLONEDX_BIN:-}"

if [[ -z "${cyclonedx_bin}" ]]; then
  cyclonedx_bin="$(command -v cyclonedx || command -v cyclonedx-cli || true)"
fi
if [[ -z "${cyclonedx_bin}" || ! -x "${cyclonedx_bin}" ]]; then
  echo "CycloneDX CLI is required. Set CYCLONEDX_BIN to an executable 0.33.1 binary." >&2
  exit 1
fi

python3 "${script_dir}/generate-sbom.py" "${repo_dir}/sbom.cdx.json"
"${cyclonedx_bin}" validate \
  --input-file "${repo_dir}/sbom.cdx.json" \
  --input-format json \
  --input-version v1_6 \
  --fail-on-errors
