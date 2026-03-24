#!/usr/bin/env bash
#
# Download wake word model files for the selected engine.
#
# Usage:
#   ./scripts/download-wake-word-models.sh sherpa-onnx    # Sherpa-ONNX KWS models
#   ./scripts/download-wake-word-models.sh openwakeword   # openWakeWord models
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
PUBLIC_DIR="$WEB_DIR/public"

# ---- Sherpa-ONNX KWS ----
download_sherpa_onnx() {
  local MODEL_DIR="$PUBLIC_DIR/models/sherpa-onnx-kws"
  local MODEL_NAME="sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
  local DOWNLOAD_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/${MODEL_NAME}.tar.bz2"
  local WASM_BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/wasm-kws-sherpa-onnx.js"

  mkdir -p "$MODEL_DIR"

  echo "==> Downloading sherpa-onnx KWS model: ${MODEL_NAME}..."
  local TMP_DIR
  TMP_DIR="$(mktemp -d)"
  trap "rm -rf '$TMP_DIR'" EXIT

  curl -L -o "$TMP_DIR/model.tar.bz2" "$DOWNLOAD_URL"
  echo "==> Extracting model files..."
  tar -xjf "$TMP_DIR/model.tar.bz2" -C "$TMP_DIR"

  # Copy int8 quantized models (smaller) or fp32 if int8 not available
  local SRC="$TMP_DIR/$MODEL_NAME"
  if [ -d "$SRC" ]; then
    # Try int8 first, fall back to fp32
    for pattern in "encoder*int8*onnx" "encoder*onnx"; do
      local found
      found=$(find "$SRC" -name "$pattern" -type f 2>/dev/null | head -1)
      if [ -n "$found" ]; then
        cp "$found" "$MODEL_DIR/encoder.onnx"
        break
      fi
    done

    for pattern in "decoder*onnx"; do
      local found
      found=$(find "$SRC" -name "$pattern" -type f 2>/dev/null | head -1)
      if [ -n "$found" ]; then
        cp "$found" "$MODEL_DIR/decoder.onnx"
        break
      fi
    done

    for pattern in "joiner*int8*onnx" "joiner*onnx"; do
      local found
      found=$(find "$SRC" -name "$pattern" -type f 2>/dev/null | head -1)
      if [ -n "$found" ]; then
        cp "$found" "$MODEL_DIR/joiner.onnx"
        break
      fi
    done

    # Copy tokens
    find "$SRC" -name "tokens.txt" -type f -exec cp {} "$MODEL_DIR/tokens.txt" \;

    # Copy or create keywords file
    local kw_file
    kw_file=$(find "$SRC" -name "keywords*.txt" -type f 2>/dev/null | head -1)
    if [ -n "$kw_file" ]; then
      cp "$kw_file" "$MODEL_DIR/keywords.txt"
    fi

    # Copy BPE model if present
    local bpe_file
    bpe_file=$(find "$SRC" -name "*.model" -type f 2>/dev/null | head -1)
    if [ -n "$bpe_file" ]; then
      cp "$bpe_file" "$MODEL_DIR/bpe.model"
    fi
  else
    echo "ERROR: Model directory not found after extraction"
    exit 1
  fi

  # Download WASM build files
  echo "==> Downloading sherpa-onnx WASM KWS build files..."
  echo "    Note: You may need to build these from source or download from a release."
  echo "    See: https://k2-fsa.github.io/sherpa/onnx/kws/index.html"

  echo ""
  echo "==> Model files downloaded to: $MODEL_DIR"
  ls -la "$MODEL_DIR"
  echo ""
  echo "NOTE: You also need the WASM build files in $MODEL_DIR:"
  echo "  - sherpa-onnx-kws.js"
  echo "  - sherpa-onnx-wasm-kws-main.js"
  echo "  - sherpa-onnx-wasm-kws-main.wasm"
  echo ""
  echo "These must be built from source or downloaded from a sherpa-onnx release."
  echo "See: https://github.com/k2-fsa/sherpa-onnx/tree/master/wasm/kws"
}

# ---- openWakeWord ----
download_openwakeword() {
  local MODEL_DIR="$PUBLIC_DIR/models/openwakeword"
  local BASE_URL="https://raw.githubusercontent.com/dscripka/openWakeWord/main/openwakeword/resources/models"

  mkdir -p "$MODEL_DIR"

  echo "==> Downloading openWakeWord shared models..."

  # Shared models
  curl -L -o "$MODEL_DIR/melspectrogram.onnx" \
    "$BASE_URL/melspectrogram.onnx"
  curl -L -o "$MODEL_DIR/embedding_model.onnx" \
    "$BASE_URL/embedding_model.onnx"

  # Silero VAD
  curl -L -o "$MODEL_DIR/silero_vad.onnx" \
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"

  echo "==> Downloading pre-trained keyword model: hey_jarvis..."
  curl -L -o "$MODEL_DIR/hey_jarvis_v0.1.onnx" \
    "$BASE_URL/hey_jarvis_v0.1.onnx"

  echo ""
  echo "==> Model files downloaded to: $MODEL_DIR"
  ls -la "$MODEL_DIR"
  echo ""
  echo "Available keywords: hey_jarvis"
  echo ""
  echo "To add more pre-trained keywords, download from:"
  echo "  $BASE_URL/<keyword>_v0.1.onnx"
  echo ""
  echo "To train a custom 'Hey Tank' model, see:"
  echo "  https://github.com/dscripka/openWakeWord#training-new-models"
}

# ---- Main ----
case "${1:-}" in
  sherpa-onnx)
    download_sherpa_onnx
    ;;
  openwakeword)
    download_openwakeword
    ;;
  *)
    echo "Usage: $0 <engine>"
    echo ""
    echo "Engines:"
    echo "  sherpa-onnx    Download Sherpa-ONNX KWS models (~5MB int8)"
    echo "  openwakeword   Download openWakeWord models (~40MB shared + ~200KB per keyword)"
    echo ""
    exit 1
    ;;
esac
