# Performance and operating limits

Jetlink is experimental. If the link drops or lags while engaged, the comma
says **TAKE CONTROL** and stays engaged on the small model: be ready to take
over. See [daily use](using-jetlink.md).

<a id="status-and-known-limitations"></a>
<a id="platform-testing"></a>

Requirements: [Jetson](jetson.md), [Mac](macos-app.md),
[iPhone](iphone-app.md), [Android](android-app.md), [PC](platforms.md).
Tested on a Jetson with JetPack 7.2.1, on a Mac, and by users on Ubuntu PCs;
JetPack 6.2 and WSL2 are untested. The installer also supports Debian, Fedora,
Arch and openSUSE PCs, untested on hardware: each release's server is only
checked to load on them.

## Measured performance

Bench Jetson: Orin Nano Super 8 GB devkit, JetPack 7.2.1, TensorRT 10.16.2.10
(FP16), MAXN SUPER with `jetson_clocks` pinning the clocks (the installer runs
it before every start). comma four over USB 3 from the Jetson's USB-A port,
with its CPU as when driving. Measured 2026-09-28 and 29.

| Model | GPU time | Frame on the comma, p50 / p99: v0.6.0 | v0.7.0 |
| --- | ---: | ---: | ---: |
| Cinque Terre V3 (default), 766 MB | 16.4 ms | 28.9 / 30.7 ms | 24.5 / 25.8 ms |
| BMRLNAP v6, 766 MB | 15.7 ms | 29.3 / 31.5 ms | 24.2 / 25.6 ms |
| Lebowski, 1757 MB | 29.1 ms | 40.0 / 41.4 ms | 37.0 / 38.6 ms |

* GPU time: the engine's time on the GPU a frame, from CUDA events; the same
  in both servers within 0.3%. Cinque Terre V2 takes BMRLNAP's 15.7 ms.
* Frame on the comma: the big model's time a frame as the comma logs it
  (`modelExecutionTime`), parked, 120 to 180 s a run; the worst run's p50 and
  p99. The budget is 50 ms; Lebowski leaves the least margin.
* v0.7.0: 3 of 13,304 frames over 50 ms, each the first after a model swap.
* The v0.7.0 runs came after the bench Jetson's GPU started throttling on
  over-current following a power cycle (hardware, not Jetlink): 0.4 to 0.8 ms
  more GPU time on the 766 MB models, 3.1 ms on Lebowski (its frames then:
  40.5 / 41.7 ms). So Lebowski's row is the Swift server's run from before
  that, on the earlier link protocol; Lebowski's transport is the same on both
  within 0.2 ms.
* Sustained use at high temperatures is untested.

The servers side by side, on the same Jetson and the same engine files
(BMRLNAP v6 unless named):

| | v0.6.0 (Python) | v0.7.0 (Swift) |
| --- | ---: | ---: |
| USB transport a frame, mean / p99 | 8.6 / 11.8 ms | 2.1 / 4.5 ms |
| Reply to the comma | 74 KB | 8 KB |
| Staging the inputs a frame, mean | 0.77 ms | 0.47 ms |
| Server CPU while serving | 2.0 to 2.4% of a core | 1.0 to 1.4% |
| Free memory while Lebowski loads | 2.8 to 3.5 GB | 4.1 to 4.3 GB |
| Engine build, TensorRT's timing cache warm | 36.9 s | 36.0 s |

* v0.7.0 loads the engines v0.6.0 built, without a rebuild, and its outputs are
  the same bit for bit (64 frames with the hidden state fed back, on each of
  four models).
* Transport: the round trip minus the server's own time, from
  `scripts/bench_link.py` on the comma, in 1,200-frame blocks. v0.6.0 left USB 3
  link power management on; with it off, v0.6.0 measured 3.9 ms mean. v0.7.0
  with it on measures 4.2 ms p50, against 2.0 off.
* Building a model's engine took 168 to 179 s when TensorRT's timing cache had
  nothing for its layers, and 33 to 44 s when an earlier model had filled it
  (v0.6.0's builds; v0.7.0's take the same, above). A built engine loads in 1
  to 3 s. After a power-on, the engine loaded last was ready in 27 s.

Mac numbers: [Mac performance](mac-performance.md).

<a id="what-still-needs-validation"></a>

## Power and connection

* Use separate power supplies for the comma and server. Voltage drops can
  reboot the server and drop the link.
* Keep laptops powered, awake, and cooled.
* Power and sleep details: [power setup](transport.md#power-requirements).
* Link over USB. TCP is for testing only ([TCP](transport.md#tcp)).
