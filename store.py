"""İma faizi anlık görüntülerini (snapshot) SQLite'e biriktirir → zaman serisi grafiği için."""
import os
import sqlite3

import pandas as pd

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viop_history.db")


def _conn():
    c = sqlite3.connect(DB)
    c.execute(
        """CREATE TABLE IF NOT EXISTS snapshots(
            ts        TEXT,
            symbol    TEXT,
            underlying TEXT,
            maturity  TEXT,
            spot      REAL,
            forward   REAL,
            days      INTEGER,
            implied   REAL,
            PRIMARY KEY(ts, symbol)
        )"""
    )
    return c


def save_snapshot(ts, rows):
    """rows: dict listesi (symbol, underlying, maturity, spot, forward, days, implied)."""
    c = _conn()
    with c:
        c.executemany(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    ts,
                    r["symbol"],
                    r["underlying"],
                    r["maturity"],
                    r["spot"],
                    r["forward"],
                    r["days"],
                    r["implied"],
                )
                for r in rows
            ],
        )
    c.close()


def load_history(symbol=None, underlying=None):
    c = _conn()
    q = "SELECT ts,symbol,underlying,maturity,spot,forward,days,implied FROM snapshots"
    conds, params = [], []
    if symbol:
        conds.append("symbol=?")
        params.append(symbol)
    if underlying:
        conds.append("underlying=?")
        params.append(underlying)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY ts"
    df = pd.read_sql_query(q, c, params=params)
    c.close()
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"])
    return df
