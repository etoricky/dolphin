# -*- coding: utf-8 -*-
"""统一入口：连接 DolphinDB 并执行 scripts/ 下的步骤脚本。

因子公式来自「客户端」的 modules-local/ 目录，由 loader.py 在会话建立后
注入到服务端执行（不再使用服务端的 `use`）。

用法:
    python run.py 1                     # 建库 + 导入行情（已存在则跳过）
    python run.py 1 RECREATE=true       # 强制删库重建并重新导入
    python run.py 2                     # 计算并落库 GTJA191 因子（默认重建因子表）
    python run.py 2 REBUILD_FACTOR=false # 复用因子表，只补算还没算过的因子
    python run.py 3 [ja1]               # 横截面分层回测
    python run.py 4 [ja1]               # 画分层净值曲线
    python run.py all                   # 依次执行 1 -> 2 -> 3 -> 4

    形如 KEY=VALUE 的参数会作为变量注入到 DolphinDB 脚本最前面，
    用来覆盖脚本里的默认配置。
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


def build_preamble(key, factor_id, overrides):
    """把命令行参数变成 DolphinDB 变量赋值，拼在脚本最前面。"""
    lines = [ov + ";" for ov in overrides]
    if key == "3" and factor_id:
        lines.append(f'factorId = "{factor_id}";')
    return "\n".join(lines) + ("\n" if lines else "")


def run_dos_step(sess, key, factor_id=None, overrides=()):
    name = STEPS[key]
    res = run_file(sess, name, build_preamble(key, factor_id, overrides))
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

    overrides = [a for a in args if "=" in a]
    non_steps = [a for a in args if a not in STEPS and a != "4" and "=" not in a]
    factor_id = non_steps[0] if non_steps else "ja1"

    for key in args:
        if key in STEPS:
            run_dos_step(get_session(), key, factor_id, overrides)
        elif key == "4":
            run_plot_step(factor_id)


if __name__ == "__main__":
    main()
