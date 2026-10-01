# -*- coding: utf-8 -*-
"""Unified entry point: run each action (action) sequentially according to a JSONL (JSON Line) pipeline.

Each line is a JSON object, one per line, executed in line order. Any action failure aborts immediately (subsequent actions
usually depend on the result of the previous one). Actions that need formula injection use a "dedicated session", isolated from each other (see action_calc_gtja's dos_modules).

Each action = one Python function action_<name>(params, get_session), registered one by one in ACTIONS at the end of the file.
Each function declares its own required/optional (extra params and missing required are inferred by _check_params). Some actions internally run a .dos (such as backtest01 / backtest02 / calc_gtja):
the parts of params mapped to DolphinDB variables are concatenated into assignment statements and injected at the very front of the script.
The implementation .py of upload_mock_data / upload_csv_data / plot is specified by the params' py (required); run.py loads it by that path.

Usage:
    python run.py                                       # omit args -> run pipeline_lite.jsonl by default
    python run.py -h | --help                           # show usage and available actions
    python run.py pipeline_full.jsonl                   # run one JSONL file

Available actions and params (params not marked "required" may be omitted; omitting uses the default in .dos / plot):

    upload_mock_data       generate mock market CSV and upload/persist (header same as data_csv, self-contained)
                   params: py (str, required, implementation .py path), symbols (int), days (int), step (float),
                           start (str), seed (int), prefix (str), output (str), recreate (bool)
    upload_csv_data upload CSV and persist
                   params: py (str, required, implementation .py path), csv (str, required), dos (str), recreate (bool)
    calc_gtja      compute and persist gtja family alpha       params: dos (str, required, calculation script path),
                   rebuild_alpha (bool), security_ids (str, comma-separated security codes; omit = all),
                   alpha_ids (list[int], compute only specified ids, e.g. [1,3,5]; omit = use alphaList in the script)
    calc_wq        compute and persist wq family alpha (WQ101; skipList skips alphas that need industry/market cap)
                   params: dos (str, required, calculation script path), rebuild_alpha (bool), security_ids (str),
                   alpha_ids (list[int], compute only specified ids, e.g. [1,3,5]; omit = use alphaList in the script)
                   Family formulas are specified by each folder's modules.json (the list of .dos to inject, each with its own independent session, mutually invisible).
                   When adding a family, hand-write an action_calc_<family> function in run.py and register it into ACTIONS.
    backtest01     cross-sectional layered backtest                 params: dos (str, required, backtest script path),
                   alpha_id (str), groups (int), ret_clip (float), db_uri/tb_mkt/tb_alpha/out_dir (str)
    backtest02     IC / RankIC / ICIR backtest         params: dos (str, required, backtest script path),
                   alpha_id (str), ret_clip (float), db_uri/tb_mkt/tb_alpha/out_dir (str)
    backtest03     instant evaluation of an expression's alpha RankIC/ICIR   params: dos (str, required, backtest script path),
                   expression (str, required, DolphinDB expression), ret_clip (float), db_uri/tb_mkt/out_dir (str)
    plot           plot layered nav curves                 params: py (str, required, implementation .py path), out_dir (str, required), alpha_id (str), show_ls (bool)

    Alphas of all families share the dfs://gtja/alpha table, distinguished by the alphaId prefix (ja / ...),
    so backtest01 / backtest02 / plot need not care which family an alpha comes from; just pass alpha_id directly.

    upload_mock_data generates a CSV "with the same header as data_csv and values being simulated movement" (default data_mock/data_mock.csv),
    and automatically uploads/persists it (reusing upload_csv_data).
    upload_csv_data reads the csv into a DataFrame and uploads it as a session variable (the variable name is an internal constant of the action, no need to specify externally),
    then automatically runs the load script (by default upload_csv_data.dos in the same directory as upload_csv_data.py, can be overridden with dos);
    the script takes that variable via objByName(FROM_VAR) to build the table, and RECREATE is injected by recreate. So one line per dataset is enough.
"""
import importlib.util
import json
import os
import sys

import config
from ddb import run_file, show, get_session


def _abs(path):
    """A relative path is resolved to an absolute path against config.project_root; an empty value / an already-absolute path is returned as-is.

    This way jsonl / modules.json only need to write relative paths (e.g. "calc_gtja/calc.dos"),
    and nothing needs to change when switching machines (including Windows->Linux)—the project root is derived automatically from config.project_root.
    """
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(config.project_root, path)


def _load_action_func(path):
    """Load an action implementation by the full .py path (the exported function name = file name minus .py)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"action implementation not found: {path}")
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load action implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


def _ddb_literal(value):
    """Convert a Python value to a DolphinDB literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Normalize backslashes to "/", to avoid Windows paths being treated as escapes inside DolphinDB strings
        return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        # Convert to a DolphinDB vector literal, e.g. [1,3,5]
        return "[" + ",".join(_ddb_literal(v) for v in value) + "]"
    raise ValueError(f"params only supports bool/int/float/str/list, got {value!r} ({type(value).__name__})")


def _run_dos(action, script, params, mapping, dos_modules=[]):
    """Run one .dos action: map params to DolphinDB variables, build the preamble, and run it at the very front of the script.

    The preamble always carries the connection credentials (taken from config); the .dos uses if (!defined()) as a fallback,
    so running the same script standalone (VS Code plugin) won't be missing variables either.
    """
    cred = (
        f"DB_USER = {_ddb_literal(config.ddb_username)};\n"
        f"DB_PASSWORD = {_ddb_literal(config.ddb_password)};\n"
    )
    preamble = "\n".join(
        f"{mapping[k]} = {_ddb_literal(v)};" for k, v in params.items() if k in mapping
    )
    if preamble:
        preamble += "\n"
    print(f"\n----- injected DolphinDB vars for action {action} -----")
    print(f"DB_USER = {config.ddb_username}; DB_PASSWORD = ***;")   # do not echo the password
    print(preamble.rstrip() if preamble else "(no other params)")
    res = run_file(get_session(dos_modules), script, cred + preamble)
    show(res, f"result of action {action} ({os.path.basename(script)})")
    return res


def _check_params(action, params, required=(), optional=()):
    """Validate params against the declared required/optional:

        allowed = required | optional
        unknown = params - allowed   (extra params)
        missing = required - params  (missing required)

    That is, as long as required/optional are declared, unknown/missing can both be inferred, no need to write allowed separately.
    """
    allowed = set(required) | set(optional)
    unknown = [key for key in params if key not in allowed]
    if unknown:
        raise ValueError(
            f"action {action!r} does not support params {', '.join(map(repr, unknown))}; "
            f"required: {', '.join(required) or '(none)'}; optional: {', '.join(optional) or '(none)'}"
        )
    missing = [key for key in required if key not in params]
    if missing:
        raise ValueError(
            f"action {action!r} is missing required params {', '.join(missing)}; "
            f"optional: {', '.join(optional) or '(none)'}"
        )


# ==================== Actions: one Python function per action ====================
# Convention: the signature is always (params, get_session); each function declares its own required/optional (validated by _check_params);
#       registered one by one in ACTIONS at the end of the file (action name -> function).

def action_upload_mock_data(params, get_session):
    """Generate mock market CSV and upload/persist it (implementation specified by params["py"])."""
    _check_params(
        "upload_mock_data", params,
        required=("py",),
        optional=("output", "symbols", "days", "start", "seed", "prefix", "step", "recreate"),
    )
    params = {**params, "py": _abs(params["py"])}
    if "output" in params:
        params = {**params, "output": _abs(params["output"])}
    return _load_action_func(params["py"])(params, get_session)


def action_upload_csv_data(params, get_session):
    """Upload CSV and persist it (implementation specified by params["py"], internally runs upload_csv_data.dos)."""
    _check_params("upload_csv_data", params, required=("py", "csv"), optional=("dos", "recreate"))
    params = {**params, "py": _abs(params["py"]), "csv": _abs(params["csv"])}
    if "dos" in params:
        params = {**params, "dos": _abs(params["dos"])}
    return _load_action_func(params["py"])(params, get_session)


def action_backtest01(params, get_session):
    """Cross-sectional layered backtest, runs the script specified by params["dos"]."""
    _check_params(
        "backtest01", params,
        required=("dos",),
        optional=("alpha_id", "groups", "ret_clip", "db_uri", "tb_mkt", "tb_alpha", "out_dir"),
    )
    # Explicitly fall back for out_dir before injection: the base session is reused by multiple actions, avoiding carrying over the OUT_DIR left by the previous script
    out_dir = params.get("out_dir") or os.path.join(config.project_root, "backtest01", "output")
    params = {**params, "dos": _abs(params["dos"]), "out_dir": _abs(out_dir)}
    return _run_dos(
        "backtest01",
        params["dos"],
        params,
        {
            "alpha_id": "ALPHA_ID", "groups": "G", "ret_clip": "RET_CLIP",
            "db_uri": "DB_URI", "tb_mkt": "TB_MKT", "tb_alpha": "TB_ALPHA", "out_dir": "OUT_DIR",
        },
    )


def action_backtest02(params, get_session):
    """IC / RankIC / ICIR backtest, runs the script specified by params["dos"]."""
    _check_params(
        "backtest02", params,
        required=("dos",),
        optional=("alpha_id", "ret_clip", "db_uri", "tb_mkt", "tb_alpha", "out_dir"),
    )
    # Same as above: explicitly fall back for out_dir, to avoid carrying over another backtest script's OUT_DIR when reusing the base session
    out_dir = params.get("out_dir") or os.path.join(config.project_root, "backtest02", "output")
    params = {**params, "dos": _abs(params["dos"]), "out_dir": _abs(out_dir)}
    return _run_dos(
        "backtest02",
        params["dos"],
        params,
        {
            "alpha_id": "ALPHA_ID", "ret_clip": "RET_CLIP",
            "db_uri": "DB_URI", "tb_mkt": "TB_MKT", "tb_alpha": "TB_ALPHA", "out_dir": "OUT_DIR",
        },
    )


def action_backtest03(params, get_session):
    """Instant evaluation of an alpha by a DolphinDB expression (RankIC / ICIR), runs the script specified by params["dos"]."""
    _check_params(
        "backtest03", params,
        required=("dos", "expression"),
        optional=("ret_clip", "db_uri", "tb_mkt", "out_dir"),
    )
    # Explicitly fall back for out_dir, to avoid carrying over the OUT_DIR left by another script when reusing the base session
    out_dir = params.get("out_dir") or os.path.join(config.project_root, "backtest03", "output")
    params = {**params, "dos": _abs(params["dos"]), "out_dir": _abs(out_dir)}
    return _run_dos(
        "backtest03",
        params["dos"],
        params,
        {"expression": "EXPRESSION", "ret_clip": "RET_CLIP", "db_uri": "DB_URI", "tb_mkt": "TB_MKT", "out_dir": "OUT_DIR"},
    )


def action_plot(params, get_session):
    """Plot layered nav curves (implementation .py specified by params["py"])."""
    _check_params("plot", params, required=("py", "out_dir"), optional=("alpha_id", "show_ls"))
    plot = _load_action_func(_abs(params["py"]))

    alpha_id = params.get("alpha_id", "ja1")
    show_ls = params.get("show_ls", True)
    print(f"\n===== plotting alpha {alpha_id} =====")
    return plot(alpha_id=alpha_id, show_ls=show_ls, out_dir=_abs(params["out_dir"]))


def action_calc_gtja(params, get_session):
    _check_params(
        "calc_gtja", params,
        required=("dos",),
        optional=("rebuild_alpha", "security_ids", "alpha_ids"),
    )
    with open(os.path.join(config.project_root, "calc_gtja", "modules.json"), encoding="utf-8") as f:
        dos_modules = [_abs(p) for p in json.load(f)["dos_modules"]]
    params = {**params, "dos": _abs(params["dos"])}
    return _run_dos(
        "calc_gtja",
        params["dos"],
        params,
        {"rebuild_alpha": "REBUILD_ALPHA", "security_ids": "SECURITY_IDS", "alpha_ids": "ALPHA_IDS"},
        dos_modules=dos_modules,
    )


def action_calc_wq(params, get_session):
    _check_params(
        "calc_wq", params,
        required=("dos",),
        optional=("rebuild_alpha", "security_ids", "alpha_ids"),
    )
    with open(os.path.join(config.project_root, "calc_wq", "modules.json"), encoding="utf-8") as f:
        dos_modules = [_abs(p) for p in json.load(f)["dos_modules"]]
    params = {**params, "dos": _abs(params["dos"])}
    return _run_dos(
        "calc_wq",
        params["dos"],
        params,
        {"rebuild_alpha": "REBUILD_ALPHA", "security_ids": "SECURITY_IDS", "alpha_ids": "ALPHA_IDS"},
        dos_modules=dos_modules,
    )


# action name -> Python function (one-to-one)
ACTIONS = {
    "upload_mock_data": action_upload_mock_data,
    "upload_csv_data": action_upload_csv_data,
    "backtest01": action_backtest01,
    "backtest02": action_backtest02,
    "backtest03": action_backtest03,
    "plot": action_plot,
    "calc_gtja": action_calc_gtja,
    "calc_wq": action_calc_wq,
}


def run_action(action, params):
    """Execute a single action: find the corresponding Python function by name and call it. params is the dict parsed from the JSON "params" field."""
    func = ACTIONS.get(action)
    if func is None:
        raise ValueError(f"unknown action {action!r}; available: {', '.join(ACTIONS)}")
    return func(params, get_session)


def _iter_tasks(text):
    """Parse JSONL line by line; skip blank lines and comment lines starting with #."""
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {lineno} is not valid JSON: {e}") from e
        if not isinstance(task, dict) or "action" not in task:
            raise ValueError(f'line {lineno} is missing the "action" field: {line}')
        yield lineno, task


def run_pipeline(text):
    """Execute each task in the JSONL in order; abort if any action fails."""
    for lineno, task in _iter_tasks(text):
        params = task.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f'line {lineno}: "params" must be an object')
        print(f"\n===== [{lineno}] action={task['action']} params={params or '{}'} =====")
        run_action(task["action"], params)


def _read_input(args):
    """Get the JSONL text to execute from command-line args or stdin; return None when there is no input."""
    if args:
        arg = args[0]
        if arg.lstrip().startswith("{"):
            return arg                       # single inline JSON
        if not os.path.exists(arg):
            raise FileNotFoundError(arg)
        with open(arg, "r", encoding="utf-8") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()              # pipe input
    return None


_DEFAULT_PIPELINE = os.path.join(config.project_root, "lab", "pipeline_lite.jsonl")   # default when no pipeline file is specified


def main():
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        print("available actions:", ", ".join(ACTIONS))
        return
    try:
        text = _read_input(args)
    except FileNotFoundError as e:
        print(f"[error] pipeline file not found: {e}")
        print("(numeric step numbers are deprecated, please use JSONL instead, e.g.:")
        sys.exit(1)

    if text is None:
        # no args and no pipe input -> run pipeline_lite.jsonl by default
        try:
            text = _read_input([_DEFAULT_PIPELINE])
        except FileNotFoundError as e:
            print(f"[error] default pipeline file not found: {e}")
            sys.exit(1)

    try:
        run_pipeline(text)
    except Exception as e:
        print(f"\n[pipeline aborted] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
