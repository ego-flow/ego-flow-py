# EgoFlow Python Client

`ego-flow` loads processed videos and active live streams from a self-hosted
[EgoFlow Server](https://github.com/ego-flow/ego-flow-server) into Python workflows.
Repository videos follow a Hugging Face Datasets-style interface, while cached videos and live HLS
streams share the same frame and batch decoding API.

Current release: `v0.0.1`

- Compatible server release: `ego-flow-server v0.0.1`
- [Changelog](./CHANGELOG.md)
- [MIT License](./LICENSE)

## Requirements

- Python 3.9 or newer
- A reachable `ego-flow-server v0.0.1` instance
- A Python token issued from the server dashboard's Profile page
- Direct access to the server's HLS port `8888` when live playback is needed

The default installation includes dataset loading, PyAV video decoding, NumPy output, and PyTorch
tensor output. There are no separate video or torch installation modes.

## Install

Install the release from PyPI:

```bash
python -m pip install "ego-flow==0.0.1"
```

To inspect or install the exact source release:

```bash
git clone https://github.com/ego-flow/ego-flow-py.git
cd ego-flow-py
git switch --detach v0.0.1
python -m pip install .
```

A detached HEAD is expected when using an immutable release tag. Use `git switch main` for
development against the latest source.

## Configure

Set the Python token and the public HTTP endpoint of your EgoFlow server:

```bash
export EF_TOKEN="ef_..."
export EF_SERVER_ENDPOINT="http://127.0.0.1"
```

`EF_SERVER_ENDPOINT` may include a port and may already end in `/api/v1`; the client normalizes both
forms. Tokens are sent as Bearer credentials only to the configured server origin, are removed from
cross-origin redirects, and are redacted from configuration representations.

You can also pass `token=` and `server_endpoint=` directly to the public helpers or construct an
`EgoFlowClient` explicitly.

## Load A Repository Dataset

Repository paths use the server's `owner/repository` slug format:

```python
from ego_flow import load_dataset, open_video

dataset = load_dataset(
    "alice/daily_kitchen",
    split="train",
    decode=False,
    with_thumbnails=True,
)
sample = dataset[0]

video = open_video(sample, format="torch")
batch = next(video.iter_batches(batch_size=8))
print(batch.data.shape)  # [batch, channels, height, width]
```

`load_dataset("owner/repository")` returns `DatasetDict({"train": dataset})`.
Passing `split="train"` returns the `Dataset` directly. EgoFlow Server `v0.0.1` exposes only the
`train` split.

Each row contains the local video path, repository and video identifiers, recording metadata,
semantic metadata, thumbnail path when requested, and artifact size/hash information. Video files
are downloaded through authenticated server endpoints, verified against the manifest SHA-256, and
stored in a server-scoped cache.

### Cache And Download Modes

The default cache uses the operating system's user cache directory. Override it with `cache_dir=` or
the `EGO_FLOW_CACHE` environment variable.

Supported download modes are:

- `reuse_cache_if_exists` — reuse a file only when its expected SHA-256 matches
- `reuse_dataset_if_exists` — accepted as a Hugging Face-compatible alias with the same cache reuse behavior
- `force_redownload` — download every artifact again

With `streaming=True`, manifest pages and rows are consumed lazily. Each video is still materialized
into the local cache when its row is yielded so it can be opened by PyAV or Hugging Face Datasets.

## Work With Live Streams

```python
from ego_flow import list_live_streams, open_live_stream

streams = list_live_streams(
    ingest_type="MEDIAMTX",
    playback_available=True,
)
stream = open_live_stream(streams[0], format="numpy")

for batch in stream.iter_batches(batch_size=4):
    print(batch.data.shape)  # [batch, height, width, channels]
```

The live-stream list can include both `MEDIAMTX` and `HTTP` ingest sessions. HTTP sessions expose
upload progress for monitoring but cannot be opened as HLS. `open_live_stream()` requests a
short-lived playback ticket and reads MediaMTX HLS directly from
`http://{server-host}:8888/{stream_path}/index.m3u8`.

## Low-Level Client

Use `EgoFlowClient` when you need explicit access to the server contract:

```python
from ego_flow import EgoFlowClient

client = EgoFlowClient.from_env()
info = client.info()
repository = client.resolve_repository("alice/daily_kitchen")

for page in client.iter_manifest(repository.id):
    print(page.pagination.page, len(page.videos))
```

The client covers server health/capabilities, Python token validation, repository resolution,
paginated manifests, artifact downloads, live-stream discovery/details, and playback-ticket
issuance.

## Community And License

Contributions are welcome. Before participating, read the [Contributing guide](./CONTRIBUTING.md)
and follow the [Code of Conduct](./CODE_OF_CONDUCT.md).

EgoFlow Python Client source code is distributed under the [MIT License](./LICENSE). Third-party
packages installed as dependencies retain their own licenses and are not relicensed by this
project.

## Development

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test,release]"
python -m pytest
python -m build
python -m twine check dist/*
```

Before publishing, install the built wheel into a clean virtual environment and verify that
`ego_flow.__version__` is `0.0.1`.
