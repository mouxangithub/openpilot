#!/usr/bin/env bash
set -e

MODE=""
UPSTREAM_BRANCH=""
CUSTOM_NAME=""
IS_20HZ="false"
OUTPUT_DIR=""
TINYGRAD_PATH=""
MODELS_DIR=""
MODEL_DATE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --upstream-branch)
      UPSTREAM_BRANCH="$2"
      shift 2
      ;;
    --custom-name)
      CUSTOM_NAME="$2"
      shift 2
      ;;
    --is-20hz)
      IS_20HZ="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --tinygrad-path)
      TINYGRAD_PATH="$2"
      shift 2
      ;;
    --models-dir)
      MODELS_DIR="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [ -z "$MODE" ]; then
  echo "Missing --mode argument (get_model or build_model)"
  exit 1
fi

if [ -z "$OUTPUT_DIR" ]; then
  echo "Missing --output-dir argument"
  exit 1
fi

if [ "$MODE" = "get_model" ]; then
  if [ -z "$UPSTREAM_BRANCH" ]; then
    echo "Missing --upstream-branch argument"
    exit 1
  fi

  WORKDIR="$(mktemp -d)"
  cd "$WORKDIR"

  echo "Cloning commaai/openpilot at $UPSTREAM_BRANCH..."
  if git clone --depth 1 --branch "$UPSTREAM_BRANCH" --recurse-submodules https://github.com/commaai/openpilot.git openpilot; then
    echo "Cloned commaai/openpilot"
  else
    echo "Falling back to sunnypilot/sunnypilot at $UPSTREAM_BRANCH..."
    git clone --depth 1 --branch "$UPSTREAM_BRANCH" --recurse-submodules https://github.com/sunnypilot/sunnypilot.git openpilot
  fi

  cd openpilot
  git lfs pull

  MODEL_DATE=$(git log -1 --format=%cd --date=format:'%B %d, %Y')
  echo "Commit date: $MODEL_DATE"

  MODEL_SRC="selfdrive/modeld/models"
  mkdir -p "$OUTPUT_DIR"
  cp $MODEL_SRC/*.onnx "$OUTPUT_DIR/" || echo "No ONNX models found."

  echo "$MODEL_DATE" > "$OUTPUT_DIR/commit_date.txt"
  echo "Done: Models copied to $OUTPUT_DIR"

elif [ "$MODE" = "build_model" ]; then
  if [ -z "$TINYGRAD_PATH" ]; then
    echo "Missing --tinygrad-path argument"
    exit 1
  fi
  if [ -z "$MODELS_DIR" ]; then
    echo "Missing --models-dir argument"
    exit 1
  fi

  # Compile models and generate metadata
  for onnx_file in "$MODELS_DIR"/*.onnx; do
    base_name=$(basename "$onnx_file" .onnx)
    output_file="${MODELS_DIR}/${base_name}_tinygrad.pkl"
    QCOM=1 python3 "${TINYGRAD_PATH}/examples/openpilot/compile3.py" "$onnx_file" "$output_file"
    QCOM=1 python3 "${MODELS_DIR}/../get_model_metadata.py" "$onnx_file" || true
  done

  sudo rm -rf "$OUTPUT_DIR"
  mkdir -p "$OUTPUT_DIR"
  rsync -avm \
    --include='*.dlc' \
    --include='*.thneed' \
    --include='*.pkl' \
    --include='*.onnx' \
    --exclude='*' \
    --delete-excluded \
    --chown=comma:comma \
    "$MODELS_DIR"/ "$OUTPUT_DIR"/

  python3 release/ci/model_generator.py \
    --model-dir "$MODELS_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --custom-name "$CUSTOM_NAME" \
    --upstream-branch "$UPSTREAM_BRANCH" \
    $( [ "$IS_20HZ" = "true" ] && echo "--is-20hz" )

  echo "Done: Model build and metadata generation complete."
else
  echo "Unknown mode: $MODE"
  exit 1
fi
