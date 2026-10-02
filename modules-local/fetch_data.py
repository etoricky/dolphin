#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载并解压 GTJA191 因子测试用的行情数据到本目录。

用法（在仓库根目录或任意位置执行都可以）：
    python modules-local/fetch_data.py       # 已有 datatest.csv 就跳过
    python modules-local/fetch_data.py -f    # 强制重新下载

数据来源：https://www.dolphindb.cn/downloads/docs/191_data.zip
解压后得到 modules-local/datatest.csv（约 170MB），临时 zip 会自动删除。

只有 `run.py 1`（建库 / 重建）需要这个 CSV；日常 `run.py 2/3/4` 不读它，
因为行情已经在 DolphinDB 的 dfs://gtja/market 里了。
"""
import argparse
import os
import sys
import urllib.request
import zipfile

URL = "https://www.dolphindb.cn/downloads/docs/191_data.zip"
TARGET_NAME = "datatest.csv"
EXPECTED_SIZE = 177868443          # 官方数据字节数，用于完整性校验

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, TARGET_NAME)
ZIP_PATH = os.path.join(HERE, "191_data.zip")


def download(url, dest):
    print(f"下载 {url}")
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
        match = [n for n in z.namelist() if os.path.basename(n).lower() == TARGET_NAME]
        if not match:
            raise RuntimeError(f"压缩包里找不到 {TARGET_NAME}，实际内容：{z.namelist()}")
        with z.open(match[0]) as src, open(target, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)


def main():
    ap = argparse.ArgumentParser(description="下载并解压 GTJA191 行情数据")
    ap.add_argument("-f", "--force", action="store_true", help="已存在也重新下载")
    args = ap.parse_args()

    if os.path.exists(CSV_PATH) and not args.force:
        print(f"已存在，跳过：{CSV_PATH}")
        print(f"  当前大小 {os.path.getsize(CSV_PATH):,} 字节；如需重新下载请加 -f")
        return 0

    try:
        download(URL, ZIP_PATH)
    except Exception as e:
        print(f"[错误] 下载失败：{e}", file=sys.stderr)
        print(f"可以手动下载 {URL}", file=sys.stderr)
        print(f"解压出 {TARGET_NAME} 后放到 {HERE} 再试。", file=sys.stderr)
        return 1

    try:
        extract(ZIP_PATH, CSV_PATH)
        print(f"解压完成：{CSV_PATH}")
    except Exception as e:
        print(f"[错误] 解压失败：{e}", file=sys.stderr)
        return 1
    finally:
        if os.path.exists(ZIP_PATH):
            os.remove(ZIP_PATH)
            print("已删除临时压缩包")

    size = os.path.getsize(CSV_PATH)
    print(f"大小：{size:,} 字节")
    if size != EXPECTED_SIZE:
        print(f"[警告] 与预期 {EXPECTED_SIZE:,} 字节不一致，请确认数据版本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
