# Traffic-light YOLOv8 detector trial (stage 1 and 2)

**Date:** 2026-10-28
**Model:** `yolov8n`, 6 classes, 50 epochs, exported to ONNX at 416x416
**Status:** observation only. The detector holds no control permission and is
not wired into the driving path.

## What was built

| Piece | Path | Role |
|-------|------|------|
| Detector | `openpilot/sunnypilot/carrot/signal_yolo_detector.py` | Pure detection: housing boxes, lamp boxes, colour state. No messaging, no Params, no control. |
| Observer | `openpilot/selfdrive/modeld/signal_yolo_shadow.py` | Device worker. Reads the road camera, publishes observations to a tmpfs transport. Opt-in via a file on disk. |
| Model | `openpilot/sunnypilot/assets/vision_models/signal_light_detector.onnx` | 12,172,446 B, sha256 `7fdf89728e86d33e8d4d67902c10804762301cc8c3dc2f28ee168adad5b893fd` |
| Accuracy harness | `tools/signal_analysis/eval_signal_yolo.py` | Offline precision/recall/mAP and the housing-level colour agreement. |

Stage 3 (replacing or fusing the observer into `SignalAssist`'s control path)
is **not** implemented. It waits for an explicit decision.

## The shape of the output

The detector returns two levels, matching how the dataset is annotated: a
`traffic_light` box for the housing, and one box per lit lamp inside it. The
housing is the unit a consumer tracks; the lamp is the colour evidence
attached to it.

Colour evidence is conservative by construction:

- a lamp only counts for a housing that **contains** it (>= 55% of the lamp box
  area inside the housing box);
- a housing whose lamps disagree (a red and a green at once) is `unknown`;
- yellow is never a red and never a green;
- the turn-arrow classes (`left_light`, `right_light`) are never a plain
  colour, because an arrow is not evidence about the lane the ego is in;
- a lamp that no housing contains is dropped - without a housing there is no
  unit to track.

`right_light` has 4 training instances and 0 in the validation split. It is
effectively untrained and should not be trusted.

## Accuracy on the labelled data

Measured with `tools/signal_analysis/eval_signal_yolo.py` over
`D:\迅雷下载\datasets` (432 train / 108 val images, 640x640, YOLO labels),
input 416x416, confidence threshold 0.25.

### Box detection

| Split | Precision | Recall | mAP50 |
|-------|-----------|--------|-------|
| val (108 images, 409 boxes) | 0.976 | 0.978 | 0.963 |
| train (432 images, 1637 boxes) | 0.981 | 0.943 | 0.921 |

### Housing-level colour state

This is the number that matters downstream, because it is what a consumer
would act on. For every annotated housing, the predicted housing that overlaps
it most is taken as the detector's answer, and its colour state is compared
with the colour the annotation implies.

| Split | Housings | Agreed | Wrong | Missed | State accuracy |
|-------|----------|--------|-------|--------|----------------|
| val | 191 | red 100, green 45, unknown 36 | 9 | 1 | **0.9476** |
| train | 743 | red 394, green 163, unknown 118 | 55 | 13 | **0.9085** |

Broken down, the errors are:

| Error | val | train | Direction |
|-------|-----|-------|-----------|
| `unknown_instead_of_red` | 8 | 45 | fails safe |
| `unknown_instead_of_green` | 0 | 7 | fails safe |
| `claimed_red_for_unknown` | 1 | 3 | the unsafe direction |

The residual errors are almost entirely **missed small or distant lamps** -
the housing is found but its lamp is not, so the state stays `unknown`. That
fails safe: an unknown signal never becomes a red.

The genuinely unsafe error - claiming a colour the annotation does not
support - is **4 out of 934 housings (0.4%)**, and all four are
`claimed_red_for_unknown`, i.e. a yellow or unlit signal read as red.

## The input geometry matters more than anything else

The model was trained on plain 640x640 **squashes** of wider frames. Feeding
the device's 1344x760 frame the way the training frames were built, versus
letterboxing it into the square, is worth 14 accuracy points:

| Input path | State accuracy (train+val) | False colour | Missed |
|------------|----------------------------|--------------|--------|
| Squashed to 416x416 (as trained) | **0.9176** | 4 | 14 |
| Letterboxed into 416x416 | 0.7773 | 6 | 98 |

Letterboxing spends most of the square on grey padding, so the network sees a
much smaller image than it was trained on. The detector therefore **squashes**
the frame, and maps the boxes back with the per-axis scale, so the consumer
only ever sees road-image coordinates.

The confidence threshold was swept the same way. 0.25 beats 0.35 (0.9176 vs
0.8994 state accuracy, same false-colour count, 4 fewer missed housings), so
0.25 is the shipped value.

## Cost

One 416x416 forward on this machine:

| Backend | Time |
|---------|------|
| OpenCV DNN | 69 ms |
| ONNX Runtime | 122 ms |

OpenCV's DNN backend is used because it is already a dependency of this fork
and it is cheaper here. The two backends produce the same detections once the
preprocessing matches (max absolute difference 0.002 over the validation
frames), so the choice costs nothing in accuracy.

The observer runs at up to **2 Hz** with a bounded CPU duty (a forward costs
~120 ms on the C3's little cores, so ``next_delay``'s 3x-CPU floor
auto-throttles toward ~1 Hz on slower devices while never exceeding ~25% of
one little core). It is pinned to the little cores at the lowest priority.

## Using it on a device

```sh
# install the model and its manifest
python -m openpilot.selfdrive.modeld.signal_yolo_shadow install

# enable the observer (it stays off until this file exists)
python -m openpilot.selfdrive.modeld.signal_yolo_shadow on

# status
python -m openpilot.selfdrive.modeld.signal_yolo_shadow status
```

The observer refuses to start unless:

- the manifest says `mode: camera_comparison_only` and
  `control_permission: false`;
- the model's sha256 matches the pinned digest;
- the road camera is 1344x760 (comma 3X / mici, OS04C10) or 1928x1208
  (comma 3 / tici, OX03C10). Both records are self-describing (they carry
  their own size and per-axis box mapping); any other geometry is refused
  rather than guessed. An unexpected crash now exits nonzero so the manager's
  restart re-validates the artifact — a fixed or reinstalled model is picked
  up without an ignition cycle.

Observations are written to `/dev/shm/carrot_signal_yolo_observation.json` -
a **separate** file from the classical observer's transport, so the two
producers cannot fight over the same path. Housings keep their ids across
frames through a greedy IoU tracker (`HousingTracker`), so a consumer can
tell "the same housing, still red" from "a new housing"; only current-frame
tracks are published (`age` stays 0), and a track unseen for more than
`max_age` frames is forgotten.

The signal HUD (`SignalHudRenderer`) draws a small **observer dot** to the
right of the planner-evidence ring whenever the observer is enabled and a
fresh record carries an agreed red or green reading. It is display only,
independent of the `SignalAssistMode` ring gate, and paints the direct palette
colour (no amber swap) so it can never be mistaken for the planner's evidence.

## Limitations

- The dataset is small (540 images) and its traffic lights are mostly
  straight-on and near. Behaviour on oblique, distant, occluded or adverse-
  weather signals is not measured.
- `right_light` is effectively untrained.
- The 91.8% squash accuracy was measured on 1344x760 frames; the comma 3's
  1928x1208 has a different aspect ratio (1.60 vs 1.77) and must be re-evaluated
  on-device (`tools/signal_analysis/eval_signal_yolo.py`) before any
  precision claim carries over.
- The colour read is per-frame with no temporal confirmation of its own. A
  consumer that needs stability must add it; the existing `SignalAssist`
  already does this for the classical observer.
- Raw camera colour differs from encoded-video colour. The device path was
  validated on the dataset, not on raw NV12 frames from a real camera.
