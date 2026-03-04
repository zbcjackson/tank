#!/usr/bin/env python3
"""Download sherpa-onnx models for ASR and speaker identification."""

import argparse
import sys
import tarfile
import urllib.request
from pathlib import Path

# --- ASR model ---
ASR_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
)
ASR_DIR = Path("models/sherpa-onnx-zipformer-en-zh")

# --- Speaker embedding models ---
SPEAKER_BASE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models"
)
SPEAKER_DIR = Path("models/speaker")

SPEAKER_MODELS = {
    # 3D-Speaker (Alibaba) — Chinese + English
    "3dspeaker-zh": {
        "file": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        "size_mb": 37.8,
        "desc": "3D-Speaker ERes2Net base, zh-cn, 192-dim (recommended)",
    },
    "3dspeaker-zh-common": {
        "file": "3dspeaker_speech_eres2net_base_200k_sv_zh-cn_16k-common.onnx",
        "size_mb": 37.8,
        "desc": "3D-Speaker ERes2Net base 200k, zh-cn, 192-dim",
    },
    "3dspeaker-en": {
        "file": "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
        "size_mb": 25.3,
        "desc": "3D-Speaker ERes2Net, English (VoxCeleb), 192-dim",
    },
    "3dspeaker-campplus-zh-en": {
        "file": "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        "size_mb": 27.0,
        "desc": "3D-Speaker CAM++, zh+en advanced, 192-dim",
    },
    # WeSpeaker — English
    "wespeaker-en": {
        "file": "wespeaker_en_voxceleb_resnet34.onnx",
        "size_mb": 25.3,
        "desc": "WeSpeaker ResNet34, English (VoxCeleb), 256-dim",
    },
    # WeSpeaker — Chinese
    "wespeaker-zh": {
        "file": "wespeaker_zh_cnceleb_resnet34.onnx",
        "size_mb": 25.3,
        "desc": "WeSpeaker ResNet34, Chinese (CNCeleb), 256-dim",
    },
}

DEFAULT_SPEAKER_MODEL = "3dspeaker-zh"


def download_progress(block_num: int, block_size: int, total_size: int) -> None:
    """Print download progress."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(downloaded * 100 / total_size, 100)
        bar_len = 30
        filled = int(bar_len * percent / 100)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(
            f"\r  [{bar}] {percent:5.1f}%  "
            f"{downloaded / 1024 / 1024:.1f} / {total_size / 1024 / 1024:.1f} MB"
        )
    else:
        sys.stdout.write(f"\r  Downloaded: {downloaded / 1024 / 1024:.1f} MB")
    sys.stdout.flush()


def download_file(url: str, dest: Path) -> None:
    """Download a file with progress display."""
    print(f"  URL: {url}")
    urllib.request.urlretrieve(url, dest, download_progress)
    print()  # newline after progress bar


def download_asr() -> None:
    """Download the ASR (streaming zipformer) model."""
    print("\n--- ASR Model (streaming zipformer bilingual zh-en) ---")

    if ASR_DIR.exists() and any(ASR_DIR.iterdir()):
        print(f"  Already exists: {ASR_DIR}. Skipping.")
        return

    ASR_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ASR_DIR / "model.tar.bz2"

    try:
        download_file(ASR_URL, archive_path)
        print("  Extracting...")

        with tarfile.open(archive_path, "r:bz2") as tar:
            members = tar.getmembers()
            top_dir = members[0].name.split("/")[0]

            for member in members:
                if member.name.startswith(top_dir + "/"):
                    member.name = member.name[len(top_dir) + 1 :]
                elif member.name == top_dir:
                    continue
                if member.name:
                    tar.extract(member, path=ASR_DIR)

        print(f"  Ready: {ASR_DIR}")
    except Exception as e:
        print(f"\n  Error: {e}", file=sys.stderr)
    finally:
        if archive_path.exists():
            archive_path.unlink()


def download_speaker(model_key: str) -> None:
    """Download a speaker embedding model."""
    if model_key not in SPEAKER_MODELS:
        print(f"  Unknown model: {model_key}", file=sys.stderr)
        print(f"  Available: {', '.join(SPEAKER_MODELS)}")
        sys.exit(1)

    info = SPEAKER_MODELS[model_key]
    filename = info["file"]
    dest = SPEAKER_DIR / filename

    print(f"\n--- Speaker Model: {model_key} ---")
    print(f"  {info['desc']}")
    print(f"  Size: ~{info['size_mb']:.0f} MB")

    if dest.exists():
        print(f"  Already exists: {dest}. Skipping.")
        return

    SPEAKER_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{SPEAKER_BASE_URL}/{filename}"

    try:
        download_file(url, dest)
        print(f"  Ready: {dest}")
    except Exception as e:
        print(f"\n  Error: {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()


def list_speaker_models() -> None:
    """Print available speaker models."""
    print("\nAvailable speaker embedding models:\n")
    print(f"  {'Key':<28} {'Size':>8}  Description")
    print(f"  {'-' * 28} {'-' * 8}  {'-' * 50}")
    for key, info in SPEAKER_MODELS.items():
        marker = " *" if key == DEFAULT_SPEAKER_MODEL else ""
        print(f"  {key:<28} {info['size_mb']:>6.0f}MB  {info['desc']}{marker}")
    print("\n  * = default (use --speaker-model to choose another)")


def main():
    parser = argparse.ArgumentParser(
        description="Download sherpa-onnx models for ASR and speaker identification."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        choices=["asr", "speaker", "all"],
        help="Which models to download (default: asr)",
    )
    parser.add_argument(
        "--speaker-model",
        default=DEFAULT_SPEAKER_MODEL,
        help=f"Speaker model key (default: {DEFAULT_SPEAKER_MODEL}). "
        "Use --list-speaker-models to see options.",
    )
    parser.add_argument(
        "--list-speaker-models",
        action="store_true",
        help="List available speaker models and exit.",
    )
    args = parser.parse_args()

    if args.list_speaker_models:
        list_speaker_models()
        return

    targets = set(args.targets) if args.targets else {"asr"}
    if "all" in targets:
        targets = {"asr", "speaker"}

    if "asr" in targets:
        download_asr()

    if "speaker" in targets:
        download_speaker(args.speaker_model)

    print("\nDone.")


if __name__ == "__main__":
    main()
