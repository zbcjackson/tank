#!/usr/bin/env bash
#
# Build sherpa-onnx WASM KWS artifacts from source and install them.
#
# This script:
#   1. Clones emsdk + sherpa-onnx into a temporary directory
#   2. Installs Emscripten (isolated — does NOT modify your PATH or shell profile)
#   3. Downloads the bilingual zh+en KWS model
#   4. Builds the WASM KWS module
#   5. Copies artifacts to web/public/models/sherpa-onnx-kws/
#   6. Removes the temporary directory
#
# Usage:
#   ./scripts/build-sherpa-onnx-kws.sh
#
# Requirements:
#   - git, curl, cmake, tar
#   - ~2GB disk during build (cleaned up afterward)
#   - ~27MB output (4 files in public/models/sherpa-onnx-kws/)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$WEB_DIR/public/models/sherpa-onnx-kws"

MODEL_NAME="sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
MODEL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/${MODEL_NAME}.tar.bz2"

# ---- Preflight checks ----
for cmd in git curl cmake tar; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not found. Please install it first."
    exit 1
  fi
done

# ---- Create isolated temp directory ----
BUILD_DIR="$(mktemp -d)"
echo "==> Build directory: $BUILD_DIR"
echo "    (will be removed on exit)"

cleanup() {
  echo "==> Cleaning up build directory..."
  rm -rf "$BUILD_DIR"
  echo "    Done."
}
trap cleanup EXIT

# ---- Clone emsdk (isolated, not added to user's PATH) ----
echo ""
echo "==> Cloning Emscripten SDK..."
git clone --depth 1 https://github.com/emscripten-core/emsdk.git "$BUILD_DIR/emsdk" 2>&1 | tail -1

echo "==> Installing Emscripten..."
(
  cd "$BUILD_DIR/emsdk"
  ./emsdk install latest 2>&1 | grep -E "^(Installing|Done)"
  ./emsdk activate latest 2>&1 | tail -1
)

# Source emsdk_env.sh in a subshell-safe way — only sets vars for this script
EMSDK_QUIET=1 source "$BUILD_DIR/emsdk/emsdk_env.sh" 2>/dev/null

echo "    emcc version: $(emcc --version 2>&1 | head -1)"

# ---- Clone sherpa-onnx ----
echo ""
echo "==> Cloning sherpa-onnx (shallow)..."
git clone --depth 1 https://github.com/k2-fsa/sherpa-onnx.git "$BUILD_DIR/sherpa-onnx" 2>&1 | tail -1

# ---- Download KWS model ----
echo ""
echo "==> Downloading bilingual zh+en KWS model..."
curl -L --progress-bar -o "$BUILD_DIR/model.tar.bz2" "$MODEL_URL"

echo "==> Extracting model..."
tar -xjf "$BUILD_DIR/model.tar.bz2" -C "$BUILD_DIR"

# ---- Copy model files into wasm/kws/assets/ with expected names ----
# The CMakeLists.txt checks for epoch-12 filenames; the zh-en model uses epoch-13.
# We rename to match the expected names.
ASSETS_DIR="$BUILD_DIR/sherpa-onnx/wasm/kws/assets"
MODEL_DIR="$BUILD_DIR/$MODEL_NAME"

cp "$MODEL_DIR/encoder-epoch-13-avg-2-chunk-16-left-64.onnx" \
   "$ASSETS_DIR/encoder-epoch-12-avg-2-chunk-16-left-64.onnx"
cp "$MODEL_DIR/decoder-epoch-13-avg-2-chunk-16-left-64.onnx" \
   "$ASSETS_DIR/decoder-epoch-12-avg-2-chunk-16-left-64.onnx"
cp "$MODEL_DIR/joiner-epoch-13-avg-2-chunk-16-left-64.onnx" \
   "$ASSETS_DIR/joiner-epoch-12-avg-2-chunk-16-left-64.onnx"
cp "$MODEL_DIR/tokens.txt" "$ASSETS_DIR/tokens.txt"
cp "$MODEL_DIR/en.phone"   "$ASSETS_DIR/en.phone"

echo "    Model files placed in assets/"

# ---- Build WASM KWS ----
echo ""
echo "==> Building WASM KWS (this takes a few minutes)..."
(
  cd "$BUILD_DIR/sherpa-onnx"
  ./build-wasm-simd-kws.sh 2>&1 | tail -5
)

# ---- Verify build output ----
WASM_OUT="$BUILD_DIR/sherpa-onnx/build-wasm-simd-kws/install/bin/wasm"
for f in sherpa-onnx-kws.js sherpa-onnx-wasm-kws-main.js sherpa-onnx-wasm-kws-main.wasm sherpa-onnx-wasm-kws-main.data; do
  if [ ! -f "$WASM_OUT/$f" ]; then
    echo "ERROR: Expected build output not found: $f"
    exit 1
  fi
done

echo "    Build succeeded."

# ---- Copy artifacts to web/public/models/sherpa-onnx-kws/ ----
echo ""
echo "==> Installing artifacts to $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

cp "$WASM_OUT/sherpa-onnx-kws.js"              "$OUTPUT_DIR/"
cp "$WASM_OUT/sherpa-onnx-wasm-kws-main.js"    "$OUTPUT_DIR/"
cp "$WASM_OUT/sherpa-onnx-wasm-kws-main.wasm"  "$OUTPUT_DIR/"
cp "$WASM_OUT/sherpa-onnx-wasm-kws-main.data"  "$OUTPUT_DIR/"

echo ""
echo "==> Done! Artifacts installed:"
ls -lh "$OUTPUT_DIR/"
echo ""
echo "To use: set VITE_WAKE_WORD_ENGINE=sherpa-onnx in web/.env"
