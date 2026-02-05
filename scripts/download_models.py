#!/usr/bin/env python3
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
MODEL_DIR = Path("models/sherpa-onnx-zipformer-en-zh")

def download_progress(block_num, block_size, total_size):
    read_so_far = block_num * block_size
    if total_size > 0:
        percent = read_so_far * 100 / total_size
        s = f"Downloading: {percent:5.1f}% [{read_so_far / 1024 / 1024:5.1f}MB / {total_size / 1024 / 1024:5.1f}MB]"
        sys.stdout.write(s)
        sys.stdout.flush()
    else:
        sys.stdout.write(f"Downloading: {read_so_far / 1024 / 1024:5.1f}MB")
        sys.stdout.flush()

def main():
    if MODEL_DIR.exists() and any(MODEL_DIR.iterdir()):
        print(f"Model already exists in {MODEL_DIR}. Skipping download.")
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = MODEL_DIR / "model.tar.bz2"

    print(f"Starting download from: {MODEL_URL}")
    try:
        urllib.request.urlretrieve(MODEL_URL, archive_path, download_progress)
        print("
Download complete. Extracting...")

        with tarfile.open(archive_path, "r:bz2") as tar:
            # Sherpa-onnx tarballs usually have a single top-level directory
            # We want to strip it to put files directly in MODEL_DIR
            members = tar.getmembers()
            top_dir = members[0].name.split('/')[0]
            
            for member in members:
                if member.name.startswith(top_dir + "/"):
                    member.name = member.name[len(top_dir)+1:]
                elif member.name == top_dir:
                    continue # Skip the top-level directory itself
                
                if member.name:
                    tar.extract(member, path=MODEL_DIR)

        print(f"Extraction complete. Model ready at {MODEL_DIR}")
    except Exception as e:
        print(f"
Error: {e}")
    finally:
        if archive_path.exists():
            archive_path.unlink()

if __name__ == "__main__":
    main()
