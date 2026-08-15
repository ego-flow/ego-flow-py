# Changelog

All notable changes to EgoFlow Python Client are documented in this file.

## [0.0.1] - 2026-08-15

### Added

- Repository resolution and paginated dataset manifests through EgoFlow Python tokens.
- Hugging Face `Dataset` and `IterableDataset` loading with server-scoped artifact caching.
- SHA-256 verification for downloaded dataset videos.
- PyAV-backed frame and batch decoding in NumPy, PyTorch, and native formats.
- Live stream discovery and direct MediaMTX HLS playback with short-lived playback tickets.
- Community contribution and conduct guidance with explicit MIT licensing information.

### Fixed

- Preserve error code, message, and details from the server's structured error envelope.
- Prevent Python tokens from being forwarded to external artifact URLs or cross-origin redirects.
- Treat non-positive frame limits as an empty result without opening the decoder.
- Reject unsupported frame formats before attempting frame conversion.
