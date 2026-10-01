# -*- coding: utf-8 -*-
"""Implementation of the upload_csv_data step: the client reads a CSV -> uploads it as a DolphinDB session variable -> runs upload_csv_data.dos to persist it into the DB.

[Note] This step now combines "upload + persist":
    1. pandas reads the CSV and session.upload creates a session variable (named by the VAR_NAME constant in this file);
    2. run the load script (upload_csv_data.dos in the same directory by default), with the preamble injecting DB_URI / TB_NAME / DB_USER / DB_PASSWORD / FROM_VAR / RECREATE,
       creating that variable as dfs://gtja/market.
  Therefore each dataset in the jsonl only needs a single line: upload_csv_data;
  the intermediate session variable name is an internal detail of this step and is not exposed externally.

  Cost (known and accepted): this file is no longer fully independent of lab -- it needs a session object to run the .dos.
  Here it only depends on the session injected by run.py (uses session.run to execute the script) and does not import lab's internal modules.

Can be run standalone for easy testing (connects to the local DB and persists with default params):

    python data_csv/upload_csv_data.py                        # uses data_full.csv in the same directory by default
    python data_csv/upload_csv_data.py <csv path> --dos <script path> --recreate

Note: when run standalone, the connection is dropped as soon as the process exits, so the uploaded variable is not retained (but the .dos has already persisted the data into dfs://gtja).

Interface contract (called by run.py):
    upload_csv_data(params, get_session)
        params      : dict, optional "csv" (client CSV path; defaults to data_full.csv in the same directory);
                      optional "dos" (load script path; defaults to upload_csv_data.dos in the same directory),
                      "recreate" (bool, RECREATE passed to the script; defaults to True)
        get_session : callable returning the current DolphinDB session (the connection is established when called)
    Returns the pandas DataFrame used for the upload.
"""
import argparse
import os
import sys

import dolphindb as ddb

# Connection params: kept consistent with lab/config.py (deliberately duplicated here, not depending on lab)
HOST = "127.0.0.1"
PORT = 8848
USER = "admin"
PASSWORD = "123456"

DB_URI  = "dfs://gtja"      # database name (consistent with the upload_csv_data.dos default, deliberately not depending on lab)
TB_NAME = "market"          # target table name

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOS = os.path.join(HERE, "upload_csv_data.dos")
DEFAULT_CSV = os.path.join(HERE, "data_full.csv")   # default input when the csv param is omitted
DEFAULT_RECREATE = True                             # default value when the recreate param is omitted
VAR_NAME = "uploaded_csv"          # intermediate session variable name: internal detail, not exposed externally


def connect():
    """Create and return a DolphinDB session (for standalone use of this file)."""
    s = ddb.session()
    s.connect(HOST, PORT, USER, PASSWORD)
    return s


def _run_load_dos(session, dos_path, var_name, recreate):
    """Persist the session variable into the DB: run dos_path with the preamble injecting DB_URI/TB_NAME + DB_USER/DB_PASSWORD (constants from this file) + FROM_VAR / RECREATE."""
    if not os.path.exists(dos_path):
        raise FileNotFoundError(f"load script not found: {dos_path}")
    with open(dos_path, "r", encoding="utf-8") as f:
        script = f.read()
    preamble = (
        f'DB_URI = "{DB_URI}";\nTB_NAME = "{TB_NAME}";\n'
        f'DB_USER = "{USER}";\nDB_PASSWORD = "{PASSWORD}";\n'
        f'FROM_VAR = "{var_name}";\nRECREATE = {"true" if recreate else "false"};\n'
    )
    print(f"\n===== running {dos_path} =====")
    return session.run(preamble + script)


def upload_csv_data(params, get_session):
    import pandas as pd

    csv_path = params.get("csv") or DEFAULT_CSV
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    print(f"\n----- uploading {csv_path} as session var {VAR_NAME} -----")
    df = pd.read_csv(csv_path)
    session = get_session()
    session.upload({VAR_NAME: df})
    print(f"uploaded {len(df)} rows x {len(df.columns)} cols as {VAR_NAME}")

    # Automatically persist after upload: runs upload_csv_data.dos in the same directory by default, overridable via params["dos"]
    dos_path = params.get("dos") or DEFAULT_DOS
    if os.path.exists(dos_path):
        _run_load_dos(session, dos_path, VAR_NAME, params.get("recreate", DEFAULT_RECREATE))
    elif params.get("dos"):
        raise FileNotFoundError(f"load script not found: {dos_path}")
    else:
        print(f"[warn] default load script {dos_path} not found; upload only, not persisted")
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(description="Upload a CSV and persist it into DolphinDB (for testing)")
    ap.add_argument("csv", nargs="?", default=DEFAULT_CSV, help=f"client CSV path (default {DEFAULT_CSV})")
    ap.add_argument("--dos", default=DEFAULT_DOS, help="load script path (defaults to upload_csv_data.dos in the same directory)")
    ap.add_argument("--recreate", action=argparse.BooleanOptionalAction, default=DEFAULT_RECREATE,
                    help="RECREATE passed to the script (default True; use --no-recreate to disable)")
    args = ap.parse_args(argv)

    upload_csv_data(
        {"csv": args.csv, "dos": args.dos, "recreate": args.recreate},
        connect,
    )
    print("done (the variable exists only in this session and disappears when the process exits)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
