#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import os
import sys
import urllib.request
import zipfile

URL = "https://www.dolphindb.cn/downloads/docs/191_data.zip"
SRC_NAME = "datatest.csv"           # file name inside the archive
TARGET_NAME = "data_full.csv"   # file name written to disk after extraction
EXPECTED_SIZE = 177868443           # official data size in bytes, used for integrity check

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, TARGET_NAME)
ZIP_PATH = os.path.join(HERE, "191_data.zip")


def download(url, dest):
    print(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1048576:7.1f} / {total / 1048576:.1f} MB "
                      f"({done * 100 / total:5.1f}%)", end="", flush=True)
            else:
                print(f"\r  {done / 1048576:7.1f} MB", end="", flush=True)
    print()


def extract(zip_path, target):
    with zipfile.ZipFile(zip_path) as z:
        match = [n for n in z.namelist() if os.path.basename(n).lower() == SRC_NAME]
        if not match:
            raise RuntimeError(f"{SRC_NAME} not found in the archive, actual contents: {z.namelist()}")
        with z.open(match[0]) as src, open(target, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)


def main():
    ap = argparse.ArgumentParser(description="Download and extract GTJA191 market data")
    ap.add_argument("-f", "--force", action="store_true", help="re-download even if it already exists")
    args = ap.parse_args()

    if os.path.exists(CSV_PATH) and not args.force:
        print(f"already exists, skipping: {CSV_PATH}")
        print(f"  current size {os.path.getsize(CSV_PATH):,} bytes; add -f to re-download")
        return 0

    try:
        download(URL, ZIP_PATH)
    except Exception as e:
        print(f"[error] download failed: {e}", file=sys.stderr)
        print(f"you can download {URL} manually", file=sys.stderr)
        print(f"extract {SRC_NAME}, rename it to {TARGET_NAME}, put it in {HERE}, then retry.", file=sys.stderr)
        return 1

    try:
        extract(ZIP_PATH, CSV_PATH)
        print(f"extraction complete: {CSV_PATH}")
    except Exception as e:
        print(f"[error] extraction failed: {e}", file=sys.stderr)
        return 1
    finally:
        if os.path.exists(ZIP_PATH):
            os.remove(ZIP_PATH)
            print("removed temporary archive")

    size = os.path.getsize(CSV_PATH)
    print(f"size: {size:,} bytes")
    if size != EXPECTED_SIZE:
        print(f"[warning] does not match the expected {EXPECTED_SIZE:,} bytes; please verify the data version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
