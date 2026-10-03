# -*- coding: utf-8 -*-
"""读取回测输出的 CSV，画出分层净值曲线。

用法:
    python plot.py ja1
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

# 让图上的中文正常显示（Windows 常见中文字体）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_nav(factor_id="ja1", show_ls=True):
    nav_path = os.path.join(config.OUTPUT_DIR, f"bt_{factor_id}_nav.csv")
    if not os.path.exists(nav_path):
        raise FileNotFoundError(f"{nav_path} 不存在，请先跑 backtest 步骤")

    nav = pd.read_csv(nav_path)
    nav["tradetime"] = pd.to_datetime(nav["tradetime"])
    wide = nav.pivot(index="tradetime", columns="bucket", values="nav")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    for bucket in wide.columns:
        ax.plot(wide.index, wide[bucket], label=f"bucket {int(bucket)}", linewidth=1.3)

    # 多空组合净值：多头（因子最大组）减空头（因子最小组），日频再平衡
    if show_ls and len(wide.columns) >= 2:
        r_top = wide[wide.columns[-1]].pct_change().fillna(0.0)
        r_bot = wide[wide.columns[0]].pct_change().fillna(0.0)
        ls = (1 + (r_top - r_bot)).cumprod()
        ax.plot(wide.index, ls, label="long-short (top - bottom)", color="black",
                linestyle="--", linewidth=1.3)

    ax.set_title(f"GTJA191 {factor_id} 分层净值 (bucket 0=因子最小, "
                 f"{len(wide.columns) - 1}=最大)")
    ax.set_xlabel("date")
    ax.set_ylabel("nav (start=1)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()

    out = os.path.join(config.OUTPUT_DIR, f"bt_{factor_id}_nav.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("chart saved:", out)
    return out


if __name__ == "__main__":
    plot_nav(sys.argv[1] if len(sys.argv) > 1 else "ja1")
