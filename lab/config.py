# -*- coding: utf-8 -*-
"""Global config: DolphinDB connection settings and database / table naming.

Values live in config.json in the same directory; they are read here and exposed
as module-level names with the **same name (lower_snake)**, so callers write
`config.ddb_host` / `config.ddb_port`, etc.
"""
import json
import os

_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
with open(_JSON, encoding="utf-8") as _f:
    _cfg = json.load(_f)

# Project root: specified via "project_root" in config.json (only change this one place when switching machine / OS).
project_root = _cfg["project_root"]

ddb_host = _cfg["ddb_host"]
ddb_port = _cfg["ddb_port"]
ddb_username = _cfg["ddb_username"]
ddb_password = _cfg["ddb_password"]
db_uri = _cfg["db_uri"]
market_tb = _cfg["market_tb"]
alpha_tb = _cfg["alpha_tb"]
