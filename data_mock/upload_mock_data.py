# -*- coding: utf-8 -*-
"""upload_mock_data step: generate a mock market data CSV and create the DB table (same header as data_csv).

Simulate the close price with a minimal random walk; the other fields (open/high/low/vwap/vol/index_*) are derived from the close price;
the market index_open/index_close use a single shared random walk (identical for all securities on the same day).
The column names and order of the output exactly match data_csv/data_full.csv.

[Self-contained] This file does not depend on data_csv: connection params are built in, and the persistence script uses upload_mock_data.dos in the **same directory**
(logically equivalent to data_csv/upload_csv_data.py + upload_csv_data.dos, intentionally duplicated; if you change the column names / partition scheme you must change both places).

Standalone run (connects to the DB and by default creates/persists data_mock/data_mock.csv into the DB):

    python data_mock/upload_mock_data.py
    python data_mock/upload_mock_data.py --symbols 5 --days 250 --step 0.05 --recreate

Interface contract (called by run.py):
    upload_mock_data(params, get_session)
        params : dict, optional "output", "symbols", "days", "start", "seed", "prefix", "step", "recreate"
        get_session : session factory; when None, only generate the CSV and do not persist
    Returns the path of the written CSV.
"""
import argparse
import os
import sys

import dolphindb as ddb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(HERE, "data_mock.csv")
DEFAULT_DOS = os.path.join(HERE, "upload_mock_data.dos")     # persistence script in the same directory

# Keep the column names and order consistent with data_csv/data_full.csv
COLUMNS = ["vol", "low", "high", "close", "open", "vwap",
           "tradetime", "securityid", "index_close", "index_open"]

# ---------------- Connection params (self-contained, deliberately not depending on data_csv) ----------------
HOST = "127.0.0.1"
PORT = 8848
USER = "admin"
PASSWORD = "123456"

DB_URI  = "dfs://gtja"      # database name (consistent with the upload_mock_data.dos default, deliberately not depending on data_csv)
TB_NAME = "market"          # target table name

VAR_NAME = "uploaded_csv"       # session variable name used for the upload (internal detail)


def connect():
    """Create and return a DolphinDB session (built into this file, not depending on data_csv)."""
    s = ddb.session()
    s.connect(HOST, PORT, USER, PASSWORD)
    return s


def _upload_and_load(df, get_session, recreate):
    """Upload the DataFrame as a session variable and run upload_mock_data.dos in the same directory (create the DB and table)."""
    if not os.path.exists(DEFAULT_DOS):
        raise FileNotFoundError(f"persistence script not found: {DEFAULT_DOS}")
    session = get_session()
    session.upload({VAR_NAME: df})
    print(f"uploaded {len(df)} rows x {len(df.columns)} cols as {VAR_NAME}")
    with open(DEFAULT_DOS, "r", encoding="utf-8") as f:
        script = f.read()
    preamble = (
        f'DB_URI = "{DB_URI}";\nTB_NAME = "{TB_NAME}";\n'
        f'DB_USER = "{USER}";\nDB_PASSWORD = "{PASSWORD}";\n'
        f'FROM_VAR = "{VAR_NAME}";\nRECREATE = {"true" if recreate else "false"};\n'
    )
    print(f"\n===== running {DEFAULT_DOS} =====")
    return session.run(preamble + script)


def upload_mock_data(params, get_session=None):
    output = params.get("output") or DEFAULT_OUTPUT
    n_sym = int(params.get("symbols", 5))
    n_day = int(params.get("days", 250))
    start = params.get("start", "2020.01.01")
    seed = int(params.get("seed", 42))
    prefix = params.get("prefix", "gen")
    step = float(params.get("step", 0.02))

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=pd.to_datetime(start, format="%Y.%m.%d"), periods=n_day)

    # Market index: a single shared random walk (identical for all securities on the same day)
    index_close = 3000 * np.cumprod(1 + rng.normal(0, 0.01, n_day))
    index_open = index_close * (1 + rng.normal(0, 0.003, n_day))

    frames = []
    for i in range(n_sym):
        sid = f"{prefix}{i + 1:06d}"
        close = (10 + rng.uniform(0, 90)) * np.cumprod(1 + rng.normal(0, step, n_day))
        prev = np.concatenate([[close[0]], close[:-1]])
        open_ = prev * (1 + rng.normal(0, 0.005, n_day))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n_day)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n_day)))
        vwap = (high + low + close) / 3
        vol = rng.integers(10000, 1000000, n_day).astype(float)
        frames.append(pd.DataFrame({
            "vol": vol,
            "low": low,
            "high": high,
            "close": close,
            "open": open_,
            "vwap": vwap,
            "tradetime": dates.strftime("%Y.%m.%dT00:00:00.000"),
            "securityid": sid,
            "index_close": index_close,
            "index_open": index_open,
        }))

    df = pd.concat(frames, ignore_index=True)[COLUMNS]
    df.to_csv(output, index=False)
    print(f"wrote {output}: {len(df)} rows, {n_sym} symbols x {n_day} days")

    # With a session factory -> upload + create/persist into the DB; when None, only generate
    if get_session is not None:
        _upload_and_load(df, get_session, params.get("recreate", False))

    return output


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a mock market data CSV and create/persist it into the DB (header same as data_csv)")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="output CSV path")
    ap.add_argument("--symbols", type=int, default=5, help="number of securities")
    ap.add_argument("--days", type=int, default=250, help="number of trading days")
    ap.add_argument("--start", default="2020.01.01", help="start date (YYYY.MM.DD)")
    ap.add_argument("--seed", type=int, default=42, help="random seed")
    ap.add_argument("--prefix", default="gen", help="security code prefix")
    ap.add_argument("--step", type=float, default=0.02, help="per-security daily return standard deviation / walk step")
    ap.add_argument("--recreate", action="store_true", default=False, help="recreate the DB (drop and reload)")
    args = ap.parse_args(argv)

    upload_mock_data(vars(args), connect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
