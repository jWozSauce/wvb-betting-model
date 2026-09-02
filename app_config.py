"""Persistent user settings, mirroring the NCAAF Python_Asshole_Algo app.

Stored in config.json next to this file. refresh_from_sheet() pulls
bankroll/kelly/edge/value from the shared Constants Google Sheet (Vball row).
"""
import csv
import io
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = f"{HERE}/config.json"
SHEET_ROW = "Vball"


def _sheet_id():
    """Sheet id lives in Streamlit secrets (CONSTANTS_SHEET_ID) or a local
    untracked sheet_id.txt — never in the repo, since the sheet is readable
    by anyone who has the id."""
    try:
        import streamlit as st
        if "CONSTANTS_SHEET_ID" in st.secrets:
            return st.secrets["CONSTANTS_SHEET_ID"]
    except Exception:
        pass
    local = f"{HERE}/sheet_id.txt"
    if os.path.exists(local):
        return open(local).read().strip()
    raise RuntimeError("No sheet id: set CONSTANTS_SHEET_ID in Streamlit "
                       "secrets or create sheet_id.txt next to the app.")

DEFAULTS = {
    "bankroll": 500.0,
    "kelly_fraction": 0.5,
    "edge_cap": 0.06,
    "value_req": 0.03,
}


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(PATH):
        with open(PATH) as f:
            cfg.update(json.load(f))
    return cfg


def save(cfg):
    with open(PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def update(**kwargs):
    cfg = load()
    cfg.update(kwargs)
    return save(cfg)


def refresh_from_sheet():
    """Pull bankroll/kelly/edge/value from the Constants sheet's Vball row."""
    url = (f"https://docs.google.com/spreadsheets/d/{_sheet_id()}"
           "/export?format=csv&gid=0")
    raw = urllib.request.urlopen(url, timeout=20).read().decode()
    for row in csv.DictReader(io.StringIO(raw)):
        if row["Sport"] == SHEET_ROW:
            return update(
                bankroll=float(row["bankroll2"].replace(",", "")),
                kelly_fraction=float(row["kelly_fraction"]),
                edge_cap=float(row["edge_limit"]),
                value_req=float(row["value_req"]),
            )
    raise RuntimeError(f"row {SHEET_ROW} not found in Constants sheet")
