# Mac performance measurements

Backend choice and requirements: [backends](backends.md). This page: the
measurements and implementation details behind the Mac defaults.

Setup: 16 GB M1 Pro, macOS 26.5, ONNX Runtime 1.29.0, the 766 MB Cinque Terre
V3 (`404a18cfd86d2963`) and V2 (`09d080f36965bb2a`) models. Other Macs may
differ.

Frame budget: 50 ms (20 Hz). The default runs the vision layers on the Neural
Engine and the rest on the GPU. `--device coreml` runs everything on the GPU:
slower, but use it if another app keeps the Neural Engine busy (the default
assumes Jetlink has it alone).

| | Default: Neural Engine and GPU | GPU only (`--device coreml`) |
| --- | ---: | ---: |
| V3 round trip at 20 Hz through the server, mean / p99 / max | 30.6 / 33.8 to 34.8 / 40.1 ms | 43.7 / 44.5 to 45.0 / 52.1 ms |
| V2 round trip at 20 Hz through the server, mean / p99 / max | 30.7 / 32.1 to 37.2 / 39.7 ms | 41.5 / 41.7 to 50.2 / 73.3 ms |
| frames over the 50 ms budget | V3 0 of 1,740, V2 0 of 1,160 | V3 1 of 1,160, V2 9 of 1,160 |
| parity gate, worst column (V3 / V2) | 0.99957 / 0.99957 pass | V2 0.99957 pass |
| build / load in a fresh process | about 20 s / 0.6 to 11 s | about 10 s / 1.8 to 4.7 s |
| artifact on disk | 2.1 GB | 2.3 GB |

- Measured 2026-09-26 on the Python server Jetlink ran then, with the same
  prepared graphs and CoreML provider; the Swift server is about 1 ms faster
  (below).
- 300-frame blocks, alternating with the code before the change measured: six
  blocks for the default on V3, four for the rest. The p99 is the range over
  blocks.
- Another process was busy throughout. It got busier in the last GPU-only V2
  block (43.6 ms mean, 7 frames over), most of that column's p99 range and
  misses; the other three blocks ran 40.8 to 41.0 ms.
- Default load: under 1 s when the same model was loaded last, 5 to 11 s after
  another (macOS prepares the Neural Engine part again).
- Mean: average frame. p99: 99% of frames at or below. Max: slowest frame.

<a id="the-python-server-and-the-swift-server"></a>

## The Swift server

2026-09-27, same M1 Pro, Cinque Terre V3, default split,
`bench_link.py --rate 20 --n 1200` over TCP loopback:

| Run | round trip p50 / p99 / max | server-side total | over 50 ms |
| --- | ---: | ---: | ---: |
| Swift 1 | 29.81 / 33.51 / 36.90 ms | 28.87 ms | 0 of 1,190 |
| Swift 2 | 30.14 / 33.90 / 34.76 ms | 29.06 ms | 0 of 1,190 |
| Python, clean run, for comparison | 31.03 / 34.54 / 45.07 ms | 29.92 ms | 0 of 1,190 |

- Loopback TCP adds about 1.4 ms to both.
- The release-built app served the same model at 29.83 ms p50, 32.87 ms p99 and
  33.70 ms max, none of 190 frames over 50 ms, loading the engine in 9.2 s.

Over USB, 2026-09-27, comma four, the Jetlink 0.4.3 app (Python server, Neural
Engine), this M1 Pro, parked live bench (big model frame times as the comma
sees them):

| Cable | p50 | p99 | Dropped |
| --- | ---: | ---: | ---: |
| USB 3 C-to-C | 36.9 ms | 45.7 ms | 0 |
| USB 2 C-to-C | 46.7 ms | 54.3 ms | 0.88% |

Not yet measured: the Swift server over USB (the gate: p99 no worse, no frame
dropped). To run it, plug the comma into the Mac with the app serving, and on
the parked comma run `jetlink_repo/scripts/comma/jetlink_live_bench.sh 180`.

## How the default runs

`--device ane`, the default:

- The convolutional trunk (reads the camera frames) runs on the Neural Engine in
  about 20 ms (GPU: 31 ms); everything after it runs on the GPU.
- Every model is cut where the trunk ends and run as two CoreML sessions
  exchanging 32 KB per frame (V3's policy and history; V2's policy with the
  history the server keeps).
- V3's history stays in the engine: onnxruntime double-buffers it, so each
  frame's outputs become the next frame's inputs without a copy.

Against one session with every compute unit, mean / p99 in ms at 20 Hz,
interleaved on 2026-09-25:

| | V3 | V2 |
| --- | ---: | ---: |
| two sessions, trunk on the Neural Engine | **32.2 / 36.6** | 29.7 / 33.5 |
| one session, every compute unit | 114.8 / 123.2 | 28.6 / 31.5 |
| GPU only | 43.1 / 44.7 | 43.6 / 46.2 |

- One session is unusable on V3: the Neural Engine cannot run its stateful
  policy efficiently.
- On V2 it was about 1 ms faster, but only with the policy's
  LayerNormalizations forced to fp32 (off the Neural Engine) and one CPU core
  spinning for CoreML each frame. Jetlink uses two sessions for both models, to
  support V3 consistently.
- One session is `--device ane-whole`, for A/B runs against the default
  ([backends](backends.md#runtime-comparison)).
- The cut also keeps the Neural Engine's fp16 LayerNormalization out of the
  layers after the trunk: with them on the Neural Engine, `road_transform` fell
  to a correlation of 0.9988 over 32 frames and failed the parity gate.

Every CoreML build, GPU-only too:

- rewrites two Expand operations CoreML will not take as the equivalent Tiles,
  so the policy stays one CoreML program instead of two with a CPU step between
  (worth 3.7 ms mean and 9 ms p99 on the default with V3; with FastPrediction,
  3.8 ms mean GPU-only with V2);
- asks CoreML for its FastPrediction specialization.

The default runs the Metal keep-alive (below) for its GPU half; without it the
split measured 46.4 ms mean, 53.5 ms p99.

Other apps on the Neural Engine slow the default: with another process running
a model on it back to back, the split measured 52.5 ms mean and 65 ms p99, GPU
only 43.5 ms. Then use `--device coreml` (**CoreML on the GPU** in the Mac app).

## How to measure

| Tool | Does |
| --- | --- |
| `scripts/verify_parity.py` | compares 32 frames against ONNX Runtime on the CPU, with the model's hidden-state feedback; passes when every output slice and column has a correlation of at least 0.999 |
| `scripts/bench_link.py --rate 20` | round-trip latency through the server over TCP loopback; use 20 Hz results for the driving frame budget ([test without a comma](platforms.md#test-without-a-comma)) |
| `jetlink-server bench` | runs a prepared engine at the comma's pace with no comma and no link, and reports its times |
| `scripts/comma/jetlink_live_bench.sh` | on the comma: the big model's frame times as the car sees them |
| `scripts/comma/jetlink_replay.py` | on the comma: replays a recorded segment through the real modeld on the accelerator |

## Keeping the Mac GPU responsive between frames

CoreML's GPU path runs a small Metal keep-alive workload while inference
requests arrive. On an M2 Pro, the gaps in a 20 Hz stream let GPU clocks fall
although continuous inference met the 50 ms deadline, at nominal thermal
pressure. A similar problem and workaround:
[Anukari's development report](https://anukari.com/blog/devlog/apple-performance-progress).

M2 Pro, ONNX Runtime 1.29.0, model `09d080f36965bb2a`, five-minute TCP loopback
runs at 20 Hz on 2026-09-21, ten warm-up frames excluded:

| | Original run | With keep-alive |
| --- | ---: | ---: |
| mean round trip | 44.13 ms | 35.41 ms |
| p99 round trip | 64.66 ms | 38.62 ms |
| maximum round trip | 83.57 ms | 70.20 ms |
| frames exceeding 50 ms | 1,119 / 5,990 (18.68%) | 3 / 5,990 (0.05%) |

- With keep-alive, every 30 s window had a mean under 35.6 ms and p99 under
  39 ms; three isolated misses remained. Desktop TCP, not USB end to end.
- A later 90 s control run with the helper disabled missed 498 of 1,790
  deadlines (27.82%), p99 69.10 ms.
- The first 32 recurrent frames were bit-identical with the helper on and off.

The helper:

- uses its own 128-byte buffer, one finite command in flight at a time, on its
  own thread;
- does not change model inputs, hidden state, precision, or CoreML compute
  units;
- stops after one second without an inference request;
- runs whenever a session uses the GPU, the default's GPU half included; CPU
  sessions do not start it;
- if Metal cannot start it, inference continues without it.

It trades GPU activity and power for latency; it does not change thermal limits
or force a GPU clock. `--no-keepalive` turns it off for comparison:

```bash
JetlinkKit/.build/release/jetlink-server --listen --host 127.0.0.1 --device coreml --no-keepalive
```

Compare with the same model and a sustained paced benchmark
(`--rate 20 --n 6000`); a continuous one (`--rate 0`) does not show whether the
server meets deadlines with pauses between frames. Results depend on hardware
and competing load; measure on the target machine.

## Model preparation

- CoreML stores weights in a binary file.
- GPU model on the M1 Pro: about 2.3 GB, 8 s to build, 2 s to load.
- The default also normalizes negative Gather indices (the Neural Engine
  mishandles them) and splits after the trunk (above); about 20 s to build.
- A CoreML engine prepared by an earlier Jetlink is rebuilt automatically.
