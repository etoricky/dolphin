#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data_full.csv")
DST = os.path.join(HERE, "data_lite.csv")
N = 5


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"source data {SRC} not found, please run python data_csv/prepare_data_full.py first")
    df = pd.read_csv(SRC)
    picks = sorted(df["securityid"].unique())[:N]
    sub = df[df["securityid"].isin(picks)]
    sub.to_csv(DST, index=False)
    print(f"wrote {DST}: {len(sub)} rows, {len(picks)} symbols={list(picks)}")


if __name__ == "__main__":
    main()
