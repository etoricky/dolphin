# -*- coding: utf-8 -*-
"""Read the backtest output CSV and plot the quantile nav curves.

Usage:
    python plot.py ja1
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Render CJK text correctly on the chart (common Windows Chinese fonts)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot(alpha_id="ja1", show_ls=True, out_dir=None):
    if out_dir is None:                       # defaults to output/ next to this file
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    nav_path = os.path.join(out_dir, f"bt_{alpha_id}_nav.csv")
    if not os.path.exists(nav_path):
        raise FileNotFoundError(f"{nav_path} not found, please run the backtest01 action first")

    nav = pd.read_csv(nav_path)
    nav["tradetime"] = pd.to_datetime(nav["tradetime"])
    wide = nav.pivot(index="tradetime", columns="bucket", values="nav")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    for bucket in wide.columns:
        ax.plot(wide.index, wide[bucket], label=f"bucket {int(bucket)}", linewidth=1.3)

    # Long-short portfolio nav: long (largest factor group) minus short (smallest factor group), daily rebalanced
    if show_ls and len(wide.columns) >= 2:
        r_top = wide[wide.columns[-1]].pct_change().fillna(0.0)
        r_bot = wide[wide.columns[0]].pct_change().fillna(0.0)
        ls = (1 + (r_top - r_bot)).cumprod()
        ax.plot(wide.index, ls, label="long-short (top - bottom)", color="black",
                linestyle="--", linewidth=1.3)

    ax.set_title(f"GTJA191 {alpha_id} quantile nav (bucket 0=smallest, "
                 f"{len(wide.columns) - 1}=largest)")
    ax.set_xlabel("date")
    ax.set_ylabel("nav (start=1)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()

    out = os.path.join(out_dir, f"bt_{alpha_id}_nav.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("chart saved:", out)
    return out


if __name__ == "__main__":
    plot(sys.argv[1] if len(sys.argv) > 1 else "ja1")
