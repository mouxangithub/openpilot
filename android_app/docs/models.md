<a id="models-and-the-model-cli"></a>

# Choose and prepare models

Pick a model on the comma under **Settings > Models > Big Model**, offroad and
online (in or out of the car). The comma downloads it, sends it to the server,
and waits while the server prepares it. Start with the default. Changing and
switching models: [daily use](using-jetlink.md#choose-a-model).

## Prepare ahead of time (optional)

Download on the server's internet connection before connecting the comma. This
saves time when the comma is on LTE.

On a Mac, open **Models**, click **Use Model**, and wait for **In Use**. Then pick
the same model on the comma. See the [Mac guide](macos-app.md#use-a-model-before-you-drive).
The iPhone and Android apps: **Get** under **Models**.

### On a Jetson or an installed PC

List the models, then fetch one by its full 40-character `ref` from the JSON
(plain `list` shortens refs):

```bash
jetlink models list --json
jetlink models fetch <ref>
```

To prepare it too, stop the server first, with any connected comma offroad:

```bash
jetlink stop
jetlink models prepare <ref>
jetlink start
```

**Do not prepare a model in a separate process while the server uses the same
cache.** Concurrent builds are unsupported and can exhaust memory;
`jetlink models prepare` refuses while the service runs. The apps prepare
through their running server, so they need no stop and start.

<a id="from-a-source-install"></a>

### From a checkout

The same commands on a built `jetlink-server`: `jetlink-server models list
--json`, `jetlink-server models fetch <ref>`, `jetlink-server models prepare
<ref>`. Stop any server using that cache before `prepare`.

## Downloads, prepared engines, and disk space

- A download is the ONNX model, most about 766 MB.
- A prepared engine is built for your backend and device. Jetlink keeps both.
- A runtime update may prepare again; the download is kept.
- On a Mac, allow about 3 GB per model with the default backend. Each Mac
  `--device` (`ane`, `coreml`, `ane-whole`) has its own prepared engine; see
  [backends](backends.md#runtime-comparison).

| Installation | Default cache folder |
| --- | --- |
| Jetson installer | `/mnt/data/jetlink` |
| PC installer | `/var/lib/jetlink` |
| Mac app | `~/Library/Application Support/Jetlink/cache` |
| `jetlink-server` on a Mac | `~/Library/Caches/jetlink` |
| `jetlink-server` on Linux | `/mnt/data/jetlink` on a Jetson, else `/var/lib/jetlink` as root, else `~/.cache/jetlink` |

- Mac app: choose a cache folder in Settings.
- `jetlink-server`: `JETLINK_CACHE` or `--cache DIR`
  ([the rule](installation-reference.md#cache-folder-and-environment)).
- The installer's `jetlink models` uses the server's cache.

Disk use: `jetlink models inventory` (installer), `jetlink-server models
inventory`, or **Models** in the apps.

## Commands

Listing, fetching, importing, preparing and deleting models:
[model command reference](model-cli.md#commands).

## Developer reference

[Model CLI](model-cli.md) and [control protocol](control-protocol.md).

<a id="model-identifiers-and-storage"></a>
<a id="the-protocol"></a>
<a id="list"></a>
<a id="resolve"></a>
<a id="fetch"></a>
<a id="import"></a>
<a id="inventory"></a>
<a id="rm"></a>
<a id="prepare"></a>
<a id="exit-codes"></a>
<a id="starting-a-server-with-a-control-socket"></a>
<a id="on-connect"></a>
<a id="example"></a>
<a id="events"></a>
<a id="commands-1"></a>
