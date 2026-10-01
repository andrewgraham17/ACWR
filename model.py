"""
K-State Baseball — Throwing Workload Model (calculation engine)

Every constant and rule below is copied from the Fall 2026 ACWR workbook
(Reference tab, Day Type Templates tab, Next Outing Planner tab).
To re-tune the model, edit the values in this file — nowhere else.
"""
from __future__ import annotations

import math
from datetime import date, time, timedelta

# ─────────────────────────────────────────────────────────────
# REFERENCE TABLES  (Reference tab)
# ─────────────────────────────────────────────────────────────

# Distance Factor — (min distance ft, factor, description)
DISTANCE_TABLE = [
    (0, 1.0, "Warm-up / catch play (≤60 ft)"),
    (61, 1.3, "Building distance (61–90 ft)"),
    (91, 1.7, "Extension / stretch (91–120 ft)"),
    (121, 2.2, "Long toss (121–150 ft)"),
    (151, 2.8, "Max long toss (151–180 ft)"),
    (181, 3.5, "Pulldowns / max distance (181+ ft)"),
]

# Intensity Factor — (min mph below Avg Top Velo, factor, description)
INTENSITY_TABLE = [
    (0, 2.0, "Max effort — at or near Avg Top Velo (about 0–3 mph off)"),
    (4, 1.5, "Compete / high intent (about 4–6 mph off)"),
    (7, 1.0, "Building (about 7–9 mph off)"),
    (10, 0.6, "Easy / recovery catch (10+ mph off)"),
]

# ACWR zones — (min ACWR, zone, guidance)
ZONE_TABLE = [
    (0.0, "Undertrained", "Below 0.8 — there is room to progress distance/intensity next session."),
    (0.8, "Sweet Spot", "0.8–1.3 — ideal loading zone; maintain the planned progression."),
    (1.31, "Caution", "1.3–1.5 — hold volume/intensity flat; add a recovery day this week."),
    (1.51, "High Risk", "Above 1.5 — mandatory easy/rest day next session; cut weekly volume 20–30%."),
]
INSUFFICIENT_ZONE = "Insufficient history (need ~28 days logged)"
INSUFFICIENT_GUIDANCE = (
    "Log at least 28 days of throws for a reliable trend. Meanwhile, rely on RPE "
    "and arm feedback before adding volume."
)

SESSION_TYPES = [
    "No Throw",
    "Long Toss",
    "Compression/Pulldowns",
    "Bullpen",
    "Moderate",
    "Game",
    "Recovery/Easy Catch",
]

# Throw rate (throws / minute) — used to estimate throw count from clock time
THROW_RATE = {
    "No Throw": 0,
    "Long Toss": 3,
    "Compression/Pulldowns": 3,
    "Bullpen": 0,
    "Moderate": 3.5,
    "Game": 0,
    "Recovery/Easy Catch": 4.5,
}

# Mound Factor — used INSTEAD of Distance Factor for Bullpen & Game
MOUND_FACTOR = {"Bullpen": 3.0, "Game": 3.2}
MOUND_TYPES = ("Bullpen", "Game")

# Periodization Rule — default day type by days until next High-Intent Day
TAPER_RULE = {
    0: ("Game", "The High-Intent Day itself — fixed by the schedule (Game or High Bullpen), not a training choice."),
    1: ("Low", "Day before he pitches: stay loose and protect freshness — never build here."),
    2: ("Medium", "Two days out: moderate catch play while yesterday's work clears."),
    3: ("High Bullpen", "Classic starter bullpen day — enough runway to recover before the next outing."),
    4: ("Medium", "Build day — moderate long toss/pulldowns, not yet max effort."),
    5: ("Low", "Start of taper week: 5 days out, base/recovery work before the build back up."),
}
# Far-out build cycle — (days-6) MOD 3
FAR_OUT_CYCLE = {
    0: ("Medium", "Build day in the repeating base cycle."),
    1: ("High Non-Bullpen", "Compete/high-intent day in the repeating base cycle."),
    2: ("Low", "Recovery day in the repeating base cycle — spaced so it never lands two days running."),
}

DAY_TYPES = ["Low", "Medium", "High Non-Bullpen", "High Bullpen", "Low Bullpen", "Game"]
OVERRIDE_CHOICES = ["(none)", "No Throw", "Low", "Medium", "High Non-Bullpen", "Low Bullpen", "High Bullpen", "Game"]
HIGH_INTENT_TYPES = ["Game", "High Bullpen", "Low Bullpen"]

PLANNER_MAX_DAYS = 21          # the workbook plans up to 21 days ahead
RATIO_HIGH, RATIO_LOW = 1.2, 0.8   # prior-day actual/planned thresholds (±20 %)
SPIKE_THRESHOLD = 1.5

# The workbook's "Prior-Day Plan Shift" formula scores a Low Bullpen day as tier 4 in its
# harder/easier comparison (everywhere else, and in the README, it's a Medium-tier day = 2).
# False = use tier 2 consistently (matches the documented rule).  True = copy the Excel quirk exactly.
EXCEL_LOW_BULLPEN_QUIRK = False

# ─────────────────────────────────────────────────────────────
# DAY TYPE TEMPLATES  (Day Type Templates tab)
# (category, example#, segment#, segment type, distance ft or None=mound,
#  throws low, throws high, deficit low, deficit high)
# ─────────────────────────────────────────────────────────────
TEMPLATE_SEGMENTS = [
    ("Low", 1, 1, "Long Toss", 90, 45, 55, 14, 18),
    ("Low", 1, 2, "Flat Ground", 60, 15, 25, 12, 14),
    ("Low", 2, 1, "Long Toss", 75, 35, 45, 15, 19),
    ("Low", 2, 2, "Flat Ground", 60, 15, 20, 13, 15),
    ("Medium", 1, 1, "Long Toss", 120, 40, 50, 7, 9),
    ("Medium", 1, 2, "Flat Ground", 60, 15, 20, 5, 7),
    ("Medium", 2, 1, "Compression/Pulldowns", 90, 30, 40, 7, 9),
    ("Medium", 2, 2, "Flat Ground", 60, 15, 20, 5, 7),
    ("High Non-Bullpen", 1, 1, "Long Toss", 150, 30, 40, 7, 9),
    ("High Non-Bullpen", 1, 2, "Compression/Pulldowns", 120, 20, 30, 0, 3),
    ("High Non-Bullpen", 1, 3, "Flat Ground", 60, 15, 20, 4, 6),
    ("High Non-Bullpen", 2, 1, "Long Toss", 180, 25, 35, 4, 6),
    ("High Non-Bullpen", 2, 2, "Compression/Pulldowns", 90, 15, 20, 0, 3),
    ("High Non-Bullpen", 2, 3, "Flat Ground", 60, 15, 20, 4, 6),
    ("High Bullpen", 1, 1, "Long Toss", 90, 20, 30, 7, 9),
    ("High Bullpen", 1, 2, "Bullpen", None, 25, 35, 0, 3),
    ("High Bullpen", 2, 1, "Long Toss", 120, 15, 20, 7, 9),
    ("High Bullpen", 2, 2, "Bullpen", None, 20, 25, 0, 3),
    ("Game", 1, 1, "Bullpen", None, 15, 20, 3, 6),
    ("Game", 1, 2, "Game", None, 20, 30, 0, 3),
    ("Game", 2, 1, "Bullpen", None, 20, 25, 3, 6),
    ("Game", 2, 2, "Game", None, 60, 80, 0, 3),
    ("Low Bullpen", 1, 1, "Long Toss", 90, 20, 30, 14, 18),
    ("Low Bullpen", 1, 2, "Bullpen", None, 20, 25, 7, 9),
    ("Low Bullpen", 2, 1, "Long Toss", 75, 15, 25, 14, 18),
    ("Low Bullpen", 2, 2, "Bullpen", None, 25, 30, 9, 12),
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    try:
        import pandas as pd
        if v is pd.NaT or (not isinstance(v, (str, bytes)) and pd.isna(v)):
            return True
    except Exception:
        pass
    return False


def excel_round(x: float, digits: int = 0) -> float:
    """Excel ROUND (half away from zero) — Python's round() is banker's rounding."""
    m = 10 ** digits
    return math.copysign(math.floor(abs(x) * m + 0.5), x) / m


def _vlookup(x, table):
    """Approximate-match VLOOKUP: row with the largest key <= x (None if below first key)."""
    hit = None
    for row in table:
        if x >= row[0]:
            hit = row
        else:
            break
    return hit


def distance_factor(distance_ft):
    if _blank(distance_ft):
        return None
    r = _vlookup(float(distance_ft), DISTANCE_TABLE)
    return r[1] if r else None


def intensity_factor(deficit):
    if _blank(deficit):
        return None
    return _vlookup(max(float(deficit), 0), INTENSITY_TABLE)[1]


def velo_mid(lo, hi):
    if _blank(lo):
        return None
    if _blank(hi):
        return float(lo)
    return (float(lo) + float(hi)) / 2


def _to_minutes(t):
    if _blank(t):
        return None
    if isinstance(t, time):
        return t.hour * 60 + t.minute + t.second / 60
    if isinstance(t, str):
        parts = t.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1]) + (int(parts[2]) / 60 if len(parts) > 2 else 0)
    if hasattr(t, "hour"):
        return t.hour * 60 + t.minute
    return None


# ─────────────────────────────────────────────────────────────
# THROW LOG ROW CALCULATION  (Throw Log columns G, I, L–Q, U–W, AA–AC)
# ─────────────────────────────────────────────────────────────
def calc_row(r: dict, avg_top) -> dict:
    stype = r.get("session_type")
    avg_top = None if _blank(avg_top) or float(avg_top) == 0 else float(avg_top)

    # Duration (min)
    s, e = _to_minutes(r.get("start_time")), _to_minutes(r.get("end_time"))
    duration = (e - s) if (s is not None and e is not None) else None

    # Throws used in calc — Actual Throw Count overrides the time estimate
    if not _blank(r.get("actual_throws")):
        throws = float(r["actual_throws"])
    elif duration is not None:
        throws = excel_round(duration * THROW_RATE.get(stype, 0))
    else:
        throws = None

    mid = velo_mid(r.get("velo_low"), r.get("velo_high"))
    deficit = (avg_top - mid) if (mid is not None and avg_top is not None) else None

    if stype in MOUND_TYPES:
        factor = MOUND_FACTOR[stype]
    else:
        factor = distance_factor(r.get("distance"))
    intensity = intensity_factor(deficit)

    # Warm-up / bullpen segment (always scored at Bullpen Mound Factor)
    w_mid = velo_mid(r.get("warm_velo_low"), r.get("warm_velo_high"))
    w_def = (avg_top - w_mid) if (w_mid is not None and avg_top is not None) else None
    w_int = intensity_factor(w_def)

    # 60' working-back-in segment (always scored at the 60 ft Distance Factor)
    s_mid = velo_mid(r.get("sixty_velo_low"), r.get("sixty_velo_high"))
    s_def = (avg_top - s_mid) if (s_mid is not None and avg_top is not None) else None
    s_int = intensity_factor(s_def)

    main_ok = throws is not None and factor is not None and intensity is not None
    warm_ok = not _blank(r.get("warm_throws")) and w_int is not None
    sixty_ok = not _blank(r.get("sixty_throws")) and s_int is not None

    if not (main_ok or warm_ok or sixty_ok):
        workload = None
    else:
        workload = (
            (throws * factor * intensity if main_ok else 0)
            + (float(r["warm_throws"]) * MOUND_FACTOR["Bullpen"] * w_int if warm_ok else 0)
            + (float(r["sixty_throws"]) * distance_factor(60) * s_int if sixty_ok else 0)
        )

    return {
        "duration_min": duration,
        "throws_used": throws,
        "velo_mid": mid,
        "avg_top_velo": avg_top,
        "velo_deficit": deficit,
        "dist_mound_factor": factor,
        "intensity_factor": intensity,
        "warm_velo_mid": w_mid,
        "warm_deficit": w_def,
        "warm_intensity": w_int,
        "sixty_velo_mid": s_mid,
        "sixty_deficit": s_def,
        "sixty_intensity": s_int,
        "set_workload": workload,
    }


def daily_totals(log_df) -> dict:
    """{date: summed Set Workload} for one player's calculated log."""
    out: dict = {}
    if log_df is None or len(log_df) == 0:
        return out
    for d, w in zip(log_df["date"], log_df["set_workload"]):
        if _blank(d) or _blank(w):
            continue
        d = d if isinstance(d, date) else d.date()
        out[d] = out.get(d, 0.0) + float(w)
    return out


# ─────────────────────────────────────────────────────────────
# DASHBOARD  (Dashboard tab)
# ─────────────────────────────────────────────────────────────
def zone_for(acwr, chronic):
    if not chronic or acwr is None:
        return INSUFFICIENT_ZONE, INSUFFICIENT_GUIDANCE
    r = _vlookup(acwr, ZONE_TABLE)
    return (r[1], r[2]) if r else ("Insufficient history", "")


def status(daily: dict, as_of: date) -> dict:
    def window(n):
        return sum(daily.get(as_of - timedelta(days=i), 0.0) for i in range(n))

    today = daily.get(as_of, 0.0)
    acute = window(7) / 7
    chronic = window(28) / 28
    acwr = acute / chronic if chronic else None
    zone, guidance = zone_for(acwr, chronic)
    spike = today / chronic if chronic else None
    if spike is None:
        spike_flag = ""
    elif spike > SPIKE_THRESHOLD:
        spike_flag = "High single-day spike — mandatory easy/rest day next session"
    else:
        spike_flag = "OK"
    return dict(today=today, acute=acute, chronic=chronic, acwr=acwr,
                zone=zone, guidance=guidance, spike=spike, spike_flag=spike_flag)


def zone_adjustment(zone: str) -> int:
    if zone in ("Caution", "High Risk"):
        return -1
    if zone == "Undertrained":
        return 1
    return 0


# ─────────────────────────────────────────────────────────────
# DAY TYPE TEMPLATES
# ─────────────────────────────────────────────────────────────
def segment_factor(seg_type, distance):
    if seg_type in MOUND_TYPES:
        return MOUND_FACTOR[seg_type]
    return distance_factor(distance)


def template_rows(avg_top):
    rows = []
    for cat, ex, sg, st, dist, tlo, thi, dlo, dhi in TEMPLATE_SEGMENTS:
        tmid, dmid = (tlo + thi) / 2, (dlo + dhi) / 2
        f = segment_factor(st, dist)
        i = intensity_factor(dmid)
        rows.append(dict(
            category=cat, example=ex, segment=sg, segment_type=st, distance=dist,
            throws_low=tlo, throws_high=thi, throws_mid=tmid,
            deficit_low=dlo, deficit_high=dhi, deficit_mid=dmid,
            velo_low=excel_round(avg_top - dhi) if avg_top else None,
            velo_high=excel_round(avg_top - dlo) if avg_top else None,
            factor=f, intensity=i, workload=tmid * f * i,
        ))
    return rows


def _fmt_num(x):
    return str(int(x)) if x is not None and float(x).is_integer() else str(x)


def segment_text(seg, avg_top):
    where = "Mound" if seg["distance"] is None else f'{seg["distance"]} ft'
    txt = f'{where} — {seg["throws_low"]}-{seg["throws_high"]} throws'
    if avg_top:
        txt += f' @ {_fmt_num(excel_round(avg_top - seg["deficit_high"]))}-{_fmt_num(excel_round(avg_top - seg["deficit_low"]))} mph'
    return txt


def plan_text(day_type: str, avg_top, example: int = 1) -> str:
    if day_type == "No Throw":
        return "Full rest — no throwing today."
    segs = [dict(distance=d, throws_low=tl, throws_high=th, deficit_low=dl, deficit_high=dh)
            for c, ex, _, _, d, tl, th, dl, dh in TEMPLATE_SEGMENTS if c == day_type and ex == example]
    if not segs:
        return ""
    if day_type == "Game" and example == 1:
        # Planner shows this for a Game day (matches workbook)
        return "Game — see warm-up rules (8 entering, +5 each extra inning)"
    return "  +  ".join(segment_text(s, avg_top) for s in segs)


def template_summary(avg_top=None):
    rows = template_rows(avg_top or 0)
    ex_tot: dict = {}
    for r in rows:
        ex_tot[(r["category"], r["example"])] = ex_tot.get((r["category"], r["example"]), 0) + r["workload"]
    summary = []
    for cat in DAY_TYPES:
        summary.append(dict(
            day_type=cat,
            ex1=ex_tot[(cat, 1)], ex2=ex_tot[(cat, 2)],
            avg=(ex_tot[(cat, 1)] + ex_tot[(cat, 2)]) / 2,
        ))
    return summary


TEMPLATE_AVG = {r["day_type"]: r["avg"] for r in template_summary()}


# ─────────────────────────────────────────────────────────────
# NEXT OUTING PLANNER  (Next Outing Planner tab)
# ─────────────────────────────────────────────────────────────
def baseline_day_type(days_until: int) -> str:
    if days_until <= 5:
        return TAPER_RULE.get(days_until, ("Low",))[0]
    return FAR_OUT_CYCLE[(days_until - 6) % 3][0]


def tier(day_type: str) -> int:
    if day_type == "No Throw":
        return 0
    if day_type == "Low":
        return 1
    if day_type in ("Medium", "Low Bullpen"):
        return 2
    if day_type in ("High Non-Bullpen", "High Bullpen"):
        return 3
    return 4


TIER_TO_TYPE = {1: "Low", 2: "Medium", 3: "High Non-Bullpen"}


def build_plan(daily: dict, today: date, target: date, zone_adj: int,
               overrides: dict, avg_top) -> list[dict]:
    rows = []
    prev = None
    for i in range(1, PLANNER_MAX_DAYS + 1):
        d = today + timedelta(days=i)
        if d >= target:
            break
        c = (target - d).days
        ov = overrides.get(d)
        ov = ov if ov and ov != "(none)" else None
        base = ov or baseline_day_type(c)
        e = tier(base)
        prior_date = d - timedelta(days=1)
        g = c + 1
        prior_type = baseline_day_type(g) if prev is None else prev["final"]
        planned = TEMPLATE_AVG.get(prior_type)
        actual = daily.get(prior_date, 0.0)
        ratio = 1.0 if (not planned or not actual) else actual / planned
        l_adj = -1 if ratio > RATIO_HIGH else (1 if ratio < RATIO_LOW else 0)
        if prev is None:
            m_shift = 0
        else:
            pt, pb = tier(prev["final"]), tier(baseline_day_type(prev["days_until"]))
            pt_cmp = 4 if (EXCEL_LOW_BULLPEN_QUIRK and prev["final"] == "Low Bullpen") else pt
            m_shift = 0 if pt == pb else (-1 if pt_cmp > pb else 1)
        combined = m_shift if m_shift != 0 else min(l_adj, zone_adj)
        clamped = min(combined, 0) if c == 1 else combined
        q = min(3, max(1, e + clamped))
        final = ov or (base if q == e else TIER_TO_TYPE[q])
        row = dict(
            date=d, day=d.strftime("%a"), days_until=c, baseline=base, baseline_tier=e,
            prior_date=prior_date, prior_days_until=g, prior_type=prior_type,
            prior_planned=planned, prior_actual=actual, ratio=ratio,
            prior_adj=l_adj, plan_shift=m_shift, zone_adj=zone_adj,
            combined=combined, clamped=clamped, final_tier=q, final=final,
            plan=plan_text(final, avg_top), override=ov or "(none)",
        )
        rows.append(row)
        prev = row
    return rows


def outing_text(target_type, target, avg_top, pitches=None, innings=None) -> str:
    head = f'({target.strftime("%a")} {target.month}/{target.day} — {target_type}) '
    if target_type == "Game":
        has_p, has_i = not _blank(pitches), not _blank(innings)
        if not has_p and not has_i:
            return head + "Enter planned pitches/innings above — velo can't be predicted for a live game."
        if has_p and has_i:
            return head + f"Planned: {_fmt_num(pitches)} pitches over {_fmt_num(innings)} innings"
        return head + (f"Planned: {_fmt_num(pitches)} pitches" if has_p else f"Planned: {_fmt_num(innings)} innings")
    return head + plan_text(target_type, avg_top)
