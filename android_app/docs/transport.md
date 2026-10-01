# Cables, networking, and power

Initial setup: [README](../README.md#quick-start), [Jetson
guide](jetson.md), [platform setup](platforms.md).

## USB connection

A USB 3 data cable; charge-only cables do not work.

| Server | Cable to the comma's USB-C port |
| --- | --- |
| Jetson | USB-A to USB-C, from the Jetson's USB-A port (its USB-C port may not connect) |
| Mac | USB-C cable, or USB-A to USB-C with a USB-C adapter |
| Linux PC | USB-A to USB-C, from a USB-A port on the PC |
| iPhone | USB-C cable, or USB-A to USB-C with a USB-C adapter; a powered USB-C hub between them keeps the phone charging |
| Android | USB-A to USB-C, from a USB 3 hub with USB-C power pass-through on the phone, so it charges; or a USB-C to USB-A adapter |

- The comma holds its USB-C port as the device for any host but a chestnut.
- The comma's USB-C port cannot serve Jetlink and chestnut at once.

### What the comma presents

One of two USB gadgets, per the comma's **Accelerator Link** setting (models
settings):

| Setting | For | Gadget |
| --- | --- | --- |
| **USB** | Jetson, Mac, Linux PC, Android | Plain: one vendor-specific interface, one bulk endpoint pair, opened through usbfs on Linux (IOKit on the Mac; usbfs on the descriptor Android's USB host API hands the app). No network interface. |
| **iOS** | iPhone | Composite: interface 0 is the same vendor interface (never used on iOS), then a CDC-NCM network interface, since iOS gives apps no vendor USB access but drives USB network adapters itself. |

- iOS network: the comma is `192.168.60.1` and runs DHCP; the phone gets a
  `192.168.60.x` address with no gateway or DNS, keeps its internet route over
  Wi-Fi, and dials `192.168.60.1:5599`.
- Changing the setting rebuilds the gadget (an unplug), so it changes only
  offroad.
- Comma side: the `jetlink.comma` package. The owner holds the gadget and lends
  modeld its endpoints or the phone's dial; every root step goes through
  `scripts/comma/jetlink-root.sh`. See the
  [installation reference](installation-reference.md#custom-usb-integrations).

### Bus speed

Latency needs USB 3 (SuperSpeed). A frame is about 400 KB to the server and
8 KB back (the model's hidden state stays on the server): about 1 ms on USB 3,
10 ms on USB 2 (hence USB 3 on every hop: cable, adapter, any hub).

On Linux the server turns off USB 3 link power management on the comma's port
while it serves the comma, and puts the kernel's default back when the session
ends or the comma has sent nothing for 30 s (parked with its gadget still up),
until its next message: waking the link from its low-power states cost 2.2 ms a
frame on the bench Jetson, and keeping it awake with nothing to carry costs
0.18 W ([details](installation-reference.md#custom-usb-integrations)).

Negotiated speed on the comma: `/sys/class/udc/*/current_speed`
(`super-speed` is USB 3, `high-speed` USB 2), also printed with the built
gadget by `sudo scripts/comma/jetlink-root.sh check`.

### Open: the comma's write size, next bench with a Jetson

The comma sends a frame in one `writev` of up to 512 KB
(`FfsTransport.write_chunk`). On its 4.9 kernel FunctionFS copies each write
into a freshly allocated contiguous buffer, and 512 KB is an order-7 page
allocation, which the allocator treats as costly: with loggerd keeping the page
cache full it can compact and reclaim inline, and that is the 200-350 ms gadget
stall that made the big model fall back. `jetlink-root.sh vm apply` answered it
with dirty-memory caps plus a 128 MB `vm.min_free_kbytes` floor, measured
together (worst frame 244 to 72 ms). The floor is gone since v0.7.3: it took
about 360 MB out of MemAvailable and openpilot's LOW MEMORY alert fired at a real
80 %. A drive with the fix showed no regression; the caps alone are not yet
measured against the stall on the bench.

To settle it, with a Jetson on the bench and the comma parked offroad:

1. `/data/jetlink-bench-20260906/bench.py --seconds 900 --record --output ...`
   at the current 512 KB, then with `--write-chunk 32768` (order 3, below the
   costly line; 16 KB is the read side already). Compare `exec` p99/max,
   `over_50ms` and fallbacks; loggerd must be writing for the stall to show.
2. If the smaller write wins, the blocker is the dwc3 replay noted above
   `write_chunk`: a TRB resent about once in 400 frames is dropped by seq when
   the message was one write, and lands mid-stream when it was several. A
   smaller quantum needs framing that survives a mid-message replay before it
   can ship.
3. If 512 KB with the caps alone shows no fallbacks over the soak, leave the
   quantum and close this.

### The network link on a Linux host

The comma's kernel (4.9, Qualcomm's u_ether) sends NCM blocks slowly when the
host lets it pack several packets into one. Comma to host, bench mici,
SuperSpeed, Jetson host:

| NCM block size | Throughput |
| --- | ---: |
| 16 KB (Linux default) | 22 Mbit/s |
| 2 KB | 190 Mbit/s |

Host to comma is unaffected (340 Mbit/s); CPU is not the limit. A Linux host
using the network link (a bench standing in for a phone, or a PC over the cable
network) should cap the block size:

    echo 2048 > /sys/class/net/<interface>/cdc_ncm/rx_max

`scripts/99-jetlink-host.rules` does that on plug-in. Apple's NCM driver picks
its own block size and showed no slow path (reference phone: 393 KB up in under
19 ms).

With the cap, parked live bench on the comma (Cinque Terre V3, 180 s, 3,416 big
frames, every frame delivered; 2026-09-27, with the earlier link protocol's
74 KB replies):

| Link | p50 | p99 |
| --- | ---: | ---: |
| Network link | 36.4 ms | 40.6 ms |
| Vendor interface | 28.6 ms | 30.3 ms |

The ~8 ms gap is all in the comma's send of the 393 KB frame (`bench_link.py`:
26 ms of transport vs 8.6 ms). That is the network link's floor on this kernel;
the vendor interface stays the link for every host that can open it.

## Link protocol

The comma (`jetlink/protocol.py` in this repo) and every server speak protocol
3, over the vendor interface's bulk pipes or over TCP (a phone's cable network,
bench tools). There is one version: update the comma and Jetlink together.

- **Messages.** A 32-byte header (magic `JLNK`, version 3, type, sequence
  number, flags, length) and a payload. Every message carries version 3. A
  header with any other version is a broken stream: the server drops the
  link, a comma on another version gets no answer to its hello, and it drives
  on its small model.
- **Session.** The comma says hello, asks for its model's engine (uploading
  the model if the server lacks it), waits until it is ready, then sends one
  INFER_REQ per model frame, 20 a second. While it waits it pings; a server
  that has not heard this comma's hello (it restarted meanwhile) answers with
  an error, and the comma says hello again.
- **INFER_REQ.** The comma's warped camera images (uint8) and 12 floats
  (`desire`, `traffic_convention`, `action_t`): 393,304 bytes with the header,
  409,600 over USB with the comma's padding.
- **INFER_RESP.** The status, the server's timings, and the model's outputs in
  float32 without `hidden_state`: 8,324 bytes for the current models (73,860
  with it). The comma sets WANT_HIDDEN on a frame to get the whole vector, for
  logging every output; WANT_STATE appends the server's telemetry as JSON.
- **Hidden state on the server.** A queued model (BMRLNAP, Cinque Terre V2,
  Lebowski) feeds each frame's `hidden_state` into the next frame, where
  openpilot's modeld feeds its own. The server keeps it: zero when an engine
  loads, on every hello and on a frame flagged RESET_QUEUES, and replaced only
  after a frame whose outputs are all finite (a NOT_FINITE or failed frame
  leaves the last good one). Outputs are bit for bit what they were when the
  comma sent the state back each frame. A stateful model (Cinque Terre V3)
  keeps its state in the engine.
- **Padding.** A bulk transfer ends on a short packet. Over USB the comma pads
  every message it sends to a multiple of 16 KB, so none ends on a short
  packet. Everything else (messages to the comma, and TCP both ways) gets one
  pad byte when a message's length is an exact multiple of 512 bytes (the
  USB 2 packet, which divides USB 3's), so a client speaks to every transport
  the same way and a link that fell back to USB 2 still ends every message.
- **Host reads.** Every USB host (usbfs on Linux and Android, IOKit on a Mac)
  keeps 32 reads of 16 KB posted on the comma's pipe, so a whole request
  streams without the server asking for the next piece, and hands the bytes
  over in the order the reads were posted. Since each message ends on the
  16 KB grid, a read never holds the end of one message while it waits for
  the next. A short packet means the stream left the grid, which only a
  broken stream does: the session ends and the comma reconnects.
- **Link power.** On Linux, USB 3 link power management is off on the comma's
  port while a session is served and the comma has sent something in the last
  30 s ([why](#bus-speed)).

Measured on the bench Jetson: [performance](status.md#measured-performance).

## Power requirements

Power the Jetson and comma separately. The Jetson's supply and cable must
deliver at least 25 W and tolerate voltage drops at engine start. **Always on**
or **Switched**: see the [power setup table](jetson.md#1-choose-your-power-setup).

### Recommended Jetson power setup

Orin Nano Super devkit: a **straight 12 V-to-DC barrel adapter** on a supply
that **stays on when the ignition is off** (such as an always-on 12 V accessory
socket), with Jetson **deep sleep** enabled.

<img src="images/jetson-12v-dc-adapter.jpg" width="320" alt="Example of a 12 V car accessory socket plug to DC barrel adapter cable">

- Plug: **5.5 mm outer / 2.5 mm inner, center-positive**. Check this when
  buying; the photo shows the style only. Other carrier boards may differ.
- Confirm the socket stays powered after ignition off, including after any
  delayed shutoff.
- Choose **Always on** in the installer for deep sleep; `jetlink setup` changes
  an existing setup.

<a id="always-on-supply-and-suspend"></a>

<a id="powering-off-with-the-comma"></a>

Parking, starting, and how battery-protection shutdown differs from sleep:
[Choose your power setup](jetson.md#1-choose-your-power-setup).

## TCP

The comma links over USB only (the plain gadget, or its network interface for
an iPhone). `jetlink-server --listen` tests a server without a comma: no client
authentication (trusted network only), and Wi-Fi misses the 50 ms frame budget.
See [test without a comma](platforms.md#test-without-a-comma).

<a id="custom-usb-integrations"></a>

Custom USB setups: [installation reference](installation-reference.md#custom-usb-integrations).
