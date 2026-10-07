# lab Handoff Notes

> When switching development machines: `git clone` this repo and just follow Section 7.
> This file only records design decisions, conventions, and gotchas that **cannot be seen from the code**.

---

## 1. What this is

A testbed on DolphinDB for **alpha computation + cross-sectional quantile backtesting**. Alphas are organized by "family";
there are currently two families: gtja (GTJA191) and wq (WQ101).

Core conventions: **formula source code lives on the client; computation runs 100% on the server.**
Each family has its own folder and its own session; formulas are mutually invisible between families.

A family = a set of formula `.dos` files to be injected into a session; each family's manifest is in its own folder's `modules.json` (read by run.py):

| family | folder | action | alphaId prefix |
|---|---|---|---|
| gtja | `calc_gtja/` | `calc_gtja` | `ja` |
| wq | `calc_wq/` | `calc_wq` | `wq` |

---

## 2. Environment

| item | value |
|---|---|
| DolphinDB Server | 2.00.19, `127.0.0.1:8848`, `admin` / `123456` |
| Python | 3.10 (`pip install dolphindb`, tested with 3.0.6.0) |
| Server modules directory | **cleared** (intentional, see Section 4) |
| Market data | `data_csv/data_full.csv` (~170MB) **kept locally, not loaded into the database**; for how to obtain, see Section 7 |
| Project root | specified in `config.json`'s `project_root` (when changing machines / OS, only change this one place); paths in jsonl / `modules.json` are always written as **relative paths**, resolved to absolute paths by run.py based on the project root |

---

## 3. Directories and Responsibilities

```
dolphin/
├─ calc_gtja/                          # family gtja (client formula source + computation script)
│   ├─ gtja191Alpha.dos                #   191 alpha formulas (for injection, pure def)
│   ├─ gtja191Prepare.dos              #   panel preparation + gtjaCalAlpha1..191 (for injection, pure def)
│   ├─ calc.dos                        #   family computation script (executed, contains top-level logic)
│   └─ modules.json                    #   list of .dos to inject into the session (read by run.py)
├─ calc_wq/                            # family wq (client formula source + computation script)
│   ├─ wq101alpha.dos                  #   101 alpha formulas (for injection, pure def)
│   ├─ prepare101.dos                  #   panel preparation + calAlpha1..101 (for injection, pure def)
│   ├─ calc.dos                        #   family computation script (executed, contains top-level logic)
│   └─ modules.json                    #   list of .dos to inject into the session (read by run.py)
├─ calc_unused/                        # modules not currently used (alphalens / ta / mytt / *Res / *StreamTest)
├─ data_csv/                           # market data + load scripts (csv not loaded into the database)
│   ├─ prepare_data_full.py            #   one-click download and extraction (run once after clone)
│   ├─ upload_csv_data.py                  #   implementation of the upload_csv_data action (client reads CSV -> uploads as session variable)
│   ├─ data_full.csv                   #   raw market data ~170MB (kept locally, not loaded into the database)
│   └─ upload_csv_data.dos                 #   create database + import market data
├─ backtest01/                         # family-agnostic scripts / plotting (specified by jsonl's dos / py)
│   ├─ backtest.dos                    #   quantile backtest (reads the alpha table)
│   ├─ plot.py                         #   plot the quantile nav curves
│   └─ output/                         #   generated CSV / PNG (gitignored)
├─ backtest02/                         # second backtest method: IC / RankIC / ICIR
│   ├─ backtest.dos                    #   daily cross-sectional IC statistics
│   └─ output/                         #   generated IC CSV (gitignored)
├─ backtest03/                         # third set: directly evaluate a DolphinDB expression (does not depend on the alpha table)
│   ├─ backtest.dos                    #   immediate expression evaluation -> Mean Rank IC / IC Volatility / ICIR / number of days
│   └─ output/                         #   eval_result.json (expression + metrics, gitignored)
└─ lab/
    ├─ config.py                       # reads config.json, exposes config.ddb_host etc.
    ├─ config.json                     # connection settings and database / table naming (values)
    ├─ ddb.py                          # create session / session reuse (inject .dos) / run .dos / print
    ├─ run.py                          # entry point: read the JSONL pipeline (including each action's dos_modules / paths) [core]
    └─ pipeline_*.jsonl                # example pipeline (copy and modify as needed)
```

Data flow: `data_full.csv` →(upload_csv_data)→ session variable `uploaded_csv` →`dfs://gtja/market`
→(`calc_gtja` / `calc_wq`)→ `dfs://gtja/alpha` →(backtest01 / backtest02) backtest + plot chart.
In the `alpha` table, families are distinguished by the `alphaId` prefix (gtja=`ja`, wq=`wq`).

> **Directory placement principle**: `modules-*/` holds the "for injection" formulas (pure `def`, no side effects),
> while `calc_*.dos` are the "executed" scripts (containing login / loadTable / loops / append).
> Don't mix the two — files for injection are executed once every time a session is created.

---

## 4. Key mechanism: per-family client-side module injection

**Why this approach**

The alpha modules under the server's modules directory were moved away (we don't want to depend on server modules, nor modify `dolphindb.cfg`),
so `use gtja191Alpha` now reports `Can't find module [gtja191Alpha]`.

**How it works**

`ddb.py`'s `load_modules` reads the passed-in `.dos` → strips the `module xxx` declaration → uses `run()` to send the function definitions to the server →
the server compiles these `def`s into the **current session**. `ddb.get_session` uses **one independent session per file manifest**
(`get_session(dos_modules)`), injecting only the `.dos` manifest passed to it by that action (e.g. `action_calc_gtja`'s `dos_modules`).

- Source code lives on the client (each `modules-<family>/` folder), controlled by the client;
- Execution still happens on the server; the client is only responsible for "delivering the source code";
- **Families are mutually invisible**: family A's session has no family B `def`s at all, giving natural isolation,
  with no name collisions/overwrites and no cross-calls.

**Four things you must remember**

1. **Injection is "once per session"** — functions live only in the server session's memory and are not persisted to disk.
   Every new connection must re-inject (`run.py` already handles this automatically).
2. **No module isolation within a family** — multiple `.dos` files injected by the same family share one namespace;
   duplicate names overwrite each other / raise errors.
3. **To use a function across families, you can only go through the `alpha` table** — after persisting alphas, backtesting/plotting retrieves them by `alphaId`,
   rather than directly calling another family's formula functions.
4. **The VS Code plugin's session is independent** — running a family computation script in the plugin requires first manually injecting that family's
   `modules`, otherwise it reports `gtjaCalAlpha1 is not defined`. The normal usage is via `python run.py ...`.

**Adding a new family**

1. Under the repo root (`dolphin/`), create `modules-<name>/`, put in the formula `.dos` (pure def, for injection)
   + a `calc_<name>.dos` (executed);
2. Hard-code the `.dos` manifest to inject in `action_calc_<name>` (`dos_modules=[...]`);
3. In `run.py`, hand-write an `action_calc_<name>(params, get_session)` by following `action_calc_gtja`,
   and register it into `ACTIONS` (**actions are not auto-generated; you must register them manually**).

> `run.py` is "one Python function per action": each action corresponds to an `action_<name>(params, get_session)`;
> the function declares its own `required`/`optional` (`_check_params` uses this to derive extra parameters and missing required ones), and all are registered one by one in `ACTIONS`.
> Actions that run `.dos` use the shared `_run_dos()` internally to assemble the preamble and execute.

---

## 5. Gotchas (important)

### 5.1 Rules for localizing `.dos` files

To flatten server modules into a "client version", you need to:

- Delete the `module <name>` declaration line
- Revert cross-module references `gtja191Alpha::gtjaAlpha1` back to `gtjaAlpha1`
- **BUT calls like `::built-in function(...)` must be preserved as-is!**

The last one is where things most easily go wrong. `ta.dos` has many of these:

```dolphindb
def ma(close, timePeriod=30, maType=0){
 	return ::ma(close, timePeriod, maType)   // :: means "call the built-in ma"
}
```

This is "wrapping the built-in implementation with a module-internal name". If you also change `::ma` to `::taMa`,
it becomes **calling itself**, causing an immediate stack overflow (`A recursive function exceeds the specified maximum depth [1000]`).
The same applies to `::abs` / `::pow` / `::sqrt` / `::iif` in `mytt.dos`.

### 5.2 Function names must not collide with DolphinDB built-ins

Defining a function with the same name in a session directly reports `Not allowed to overwrite existing built-in functions [xxx]`.

Renames already done:

| file | original function name | renamed to |
|---|---|---|
| `ta.dos` | `var` `beta` `sma` `ema` `wma` `dema` `tema` `trima` `kama` `t3` `ma` | add the `ta` prefix: `taVar` `taBeta` `taSma` … `taT3` `taMa` |
| `mytt.dos` | `BETWEEN` | `myttBetween` |

> The same caution applies when writing your own wrapper functions later: **don't collide with built-in function names**.

### 5.3 Same-named metadata functions across multiple modules

`gtja191Alpha` / `ta` / `mytt` / `wq101alpha` / `alphalens` all define `module_info`;
injecting them simultaneously reports `Can't redefine function/procedure module_info`.
They have each been renamed to `<moduleName>ModuleInfo`.

### 5.4 Column name adaptation (the market table ≠ standard field names)

The `market` table uses **custom column names**:

| standard field (required by GTJA191) | actual market column name |
|---|---|
| tradetime / securityid | `Timestamp` / `Symbol` |
| open / close / high / low | `MidOpen` / `MidClose` / `MidHigh` / `MidLow` |
| vol / vwap | `BarVolume` / `BarVwap` |
| index_open / index_close | `IndexOpen` / `IndexClose` |

```dolphindb
data = prepareData(rawData = rawData, startTime = startTime, endTime = endTime,
                   securityidName = "Symbol",     tradetimeName  = "Timestamp",
                   openName       = "MidOpen",    closeName      = "MidClose",
                   highName       = "MidHigh",    lowName        = "MidLow",
                   volumeName     = "BarVolume",  vwapName       = "BarVwap",
                   indexCloseName = "IndexClose", indexOpenName  = "IndexOpen")
```

After mapping, `data`'s field names are the standard names; subsequent logic need not care about the original column names.

### 5.5 Idempotency switches

| action (script) | switch | default | meaning |
|---|---|---|---|
| `upload_csv_data` (`upload_csv_data.dos`) | `RECREATE` | `false` | if the database/table already exists, skip the import; if `true`, drop the database and recreate |
| `calc_<family>` (each family's `calc_*.dos`) | `REBUILD_ALPHA` | `true` | if `true`, delete only **this family's prefixed** alphas and recompute; if `false`, only compute the alphas not yet computed |

Command-line override: parameters are written in the JSONL's `params`, e.g.
`{"action":"upload_csv_data","params":{"py":"data_csv/upload_csv_data.py","csv":"C:/data/dataset_v2.csv","recreate":true}}` / `{"action":"calc_gtja","params":{"dos":"calc_gtja/calc.dos","rebuild_alpha":false}}`
(`params` are translated into DolphinDB variables and injected at the very top of the .dos).

> **After changing column names or the partitioning scheme, you must use `recreate=true`** —
> otherwise `upload_csv_data` (the database creation step) will be skipped because "the table already exists", leaving the old schema behind, and subsequent actions will report baffling errors.
> Dropping the database also drops the shared `alpha` table, so remember to re-run all families' `calc_<family>`.
>
> The `alpha` table is shared by all families, so each family computation script's rebuild is **`delete ... where alphaId like '<prefix>%'`**
> (deleting only its own family's rows), **no longer `dropTable`** — otherwise it would delete the other families' alphas too.

Now "upload" and "persist" are merged into the single `upload_csv_data` action; one JSONL line per dataset is enough:

```
{"action":"upload_csv_data", "params":{"py":"data_csv/upload_csv_data.py","csv":"C:/data/dataset_v2.csv","dos":"C:/data/load_v2.dos","recreate":true}}
```

- `upload_csv_data`: the client reads the CSV (`pandas.read_csv`) → `session.upload` into a server session variable
  (the variable name is an internal constant of the action, not exposed) → automatically runs the load script (by default the
  `upload_csv_data.dos` in the same directory as `upload_csv_data.py`, overridable with `dos`; `recreate` is injected as `RECREATE`).
  **The csv is client-side data and does not depend on the server's file system** (works even when the server is remote).
  The implementation .py is specified by the required `py` in params; `run.py` loads it via `importlib` by that path (the exported function name = the file name).
  This action now needs a session to run .dos, so it is **no longer fully independent of lab** (the cost is known and accepted).
  The connection settings are still duplicated on its own (consistent with `config.py`); when changing host/port/account you must change both places.
  It can also be run standalone for testing: `python data_csv/upload_csv_data.py <csv> [--dos ...] [--recreate]`
  (it disconnects on exit, but the .dos has already persisted the data).
- The internal session variable name is defined by `upload_csv_data` itself (constant `VAR_NAME`); no need to align when using it.

### 5.6 data_full.csv is synthetic random data

This is DolphinDB's official data for **verifying alpha computation correctness**; prices have no continuity at all:

```
sz000001: 37.7 → 12.6 → 51.1 → 94.7 → 50.2 → 57.1 → 16.1 ...
```

The mean single-day return is +181%, with a standard deviation of 381; backtesting directly on it yields numbers like `1e102`.
`backtest.dos` adds `RET_CLIP = 0.2` (price limit / winsorization) to bring the metrics down to a normal magnitude.

**Conclusion: the backtest numbers only prove the pipeline runs; they have no strategic meaning. To see real results you must switch to real market data.**

### 5.7 Backtest outputs are written on the client, not the server

The backtest `.dos` scripts used to call `saveText(..., OUT_DIR + "/...")`, which writes on the **server** machine.
When the server-side `OUT_DIR` does not exist this fails at run time
(`saveText(...) => Cannot open file [...]: No such file or directory`) even though the computation itself succeeded.

So the backtests no longer persist anything on the server. Instead:

- `backtest01/backtest.dos` returns its `dict(`daily`nav`stats`drawdown`ls, ...)` to the client;
- `backtest02/backtest.dos` returns `dict(["icTb", "summary"], ...)`;
- `backtest03/backtest.dos` returns the result JSON string (`js`).

`run.py` receives that value from `session.run()`, writes it under `out_dir` (a **client-side** path, resolved by `_abs`)
and prints a curated summary (`_run_dos(..., show_result=False)` + `_save_tables` / `_save_text`).
DolphinDB tables come back as pandas `DataFrame`s and are written with `to_csv`, so `plot.py` is unaffected.
This means there is no `OUT_DIR` variable injected into the backtest scripts any more, and the whole pipeline works even
against a remote DolphinDB whose file system is not accessible from the client.

---

## 6. DolphinDB Syntax Notes

- `rank(x)` starts from **0**; `rank(x, percent=true)` returns a percentage rank in (0,1]
- `count(distinct x)` is not supported; use `size(exec distinct x from t)`
- The condition of the ternary `? :` must be a bool scalar and easily reports
  `The condition clause of a ternary operator must return a bool`; using `if/else` is more robust
- `move(x, -1)` takes the next element (used with `context by securityid` to compute next-day returns)
- Matrix `flatten()` is **column-major**
- `panel(row labels, column labels, [vectors...])` returns a **list** of matrices, and **sorts** the labels
- The client-uploaded `tradetime` is a string; in the script use `timestamp(tradetime)` to convert it to `TIMESTAMP`
- Don't call `existsTable(db, tb)` directly when the database does not exist; check with `existsDatabase` first

---

## 7. Setting Up on a New Machine

1. Install DolphinDB 2.00.x, start a single node on `8848`, account `admin` / `123456`
   (it's normal if `getHomeDir()` returns the server directory)
2. `pip install dolphindb` (Python 3.10)
3. `git clone` this repo (code only, a few dozen KB)
4. **Download the market data** (kept locally but not loaded into the database; only the load step needs it):

   ```powershell
   python data_csv/prepare_data_full.py
   ```

   The script downloads `191_data.zip` from the official address, extracts `data_csv/data_full.csv`
   (~170MB), and automatically deletes the temporary archive; it skips if the data already exists.
   Manual alternative: download <https://www.dolphindb.cn/downloads/docs/191_data.zip>
   and extract `data_full.csv` into `data_csv/`.

   > Only the `upload_csv_data` (create / rebuild database) step uses this CSV, and it is **read on the client** and then uploaded to the server;
   > `calc_<family>` / `backtest01` / `backtest02` / `plot` do not read it, because the market data is already in DolphinDB's `dfs://gtja/market`.
   > So **this CSV is only needed when `recreate=true` or the database has been dropped**.
5. Run:

```powershell
cd lab
python run.py pipeline_full.jsonl
```

---

## 8. Common Commands

```powershell
cd lab

python run.py pipeline_full.jsonl                   # full pipeline: upload -> create database -> alphas -> backtest -> plot chart
python run.py '{"action":"calc_gtja","params":{"dos":"calc_gtja/calc.dos","rebuild_alpha":false}}'   # only compute newly added alphas
python run.py '{"action":"backtest01","params":{"dos":"backtest01/backtest.dos","alpha_id":"ja5","groups":5}}' # backtest ja5
python run.py '{"action":"plot","params":{"py":"backtest01/plot.py","out_dir":"backtest01/output","alpha_id":"ja5"}}'                # plot ja5 nav
python run.py < pipeline_full.jsonl                 # read from stdin (can be chained via pipes)
```

Action names: `upload_csv_data` / `calc_gtja` / `calc_wq` / `backtest01` / `backtest02` / `backtest03` / `plot`;
for parameters, see the docstring at the top of `run.py` or `pipeline_*.jsonl`.

> To rebuild the market data (`recreate=true`): just change `recreate` to `true` on the `upload_csv_data` line in `pipeline_*.jsonl`.

Each family's `calc_*.dos` can also be run directly in the VS Code DolphinDB plugin, but you **must first manually inject that family's modules**
(see Section 4), otherwise it reports `gtjaCalAlpha1 is not defined`.
