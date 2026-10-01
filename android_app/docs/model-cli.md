# Model command reference

Reference for `jetlink models`, the installer's command, which runs
`jetlink-server models` on the server's models folder. To choose or prepare a
model before a drive, start with [model management](models.md).

## Model identifiers and storage

- A **ref** is a 40-character commit hash from comma's openpilot repository. It
  names a model in sunnypilot's big-model catalog, the list under
  **Settings > Models > Big Model** on the comma.
- A **SHA-256** is the 64-character hash of the ONNX file. One ref resolves to
  exactly one SHA-256, and that never changes.
- The catalog updates on its own, so new models appear without a Jetlink update.
- From Cinque Terre V3 on, the ONNX comes from comma's model repo on Hugging
  Face (`commaai/openpilot_driving_models`).

| Path | What is in it |
| --- | --- |
| `<cache>/models/` | The downloaded ONNX files, about 766 MB each |
| `<cache>/engines/` | The prepared engines and their sidecar files, one per backend and device |
| `<cache>/registry/` | The cached catalog, the resolved pointers, and records of models you imported |

Default cache folders: [model management](models.md#downloads-prepared-engines-and-disk-space).
`--cache DIR` overrides it on every command.

## Commands

```
jetlink models list      [--refresh] [--json]
jetlink models resolve   REF [--json]
jetlink models fetch     REF_OR_SHA256
jetlink models import    PATH [--name NAME]
jetlink models inventory [--json]
jetlink models rm        SHA256 [--artifacts] [--model]
jetlink models prepare   REF_OR_SHA256 [--backend auto|trt|ort] [--device D]
```

- From a checkout, run `jetlink-server models ...` with the same arguments;
  each takes `--cache DIR`. `jetlink models prepare` passes a PC's
  `--tensorrt-libs` itself; `jetlink-server models prepare` on a PC needs it
  ([the server command](installation-reference.md#the-server-command)).
- `REF_OR_SHA256` is a ref, or the SHA-256 of a model whose ref was resolved
  on this machine before.
- Output a script reads goes to standard output; progress and warnings go to
  standard error.

| Command | Does |
| --- | --- |
| `list` | The catalog, newest first, with each model's size and state (`downloaded`, `prepared`). Uses the cached catalog if under an hour old; `--refresh` fetches a new one. The table shortens refs; `--json` prints the full catalog: the [control protocol](control-protocol.md)'s `catalog` event fields. |
| `resolve` | Prints a ref's SHA-256 and size in bytes. Cached, so later lookups need no network. |
| `fetch` | Downloads the ONNX to a `.part` file, checks size and hash, renames it into place, and prints its path. An interrupted download starts over. |
| `import` | Hashes and copies an ONNX file you already have into `<cache>/models/`, records its name, and prints the SHA-256 and path. |
| `inventory` | Downloaded models, prepared engines with backend and device, and disk use. `*` marks the engine a server started here would load. `--json` prints the `inventory` event fields. |
| `rm` | `--model` deletes the download, `--artifacts` every prepared engine; name at least one. A prepared engine keeps working after its download is removed. |
| `prepare` | Fetches the model if needed, then builds an engine and loads it once, as `jetlink-server build` does. That makes it the model loaded last, which a server started on this cache preloads. |

**Do not run `prepare` while a server uses the same cache.** Concurrent builds
are unsupported and can exhaust memory. On a Jetson or PC, `jetlink models
prepare` refuses while the service runs:

```bash
jetlink stop
jetlink models prepare f877d7a0ccc3cce943c76e285214c020cd65c899
jetlink start
```

The apps prepare through their running server instead.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Refused, or the ref or model was not found |
| 2 | A network request failed |
| 3 | The download failed verification, by size or by hash |
