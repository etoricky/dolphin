# -*- coding: utf-8 -*-
"""统一入口：按 JSONL（JSON Line）流水线依次执行各步骤。

每一步是一个 JSON 对象，一行一个，按行顺序执行；params 里的键会被翻译成
DolphinDB 变量，注入到对应 .dos 脚本的最前面。任一步失败立即中止（后续步骤
通常依赖前一步的结果）。

用法:
    python run.py pipeline.jsonl                        # 跑一个 JSONL 文件
    python run.py < pipeline.jsonl                      # 从 stdin 读（可管道串联）
    python run.py '{"step":"backtest","params":{"factorId":"ja1"}}'   # 单条内联 JSON

可用步骤与参数（params 可省略，省略即用 .dos / plot 里的默认值）:

    load_market    建库 + 导入行情        params: recreate (bool)
    calc_factors   计算并落库 GTJA191 因子  params: rebuildFactor (bool)
    backtest       横截面分层回测          params: factorId (str), groups (int), retClip (float)
    plot           画分层净值曲线          params: factorId (str), showLs (bool)

示例流水线:

    {"step": "load_market",  "params": {"recreate": false}}
    {"step": "calc_factors", "params": {"rebuildFactor": true}}
    {"step": "backtest",     "params": {"factorId": "ja1", "groups": 5}}
    {"step": "plot",         "params": {"factorId": "ja1"}}

因子公式来自「客户端」的 modules-local/ 目录，由 loader.py 在会话建立后注入到
服务端执行（不再使用服务端的 use）。
"""
import json
import os
import sys

import config
import loader
from ddb import connect, run_file, show

# 步骤名 -> 执行方式
#   script: 要跑的 .dos 文件
#   params: JSON 参数名 -> DolphinDB 变量名（"python": true 的步骤直接传 Python 函数）
STEPS = {
    "load_market": {
        "script": os.path.join(config.DATA_LOCAL, "01_create_market_db.dos"),
        "params": {"recreate": "RECREATE"},
    },
    "calc_factors": {
        "script": os.path.join(config.SCRIPTS_DIR, "02_calc_factors.dos"),
        "params": {"rebuildFactor": "REBUILD_FACTOR"},
    },
    "backtest": {
        "script": os.path.join(config.SCRIPTS_DIR, "03_backtest.dos"),
        "params": {"factorId": "factorId", "groups": "G", "retClip": "RET_CLIP"},
    },
    "plot": {
        "python": True,
        "params": {"factorId": "factorId", "showLs": "showLs"},
    },
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


def _ddb_literal(value):
    """把 Python 值转成 DolphinDB 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise ValueError(f"params 只支持 bool/int/float/str，收到 {value!r} ({type(value).__name__})")


def build_preamble(step, params):
    """把 params 变成 DolphinDB 变量赋值，拼在 .dos 脚本最前面。"""
    mapping = STEPS[step]["params"]
    lines = [f"{mapping[key]} = {_ddb_literal(value)};" for key, value in params.items()]
    if step == "load_market":
        # 行情 CSV 路径由 config.py 统一提供，避免 .dos 里再硬编码一份
        lines.insert(0, f'CSV_PATH = "{config.RAW_CSV.replace(chr(92), "/")}";')
    return "\n".join(lines) + ("\n" if lines else "")


def run_step(step, params):
    """执行单个步骤。params 为 JSON 里 params 字段解析出的 dict。"""
    spec = STEPS.get(step)
    if spec is None:
        raise ValueError(f"未知步骤 {step!r}；可用: {', '.join(STEPS)}")
    unknown = [key for key in params if key not in spec["params"]]
    if unknown:
        raise ValueError(
            f"步骤 {step!r} 不支持参数 {', '.join(map(repr, unknown))}；"
            f"可用: {', '.join(spec['params']) or '（无）'}"
        )

    if spec.get("python"):
        return _run_plot(params)

    path = spec["script"]
    res = run_file(get_session(), path, build_preamble(step, params))
    show(res, f"result of step {step} ({os.path.basename(path)})")
    return res


def _run_plot(params):
    from plot import plot_nav

    factor_id = params.get("factorId", "ja1")
    show_ls = params.get("showLs", True)
    print(f"\n===== plotting factor {factor_id} =====")
    return plot_nav(factor_id, show_ls=show_ls)


def _iter_tasks(text):
    """逐行解析 JSONL；跳过空行与 # 开头的注释行。"""
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {lineno} 行不是合法 JSON: {e}") from e
        if not isinstance(task, dict) or "step" not in task:
            raise ValueError(f'第 {lineno} 行缺少 "step" 字段: {line}')
        yield lineno, task


def run_pipeline(text):
    """按顺序执行 JSONL 里的每个任务；任一步失败即中止。"""
    for lineno, task in _iter_tasks(text):
        params = task.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f'第 {lineno} 行的 "params" 必须是对象')
        print(f"\n===== [{lineno}] step={task['step']} params={params or '{}'} =====")
        run_step(task["step"], params)


def _read_input(args):
    """从命令行参数或 stdin 取到要执行的 JSONL 文本；无输入时返回 None。"""
    if args:
        arg = args[0]
        if arg.lstrip().startswith("{"):
            return arg                       # 单条内联 JSON
        if not os.path.exists(arg):
            raise FileNotFoundError(arg)
        with open(arg, "r", encoding="utf-8") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()              # 管道输入
    return None


def main():
    args = sys.argv[1:]
    try:
        text = _read_input(args)
    except FileNotFoundError as e:
        print(f"[错误] 找不到流水线文件: {e}")
        print("（数字步骤号已废弃，请改用 JSONL，例如：")
        print('  python run.py \'{"step":"backtest","params":{"factorId":"ja1"}}\'）')
        sys.exit(1)

    if text is None:
        print(__doc__)
        print("可用步骤:", ", ".join(STEPS))
        return

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    try:
        run_pipeline(text)
    except Exception as e:
        print(f"\n[pipeline 中止] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
