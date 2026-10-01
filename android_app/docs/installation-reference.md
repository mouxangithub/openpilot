# Installation reference

Normal setup: [Jetson guide](jetson.md), [Mac app](macos-app.md),
[PC guide](platforms.md). This page: what the installer does, manual installs,
the [server command](#the-server-command) and custom integrations.

<a id="jetson-installation"></a>

## Jetson and PC installation

### What the installer changes

- Installs TensorRT if it is missing:
  - Jetson: JetPack's `libnvinfer10`, `libnvonnxparsers10` and
    `libnvinfer-plugin10` from its package source (on JetPack 7.2 the newest
    there, at least 10.16.2.10; a 2.3 GB download).
  - PC and WSL2: no system package. NVIDIA's TensorRT 11.3.0.99 runtime wheel,
    the build the server is compiled against (3.8 GB, checked against its
    sha256), unpacked to `/opt/jetlink/tensorrt/11.3.0.99` (2.7 GB). The
    service passes that folder to the server with `--tensorrt-libs`, and later
    server versions reuse it. Only the NVIDIA driver comes from the system.
- Installs libcurl (the server needs it), `curl` and `git` if missing, and
  `unzip` on a PC, from the distribution's package manager: apt, dnf, pacman
  or zypper. A PC with another installs when they are already there.
- PC without NVIDIA driver 580: on Ubuntu's family (Mint, Pop!_OS), installs
  it with `ubuntu-drivers` (`nvidia:580-open`); on Arch's (EndeavourOS,
  CachyOS; not Manjaro), `nvidia-open` for the running kernel
  (`nvidia-open-lts` on the LTS kernel, `nvidia-open-dkms` and the headers on
  another). Elsewhere it prints the distribution's documented steps and stops.
  Either way the install continues after a restart.
- Unpacks the release's server to `/opt/jetlink/<version>`, with
  `/opt/jetlink/current` pointing at it and `previous` at the one before, and
  checks it can use the GPU before it replaces the running one.
- Installs the `jetlink-server` service (runs as root) and its udev rules from
  the server's tarball, so they always match the binary, and the `jetlink`
  command. Settings: `/etc/jetlink/server.env` ([keys](#the-service));
  your answers: `/etc/jetlink/install.conf`.
- Serves the read-only status page on port 5600 (a question; 0 turns it off).
- Keeps models and prepared engines in `/mnt/data/jetlink` on a Jetson,
  `/var/lib/jetlink` on a PC.
- Jetson only: sets the fastest power mode (MAXN SUPER on an Orin Nano; may
  need one restart) and runs `jetson_clocks` before every start; adds 8 GB of
  swap for preparing the 1.7 GB models; stops boot waiting for a network (none
  in the car; about two minutes); caps the system log at 200 MB.

An install from 0.6.0 or earlier runs the server in Docker. Its next
`jetlink update` moves it to the native server, keeping the answers, models,
engines and Jetson setup, and saves the Docker setup in
`/etc/jetlink/docker-era`. Jetlink's Docker images go once the new server runs;
Docker itself stays.

- Jetson: the host gets the JetPack TensorRT the Docker image had, so its
  prepared engines load as they are (checked on JetPack 7.2.1). A later
  TensorRT update from JetPack's package source prepares each model again,
  once.
- PC: the Docker image had the same TensorRT 11.3.0.99 build. An engine that
  does not load is prepared again, once, from the downloaded model.

### Installing by hand

The installer is the supported path. Its pieces, from a release tarball, on
any systemd distribution with glibc 2.35 or newer:

1. libcurl (`libcurl4` on apt and zypper, `libcurl` on dnf, in `curl` on
   pacman), and TensorRT:
   - Jetson: `sudo apt install libnvinfer10 libnvonnxparsers10 libnvinfer-plugin10`.
   - PC: NVIDIA driver 580 or newer, and TensorRT 11.3.0.99's libraries from
     NVIDIA's wheel. Its sha256 must equal `PC_TRT_SHA256` at the top of
     `install.sh`:

     ```bash
     wheel=tensorrt_cu13_libs-11.3.0.99-py3-none-manylinux_2_28_x86_64.whl
     curl -fLO "https://pypi.nvidia.com/tensorrt-cu13-libs/$wheel"
     sha256sum "$wheel"
     sudo unzip -j "$wheel" 'tensorrt_libs/lib*.so*' '*/LICENSE.txt' -x '*_win_*' \
       -d /opt/jetlink/tensorrt/11.3.0.99
     ```

2. The tarball in `/opt/jetlink/<version>`, and `current` pointing at it:

   ```bash
   sudo mkdir -p /opt/jetlink/<version>
   sudo tar -xzf jetlink-server-<version>-linux-<arch>.tar.gz --strip-components 1 -C /opt/jetlink/<version>
   sudo ln -sfn /opt/jetlink/<version> /opt/jetlink/current
   ```

3. `/etc/jetlink/server.env`, which the service needs, with at least the
   cache folder, and on a PC the TensorRT folder ([keys](#the-service)):

   ```bash
   sudo mkdir -p /etc/jetlink
   echo JETLINK_CACHE_DIR=/var/lib/jetlink | sudo tee /etc/jetlink/server.env
   # a PC only
   echo 'JETLINK_TENSORRT="--tensorrt-libs /opt/jetlink/tensorrt/11.3.0.99"' | sudo tee -a /etc/jetlink/server.env
   ```

4. `share/jetlink/systemd/jetlink-server.service` from the tarball in
   `/etc/systemd/system`, then
   `sudo systemctl daemon-reload && sudo systemctl enable --now jetlink-server`.
5. Jetson: a drop-in for the service with `ExecStartPre=-/usr/bin/jetson_clocks`.
6. Always-on supply only (lets the comma wake the Jetson):
   `share/jetlink/udev/99-jetlink-usb-wakeup.rules` in `/etc/udev/rules.d`.

The `jetlink` command needs the installer's files, so a hand install manages
the service with `systemctl` and reads its log with
`journalctl -u jetlink-server`.

<a id="the-service"></a>

### The service

`jetlink-server.service` runs
`/opt/jetlink/current/bin/jetlink-server --usb --backend trt` as root, and
starts it again 2 seconds after it exits. Its settings come from
`/etc/jetlink/server.env`:

| Key | Passed as | The installer sets it to |
| --- | --- | --- |
| `JETLINK_CACHE_DIR` | `--cache` | `/mnt/data/jetlink` on a Jetson, `/var/lib/jetlink` on a PC |
| `JETLINK_SLEEP_AFTER` | `--sleep-after` (0 when unset) | 120 for **Always on** with deep sleep, else 0 |
| `JETLINK_STATUS_PORT` | `--status-port` (0 when unset) | the status page answer, 5600 by default |
| `JETLINK_POWEROFF` | `--poweroff`, or nothing | `--poweroff` on a Jetson whose battery answer was Yes |
| `JETLINK_TENSORRT` | `--tensorrt-libs DIR`, or nothing | the TensorRT folder on a PC; empty on a Jetson |

- The installer also writes `JETLINK_JETSON`, `JETLINK_FLAVOR` and
  `JETLINK_SERVER_VERSION` there, for the `jetlink` command.
- It rewrites the file on every run. Change the answers with `jetlink setup`;
  put anything else, such as `JETLINK_USB_LPM=1`, in a drop-in
  (`sudo systemctl edit jetlink-server`, then `Environment=JETLINK_USB_LPM=1`
  under `[Service]`).
- Its own drop-ins wait for the cache's mount and, on a Jetson, run
  `jetson_clocks` before each start.

`jetlink run` runs the service's command line, with those settings, in the
terminal instead (it stops the service first; Ctrl-C stops it). Extra flags go
on the end: `jetlink run --listen` for a TCP bench, `jetlink run --log-level debug`.

<a id="the-server-command"></a>

## The server command

`jetlink-server` is the one server on every platform: the service on a Jetson
or PC, a Mac's server in a terminal ([from a terminal](platforms.md#from-a-terminal)),
and the server inside the Mac, iPhone and Android apps.
`jetlink-server <command> --help` lists each command's options.

| Command | Does |
| --- | --- |
| `serve` (the default) | Serves the comma until SIGINT or SIGTERM. |
| `build ONNX` | Builds this backend's engine for a model before a drive, and loads it once. The next `serve` on that cache preloads it. |
| `models ...` | The model catalog and the cache: [model command reference](model-cli.md). |
| `bench` | Runs a built engine at the comma's pace (20 frames a second) with no comma and no link, and prints its times. |
| `backends` | Lists the backends and why each can or cannot run here. Exits 0 when one can. |
| `spec ONNX` | Prints the spec the comma is sent for a model, as JSON (the file `scripts/bench_link.py --spec` reads). |

`build`, `bench` and `models prepare` open the GPU and the cache on their own:
stop any server using the same cache first.

### serve

| Option | Default | Does |
| --- | --- | --- |
| `--usb` | off | Be the USB host for the comma's gadget (usbfs on Linux, IOKit on a Mac). No TCP listener then, unless `--listen` too. |
| `--listen` | on without `--usb` | Listen on TCP for bench tools. No authentication: trusted networks only. |
| `--host ADDR` | `0.0.0.0` | The address to listen on. |
| `--port N` | `5599` | The TCP port. |
| `--dial HOST[:PORT]` | none | Also dial this address and serve it, as the phone apps dial the comma (`192.168.60.1:5599`) over its USB network interface. |
| `--cache DIR` | [see below](#cache-folder-and-environment) | Models and prepared engines. |
| `--backend B` | `auto` | `auto` takes TensorRT where it loads, else ONNX Runtime; `trt` or `ort` that cannot run here is an error. The service passes `trt`, so a machine without TensorRT fails loudly instead of serving from the CPU. |
| `--device D` | per backend | `trt`: the CUDA device index (0). `ort`: `ane` (default), `ane-whole`, `coreml` or `cpu` on a Mac; `cpu` on Linux. |
| `--tensorrt-libs DIR` | `lib/tensorrt` beside `bin/` if it exists, else the loader path | Where TensorRT's libraries are: a PC's own copy. A Jetson's are JetPack's, on the loader path. |
| `--gpu-timing` | off | TensorRT: time each launch with CUDA events and log their spread every 1,200 frames. |
| `--sleep-after S` | 0 (never) | Linux, with `--usb` only: suspend after S seconds with no comma on the bus. |
| `--status-port P` | 0 (off) | Serve the read-only [status page](control-protocol.md#the-status-page) on port P. |
| `--poweroff` | off | Linux: power the machine off when the comma asks (its battery-protection shutdown). Without it the comma is told yes and the machine stays up. |
| `--no-preload` | off | Do not load the engine loaded last until a comma asks for it. |
| `--no-keepalive` | off | Mac ONNX Runtime: no [GPU keep-alive](mac-performance.md#keeping-the-mac-gpu-responsive-between-frames) between frames. |
| `--no-cpu-keepwarm` | off | Mac ONNX Runtime: no busy CPU core between Neural Engine frames. |
| `--log-level L` | `info` | `debug`, `info`, `warning` or `error`, on standard error (the service's go to the journal: `jetlink logs`). |

Exit status: 0 after SIGINT or SIGTERM; 1 when it cannot serve (no usable
backend, a bad option, a cache it cannot create); 3 after a CUDA error that
only a new process recovers from (the service starts one, which loads the
engine again).

### build, bench and backends

- `build ONNX [--frame-skip N]`: N model frames per camera frame, 4 by default.
  Copies the model into the cache first.
- `bench [--seconds S] [--sha256 SHA] [--frame-skip N]`: S up to 3600, 60 by
  default; the model loaded last unless `--sha256` names another one built
  here. The report goes to standard output.
- `backends`: `--backend trt` tries TensorRT alone, so it exits 0 only with a
  usable GPU. The installer runs it before it replaces a server.
- All three take `--backend`, `--device`, `--tensorrt-libs` and
  `--gpu-timing`; `build` and `bench` also `--cache` and `--log-level`.

<a id="cache-folder-and-environment"></a>

### Cache folder and environment

The cache is `--cache DIR`, else `$JETLINK_CACHE`, else:

| Where | Cache |
| --- | --- |
| Jetson | `/mnt/data/jetlink` |
| Linux, as root | `/var/lib/jetlink` |
| Linux, as a user | `${XDG_CACHE_HOME:-~/.cache}/jetlink` |
| Mac | `~/Library/Caches/jetlink` |

| Variable | Does |
| --- | --- |
| `JETLINK_CACHE` | The cache folder when `--cache` is not given. |
| `JETLINK_USB_LPM=1` | Linux: leaves USB 3 link power management on during a session, for comparing ([why it is off](#custom-usb-integrations)). |
| `JETLINK_FAULT_CUDA_AFTER=N` | Tests only: every frame after the first N fails as a CUDA error the process cannot recover from, to exercise the exit and restart. |

## Custom USB integrations

- comma 3X (AGNOS kernel 4.9.103) has FunctionFS and USB gadget support.
- The server is always the USB host, through usbfs (IOKit on a Mac): no driver
  and no gadget kernel modules on the host.
- On Linux the server turns off USB 3 link power management (U1/U2) on the
  comma's port while it serves the comma, and puts the kernel's default back
  when the session ends, when the comma has sent nothing for 30 s (parked with
  its gadget still up; off again at its next message), or when the server
  stops. On, waking the link cost 2.2 ms a frame on the bench Jetson (4.2
  against 2.0 ms of transport, p50); off, the idle link drew 0.18 W more, so it
  is not off for the whole park. Deep sleep and USB wake are unaffected.
  `JETLINK_USB_LPM=1` leaves it on.
- How the link carries a frame: [link protocol](transport.md#link-protocol).
- Nothing on the comma runs by hand. The owner builds the gadget on its first
  step, USB or iOS per the comma's Accelerator Link setting, and rebuilds it
  when the setting changes with the car off (the setting is locked while
  driving).

`scripts/comma/jetlink-root.sh` is every root action Jetlink takes on the comma
(comma four and 3X); the owner runs it under `sudo -n`.

| Subcommand | Does |
| --- | --- |
| `gadget` | Creates the gadget configuration: the vendor interface alone. The owner then opens `ep0`, writes the FunctionFS descriptors and binds the USB device controller (binding needs the descriptors first). |
| `gadget --ios` | Accelerator Link iOS: composite, adds a network interface for an iPhone. |
| `net` | Run by the owner after each iOS bind (the interface exists only from the first bind). |
| `port hold`, `port off` | Keeps the USB-C port the device end of a USB link. |
| `vm apply`, `vm restore` | Sets and undoes the VM tuning the link needs while the comma records. |
| `check` | By hand, `sudo scripts/comma/jetlink-root.sh check`: what is built and the negotiated bus speed. |
| `teardown` | Removes the gadget. |

The owner holds the gadget while the link is on; openpilot lists it as
`jetlinkd`. Standard library only, about 10 MB. Code in `jetlink/comma/`:

| File | Role |
| --- | --- |
| `gadget.py` | the gadget, and what carries the link |
| `owner.py` | the owner |
| `lending.py` | the lease modeld borrows the endpoints, or a phone's dial, on |
| `port.py` | the USB-C port |
| `root.py` | runs `jetlink-root.sh` under `sudo -n`, on AGNOS only |

The zoompilot fork's manager runs it as its adapter module,
`openpilot/sunnypilot/jetlink_adapter`, whose `main()` hands
`jetlink.openpilot.owner` the params directory and keys, the chestnut's USB
ids and the adapter's name; the owner starts `python -m
jetlink.openpilot.provision --adapter openpilot.sunnypilot.jetlink_adapter`
when there is provisioning to do.

| Descriptor | Value |
| --- | --- |
| idVendor:idProduct | `1209:0001` (pid.codes test allocation) |
| bcdDevice | `0x0100`; `0x0101` for iOS, so hosts refetch cached descriptors |
| bDeviceClass/SubClass/Protocol | `0x00/0x00/0x00`, class per interface; for iOS `0xEF/0x02/0x01`, Miscellaneous with interface association (composite) |
| Interface 0 | `0xFF/0xFF/0xFF` vendor specific, one bulk IN and one bulk OUT endpoint: the Jetlink link |
| Interfaces 1 and 2 (iOS only) | CDC-NCM control and data: the network for an iPhone |
| Network (iOS only) | comma `192.168.60.1/24`; DHCP `192.168.60.2` to `.254` with 10 minute leases from dnsmasq on the gadget's interface (`usb1` or later, since the modem holds `usb0`), no router or DNS options |

Custom distributions need their own USB product ID.

## Versions and manual rollback

### Choose a version

- The installer installs the newest release; `jetlink update` moves to the
  next. `jetlink update --ref main` switches to development builds (the `edge`
  prerelease).
- The zoompilot fork pins the Jetlink it was tested with as its `jetlink_repo`
  submodule: `develop`, `danger-unstable` and `jetson-trt` pin a commit on
  `main`, which may lie between releases.
- The comma and the server have to speak the same protocol version; a release
  that changes it says so, and across it the two update together. A comma on
  the older protocol stays on its small model.

To pin a release, pass it to the installer (replace `v0.7.0`);
`jetlink update --ref latest` follows releases again:

```bash
curl -fsSL https://raw.githubusercontent.com/zoompilot/jetlink/v0.7.0/install.sh | bash -s -- --ref v0.7.0
```

<a id="restore-a-docker-image"></a>

### Roll back by hand

- Back one update from 0.7.0 or later: point `current` at `previous` and
  restart. `jetlink update` moves forward again.

  ```bash
  sudo ln -sfn "$(readlink -f /opt/jetlink/previous)" /opt/jetlink/current
  jetlink restart
  ```

- Back to 0.6.0, the last Docker release: `jetlink update --ref v0.6.0`. Its
  own installer takes over with the same answers. 0.6.0's `jetlink update`
  cannot install a native release, so to come forward again run:

  ```bash
  curl -fsSL https://raw.githubusercontent.com/zoompilot/jetlink/main/install.sh | bash -s -- --update --ref latest
  ```

## Deep sleep and USB wake

**Always on** in the installer installs a udev rule that lets the USB hubs wake
the Jetson, sets `--sleep-after 120`, and checks for `deep` in
`/sys/power/mem_sleep`. The server arms the hubs again before every suspend.

- Ignition off: the comma releases USB once the engine is ready and at least
  one minute has passed.
- The Jetson sleeps after 120 s without a USB connection. USB connect or
  disconnect wakes it; with no new connection it sleeps again after 120 s.
- A 30-minute RTC alarm also wakes it, in case a USB wake failed. With no comma
  it sleeps again after 15 s.
- `jetlink caffeinate` keeps an awake Jetson awake, like the Mac's
  `caffeinate`: until Ctrl-C, for `-t SECONDS`, or while `COMMAND` runs. No
  sudo needed. Updates hold it awake on their own.
- Failed sleep retries after 10 s, doubling up to 5 minutes. Check the logs and
  USB wake on the root and onboard hubs.
- With `--sleep-after 0`, the link stays up while the comma is awake.

## Battery-protection shutdown

- The comma requests shutdown at 11.8 V or after 30 hours parked.
- The Jetson powers off (`systemctl poweroff`) only if you answered Yes to the
  installer's battery question: it then writes `JETLINK_POWEROFF=--poweroff` in
  `/etc/jetlink/server.env`. Otherwise it stays up; so does a PC.
  `jetlink setup` changes the answer.
- Restart after full shutdown needs hardware that cycles DC power or triggers
  the J14 power-button input; the devkit boots when DC power returns.
