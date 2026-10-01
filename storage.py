"""SQLite storage. Every function writes immediately, so the app autosaves on each change."""
from __future__ import annotations

import os
import re
import sqlite3
import time
import unicodedata
import uuid
from datetime import date, datetime

import pandas as pd

DB_PATH = os.environ.get("THROW_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "throwing.db"))

LOG_FIELDS = ["date", "session_type", "distance", "start_time", "end_time", "actual_throws",
              "velo_low", "velo_high", "warm_throws", "warm_velo_low", "warm_velo_high",
              "sixty_throws", "sixty_velo_low", "sixty_velo_high", "notes"]
NUM_FIELDS = {"distance", "actual_throws", "velo_low", "velo_high", "warm_throws", "warm_velo_low",
              "warm_velo_high", "sixty_throws", "sixty_velo_low", "sixty_velo_high"}

# 2026 pitching staff (jersey, name, position, year, bats/throws)
DEFAULT_ROSTER = [
    ("30", "Max Bettis", "RHP", "So.", "R/R"), ("33", "Sam Bettis", "RHP", "So.", "R/R"),
    ("26", "Noah Gartner", "RHP", "So.", "R/R"), ("31", "Cooper Jesperson", "RHP", "So.", "R/R"),
    ("23", "Jonah Reich", "RHP", "5th", "R/R"), ("32", "Jackson Baker", "RHP", "Sr.", "R/R"),
    ("7", "Trenton Buckley", "RHP", "Jr.", "R/R"), ("17", "Stevie Doty", "RHP", "Jr.", "R/R"),
    ("99", "Colin Driffill", "RHP", "Fr.", "R/R"), ("37", "Jackson Hulcher", "RHP", "Sr.", "R/R"),
    ("35", "Griffin Lewis", "RHP", "Jr.", "R/R"), ("50", "Max Nantais-Vlahovich", "RHP", "Fr.", "R/R"),
    ("28", "Joseph Pereira", "RHP", "Fr.", "L/R"), ("18", "Stocton Timbrook", "RHP", "Jr.", "R/R"),
    ("15", "Grady Westphal", "RHP", "So.", "R/R"), ("4", "Cordell Clinkingbeard", "RHP/INF", "Fr.", "R/R"),
    ("16", "Kyler Horsman", "RHP/OF", "Sr.", "R/R"), ("9", "Donte Lewis", "UTL", "Jr.", "R/R"),
    ("41", "Adam Arther", "LHP", "Sr.", "L/L"), ("0", "Kaden Dean", "LHP", "Fr.", "L/L"),
    ("25", "Grant Meert", "LHP", "Sr.", "L/L"),
]


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).lower()
    s = re.sub(r"[^\w\s-]", "", s).strip()
    return re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", s))


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS players(
        id TEXT PRIMARY KEY, name TEXT, number TEXT, position TEXT, year TEXT, bt TEXT,
        avg_top_velo REAL, peak_velo REAL, active INTEGER DEFAULT 1, sort INTEGER,
        target_type TEXT DEFAULT 'Game', target_date TEXT, planned_pitches REAL, planned_innings REAL)""")
    cols = ", ".join(f + (" REAL" if f in NUM_FIELDS else " TEXT") for f in LOG_FIELDS)
    c.execute(f"CREATE TABLE IF NOT EXISTS throws(id TEXT PRIMARY KEY, player TEXT, created REAL, updated REAL, {cols})")
    c.execute("CREATE TABLE IF NOT EXISTS overrides(player TEXT, day TEXT, day_type TEXT, PRIMARY KEY(player, day))")
    return c


def _clean(field, v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if field == "date":
        if isinstance(v, datetime):
            v = v.date()
        return v.isoformat() if isinstance(v, date) else (str(v)[:10] or None)
    if field in ("start_time", "end_time"):
        return v.strftime("%H:%M") if hasattr(v, "strftime") else (str(v).strip()[:5] or None)
    if field in NUM_FIELDS:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    s = str(v).strip()
    return s or None


# ───────── players ─────────
def load_players(include_inactive=False) -> pd.DataFrame:
    with _db() as c:
        df = pd.read_sql("SELECT * FROM players" + ("" if include_inactive else " WHERE active=1") +
                         " ORDER BY sort, name", c)
    df["target_date"] = [date.fromisoformat(v) if isinstance(v, str) and v else None for v in df["target_date"]]
    df["target_date"] = df["target_date"].astype(object)
    return df


def get_player(pid) -> dict | None:
    df = load_players(include_inactive=True)
    hit = df[df["id"] == pid]
    if hit.empty:
        return None
    r = hit.iloc[0].to_dict()
    for k in ("avg_top_velo", "peak_velo", "planned_pitches", "planned_innings"):
        if pd.isna(r.get(k)):
            r[k] = None
    if not isinstance(r.get("target_date"), date) or pd.isna(r.get("target_date")):
        r["target_date"] = None
    return r


def add_player(name, number="", position="RHP", year=None, bt=None, avg_top=None, peak=None) -> str:
    pid = slugify(name)
    with _db() as c:
        n = c.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM players").fetchone()[0]
        exists = c.execute("SELECT 1 FROM players WHERE id=?", (pid,)).fetchone()
        if exists:  # re-adding a removed player brings his log back
            c.execute("UPDATE players SET active=1, name=?, number=?, position=? WHERE id=?", (name.strip(), number, position, pid))
            if avg_top is not None:
                c.execute("UPDATE players SET avg_top_velo=? WHERE id=?", (avg_top, pid))
        else:
            c.execute("""INSERT INTO players(id, name, number, position, year, bt, avg_top_velo, peak_velo, active, sort)
                         VALUES (?,?,?,?,?,?,?,?,1,?)""", (pid, name.strip(), number, position, year, bt, avg_top, peak, n))
    return pid


def update_player(pid, **fields):
    allowed = {"name", "number", "position", "year", "bt", "avg_top_velo", "peak_velo", "active",
               "target_type", "target_date", "planned_pitches", "planned_innings"}
    with _db() as c:
        for k, v in fields.items():
            if k not in allowed:
                continue
            if isinstance(v, date):
                v = v.isoformat()
            if isinstance(v, float) and pd.isna(v):
                v = None
            c.execute(f"UPDATE players SET {k}=? WHERE id=?", (v, pid))


def remove_player(pid):
    """Hides his tab. His throw log is kept and comes back if he's added again."""
    update_player(pid, active=0)


# ───────── throw log (row level) ─────────
def load_log(pid) -> pd.DataFrame:
    with _db() as c:
        df = pd.read_sql(f"SELECT id, created, {', '.join(LOG_FIELDS)} FROM throws WHERE player=?", c, params=(pid,))
    df = df.sort_values(["date", "created"], ascending=False, na_position="last").reset_index(drop=True)
    return df


def get_row(row_id) -> dict | None:
    with _db() as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM throws WHERE id=?", (row_id,)).fetchone()
    return dict(r) if r else None


def add_row(pid, rec: dict) -> str:
    rid = uuid.uuid4().hex[:12]
    now = time.time()
    with _db() as c:
        c.execute(f"INSERT INTO throws(id, player, created, updated, {', '.join(LOG_FIELDS)}) VALUES (?,?,?,?{',?' * len(LOG_FIELDS)})",
                  [rid, pid, rec.get("created", now), now] + [_clean(f, rec.get(f)) for f in LOG_FIELDS])
    return rid


def update_row(row_id, rec: dict):
    fields = [f for f in LOG_FIELDS if f in rec]
    if not fields:
        return
    with _db() as c:
        c.execute(f"UPDATE throws SET {', '.join(f + '=?' for f in fields)}, updated=? WHERE id=?",
                  [_clean(f, rec[f]) for f in fields] + [time.time(), row_id])


def delete_row(row_id):
    with _db() as c:
        c.execute("DELETE FROM throws WHERE id=?", (row_id,))


# ───────── overrides ─────────
def load_overrides(pid) -> dict:
    with _db() as c:
        return {date.fromisoformat(d): t for d, t in c.execute("SELECT day, day_type FROM overrides WHERE player=?", (pid,))}


def save_override(pid, day: date, day_type):
    with _db() as c:
        if not day_type or day_type == "(none)":
            c.execute("DELETE FROM overrides WHERE player=? AND day=?", (pid, day.isoformat()))
        else:
            c.execute("INSERT OR REPLACE INTO overrides VALUES (?,?,?)", (pid, day.isoformat(), day_type))


def clear_overrides(pid):
    with _db() as c:
        c.execute("DELETE FROM overrides WHERE player=?", (pid,))


# ───────── first run / import ─────────
def seed_if_empty(workbook_path=None):
    with _db() as c:
        if c.execute("SELECT COUNT(*) FROM players").fetchone()[0]:
            return False
    for num, name, pos, yr, bt in DEFAULT_ROSTER:
        add_player(name, num, pos, yr, bt)
    if workbook_path and os.path.exists(workbook_path):
        import_workbook(workbook_path)
    return True


def import_workbook(src) -> tuple[int, int]:
    """Import Avg Top Velo / Peak Velo (Roster tab), the Throw Log and planner inputs from the ACWR workbook."""
    import warnings
    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(src)
    n_players = 0
    for row in wb["Roster"].iter_rows(min_row=5, values_only=True):
        if row[0]:
            name = str(row[0]).strip()
            pid = slugify(name)
            if get_player(pid) is None:
                add_player(name, position=row[1] or "RHP")
            update_player(pid, avg_top_velo=row[3], peak_velo=row[2])
            n_players += 1
    colmap = {1: "date", 3: "session_type", 4: "distance", 5: "start_time", 6: "end_time", 8: "actual_throws",
              10: "velo_low", 11: "velo_high", 18: "warm_throws", 19: "warm_velo_low", 20: "warm_velo_high",
              24: "sixty_throws", 25: "sixty_velo_low", 26: "sixty_velo_high", 30: "notes"}
    ws = wb["Throw Log"]
    by_player: dict = {}
    for r in range(5, ws.max_row + 1):
        name = ws.cell(r, 2).value
        if not name:
            continue
        rec = {}
        for col, k in colmap.items():
            v = ws.cell(r, col).value
            rec[k] = None if isinstance(v, str) and v.startswith("=") else v
        rec["created"] = 1000 + r
        by_player.setdefault(slugify(str(name)), []).append(rec)
    n = 0
    for pid, recs in by_player.items():
        if get_player(pid) is None:
            add_player(pid.replace("-", " ").title())
        with _db() as c:
            c.execute("DELETE FROM throws WHERE player=?", (pid,))   # replace, never duplicate
        for rec in recs:
            add_row(pid, rec)
            n += 1
    if "Next Outing Planner" in wb.sheetnames:
        nop = wb["Next Outing Planner"]
        if nop["B4"].value and isinstance(nop["B6"].value, datetime):
            update_player(slugify(str(nop["B4"].value)), target_type=nop["B5"].value or "Game",
                          target_date=nop["B6"].value.date(), planned_pitches=nop["B23"].value,
                          planned_innings=nop["D23"].value)
    return n_players, n
