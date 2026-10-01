# -*- coding: utf-8 -*-
"""统一入口：连接 DolphinDB 并执行 scripts/ 下的步骤脚本。

因子公式来自「客户端」的 modules-local/ 目录，由 loader.py 在会话建立后
注入到服务端执行（不再使用服务端的 `use`）。

用法:
    python run.py 1          # 建库 + 导入行情
    python run.py 2          # 计算并落库 GTJA191 因子
    python run.py 3          # 横截面分层回测
    python run.py 4 [ja1]    # 画分层净值曲线（默认因子 ja1）
    python run.py all        # 依次执行 1 -> 2 -> 3 -> 4
"""
import os
import sys

import config
import loader
from ddb import connect, run_file, show

# 步骤号 -> DolphinDB 脚本
STEPS = {
    "1": "01_create_market_db.dos",
    "2": "02_calc_factors.dos",
    "3": "03_backtest.dos",
}

_sess = None


def get_session():
    """建立会话，并把客户端本地模块注入进去。"""
    global _sess
    if _sess is not None:
        return _sess

    _sess = connect()
    print(f"connected to {config.HOST}:{config.PORT} (admin)")
    try:
        n = loader.load_modules(_sess, config.LOCAL_MODULES)
        print(f"injected client-side modules from {config.MODULES_LOCAL} ({n} chars)")
    except FileNotFoundError as e:
        print(f"[warn] 本地模块目录缺失，跳过注入: {e}")
    return _sess


def run_dos_step(sess, key, factor_id=None):
    name = STEPS[key]
    preamble = ""
    if key == "3" and factor_id:
        preamble = f'factorId = "{factor_id}";\n'
    res = run_file(sess, name, preamble)
    show(res, f"result of step {key} ({name})")


def run_plot_step(factor_id="ja1"):
    from plot import plot_nav
    print(f"\n===== plotting factor {factor_id} =====")
    plot_nav(factor_id)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        print("可用步骤:", ", ".join(list(STEPS) + ["4", "all"]))
        return

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if args[0] == "all":
        for key in sorted(STEPS):
            run_dos_step(get_session(), key)
        run_plot_step("ja1")
        return

    # 参数里属于步骤号的执行，其余当作因子号（给回测/绘图用）
    non_steps = [a for a in args if a not in STEPS and a != "4"]
    factor_id = non_steps[0] if non_steps else "ja1"
    for key in args:
        if key in STEPS:
            run_dos_step(get_session(), key, factor_id)
        elif key == "4":
            run_plot_step(factor_id)


if __name__ == "__main__":
    main()
