"""
K-State Baseball — Throw Log (Streamlit)
Run in VS Code:  press ▶ on run.py   — or —   streamlit run app.py
Everything saves automatically the moment it's entered.
"""
from __future__ import annotations

import io
from functools import partial
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import model as m
import storage as db

HERE = os.path.dirname(os.path.abspath(__file__))
PURPLE, DARK_GRAY, LIGHT_GRAY = "#330a57", "#a7a9ac", "#e2e3e4"
TAB_KEY = "player_tab"

st.set_page_config(page_title="K-State Throw Log", page_icon="⚾", layout="wide")
st.markdown(f"""<style>
.block-container {{ padding-top: 3.6rem; max-width: 1240px; }}
h1, h2, h3 {{ color: {PURPLE}; }}
div[data-testid="stMetric"] {{ background: rgba(51,10,87,.05); border-radius: 6px; padding: .5rem .9rem; }}
.jersey {{ background:{PURPLE}; color:#fff; font-weight:800; font-size:2.3rem; line-height:1; border-radius:6px;
  min-width:64px; height:64px; display:flex; align-items:center; justify-content:center; padding:0 8px; }}
.pname {{ font-size:1.9rem !important; font-weight:800; color:{PURPLE}; line-height:1.1; margin:0 0 .15rem 0; }}
.pmeta {{ color:#666; }}
.pill {{ display:inline-block; padding:3px 11px; border-radius:999px; font-weight:700; font-size:.85rem; white-space:nowrap; }}
.zone {{ padding:.65rem 1rem; border-radius:8px; margin:.2rem 0 .6rem 0; }}
.zone b {{ display:block; }}
.z-Undertrained {{ background:#e6eefb; color:#1d4f91; }} .z-Sweet {{ background:#e4f3e8; color:#1b6632; }}
.z-Caution {{ background:#fff2d1; color:#7d5300; }} .z-High {{ background:#fde6e6; color:#a3191c; }}
.z-Insufficient, .z-none {{ background:#eceaef; color:#3d3845; }}
.plan {{ background:rgba(51,10,87,.06); border-radius:8px; padding:.6rem .9rem; margin-bottom:.45rem; }}
.saved {{ color:#1b6632; font-weight:700; font-size:.85rem; }}
.preview {{ background:rgba(51,10,87,.07); border-radius:8px; padding:.7rem 1rem; display:flex; gap:1.6rem; flex-wrap:wrap; align-items:baseline; }}
.preview .k {{ display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; color:#666; }}
.preview .big {{ font-size:2rem; font-weight:800; color:{PURPLE}; line-height:1; }}
button[data-baseweb="tab"] p {{ font-size:.95rem; }}
</style>""", unsafe_allow_html=True)


# ───────────────────────── helpers ─────────────────────────
def chicago_today() -> date:
    return datetime.now(ZoneInfo("America/Chicago")).date()


def fmt(x, d=1, dash="—"):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return dash
    return f"{x:,.{d}f}"


def none_if_nan(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def zkey(zone):
    return (zone or "none").split()[0]


def zshort(zone):
    return (zone or "").split(" (")[0].replace("Insufficient history", "Building history")


def pill(zone):
    return f'<span class="pill z-{zkey(zone)}">● {zshort(zone)}</span>'


def zone_box(zone, guidance):
    return f'<div class="zone z-{zkey(zone)}"><b>Zone: {zone}</b>{guidance}</div>'


def toast(msg):
    st.session_state.setdefault("_toasts", []).append(msg)


def bump(k):
    st.session_state[k] = st.session_state.get(k, 0) + 1


def stamp():
    return datetime.now().strftime("%-I:%M:%S %p") if os.name != "nt" else datetime.now().strftime("%I:%M:%S %p")


def calc_log(pid, avg):
    df = db.load_log(pid)
    calc = pd.DataFrame([m.calc_row(r, avg) for r in df.to_dict("records")], columns=list(m.calc_row({}, None).keys()))
    out = pd.concat([df.reset_index(drop=True), calc], axis=1)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out


def daily_of(pid, avg):
    return m.daily_totals(calc_log(pid, avg))


def tab_label(p):
    return f"{p['number']}  {p['name']}" if p.get("number") not in (None, "") else p["name"]


def to_time(s):
    if not s or (isinstance(s, float) and pd.isna(s)):
        return None
    h, mi = map(int, str(s)[:5].split(":"))
    return time(h, mi)


def time_txt(s):
    t = to_time(s)
    return t.strftime("%I:%M %p").lstrip("0") if t else ""


# ───────────────────────── first run ─────────────────────────
db.seed_if_empty(os.path.join(HERE, "data", "ACWR Throwing Plan Fall 2026.xlsx"))

for msg in st.session_state.pop("_toasts", []):
    st.toast(msg, icon="✅")

players = db.load_players()

# ───────────────────────── sidebar ─────────────────────────
with st.sidebar:
    st.image(os.path.join(HERE, "assets", "baseball-wordmark.png"), width="stretch")
    st.markdown("### Throw Log · Fall 2026")
    today = st.date_input("Today's date", value=chicago_today(), key="today", format="MM/DD/YYYY")
    st.caption("Everything you enter saves automatically.")
    st.divider()
    with st.expander("Import / backup"):
        up = st.file_uploader("Import the ACWR Excel workbook", type=["xlsx"])
        if up is not None and st.button("Import now", type="primary"):
            n_p, n_r = db.import_workbook(io.BytesIO(up.getvalue()))
            toast(f"Imported velo for {n_p} players and {n_r} throw-log rows")
            st.rerun()
        if st.button("Prepare Excel backup"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                players.drop(columns=["active", "sort"]).to_excel(xw, sheet_name="Roster", index=False)
                frames = []
                for p in players.to_dict("records"):
                    lg = calc_log(p["id"], none_if_nan(p["avg_top_velo"])).drop(columns=["id", "created"])
                    lg.insert(0, "player", p["name"])
                    frames.append(lg)
                (pd.concat(frames) if frames else pd.DataFrame()).to_excel(xw, sheet_name="Throw Log", index=False)
            st.session_state["_backup"] = buf.getvalue()
        if st.session_state.get("_backup"):
            st.download_button("Download backup (.xlsx)", st.session_state["_backup"],
                               file_name=f"throw_log_backup_{today.isoformat()}.xlsx", width="stretch")
    st.caption("Set Workload = Throws × Distance/Mound Factor × Intensity Factor. ACWR = 7-day avg ÷ 28-day avg. "
               "Coaching decision-support tool, not a medical instrument.")


# ═════════════════════════ THROW LOG ═════════════════════════
def ek(rid, f):
    return f"ed_{rid}_{f}"


EDIT_FIELDS = ["date", "session_type", "distance", "start_time", "end_time", "actual_throws", "velo_low", "velo_high",
               "warm_throws", "warm_velo_low", "warm_velo_high", "sixty_throws", "sixty_velo_low", "sixty_velo_high", "notes"]


def read_editor(rid, base: dict) -> dict:
    """Current editor values (only the widgets on screen) merged over the saved row."""
    rec = dict(base)
    for f in EDIT_FIELDS:
        k = ek(rid, f)
        if k in st.session_state:
            rec[f] = st.session_state[k]
    if st.session_state.get(ek(rid, "mode")) == "Time it":
        rec["actual_throws"] = None
    if rec.get("session_type") in m.MOUND_TYPES:
        rec["distance"] = None
    return rec


def save_editor(pid, rid):
    base = db.get_row(rid)
    if not base:
        return
    rec = read_editor(rid, base)
    db.update_row(rid, {f: rec.get(f) for f in EDIT_FIELDS})
    st.session_state[f"saved_{rid}"] = f"✓ Saved {stamp()}"


def new_session(pid, copy_from=None):
    rec = dict(copy_from or {"session_type": "Long Toss"})
    rec["date"] = st.session_state.get("today") or chicago_today()
    rec.pop("created", None)
    rid = db.add_row(pid, rec)
    st.session_state[f"edit_{pid}"] = rid
    st.session_state[f"saved_{rid}"] = "✓ New session created — fill it in, it saves as you go"
    st.session_state.pop(f"del_{pid}", None)


def close_editor(pid):
    st.session_state.pop(f"edit_{pid}", None)
    st.session_state.pop(f"del_{pid}", None)
    bump(f"logsel_{pid}")


def delete_session(pid, rid):
    db.delete_row(rid)
    close_editor(pid)
    toast("Session deleted")


def pick_row(pid, key, ids):
    rows = st.session_state[key].selection.rows
    if rows:
        st.session_state[f"edit_{pid}"] = ids[rows[0]]
        st.session_state.pop(f"del_{pid}", None)


def editor(p, avg):
    pid, rid = p["id"], st.session_state.get(f"edit_{p['id']}")
    r = db.get_row(rid) if rid else None
    if not r:
        return
    cb = dict(on_change=save_editor, args=(pid, rid))
    mound = r["session_type"] in m.MOUND_TYPES
    with st.container(border=True):
        h = st.columns([3, 2, 1, 1, 1], vertical_alignment="center")
        d = date.fromisoformat(r["date"]) if r.get("date") else None
        h[0].markdown(f"#### {d.strftime('%A, %b %-d') if d and os.name != 'nt' else (d.strftime('%A, %b %d') if d else 'New session')}")
        h[1].markdown(f"<span class='saved'>{st.session_state.get(f'saved_{rid}', '')}</span>", unsafe_allow_html=True)
        h[2].button("Copy as new", key=f"copy_{rid}", on_click=new_session, args=(pid, r), width="stretch")
        if st.session_state.get(f"del_{pid}"):
            h[3].button("Delete it", key=f"dely_{rid}", type="primary", on_click=delete_session, args=(pid, rid), width="stretch")
            h[4].button("Keep", key=f"deln_{rid}", on_click=lambda: st.session_state.pop(f"del_{pid}", None), width="stretch")
        else:
            h[3].button("Delete", key=f"del_{rid}", on_click=lambda: st.session_state.update({f"del_{pid}": True}), width="stretch")
            h[4].button("Done", key=f"done_{rid}", type="primary", on_click=close_editor, args=(pid,), width="stretch")

        c = st.columns([1.2, 1.6, 1.2, 2])
        c[0].date_input("Date", value=d, key=ek(rid, "date"), format="MM/DD/YYYY", **cb)
        c[1].selectbox("Session type", m.SESSION_TYPES, index=m.SESSION_TYPES.index(r["session_type"]) if r["session_type"] in m.SESSION_TYPES else 1,
                       key=ek(rid, "session_type"), **cb)
        stype = st.session_state.get(ek(rid, "session_type"), r["session_type"])
        mound, rest = stype in m.MOUND_TYPES, stype == "No Throw"
        if not rest:
            if mound:
                c[2].text_input("Distance", "Mound (60′6″)", disabled=True, key=ek(rid, "mound_note"),
                                help="Bullpen/Game use the flat Mound Factor instead of distance")
            else:
                c[2].number_input("Distance (ft)", 0, 400, none_if_nan(r["distance"]) and int(r["distance"]), 5,
                                  key=ek(rid, "distance"), placeholder="e.g. 120", **cb)
            default_mode = "Exact count" if (none_if_nan(r["actual_throws"]) is not None or (mound and not r["start_time"])) else "Time it"
            c[3].segmented_control("Throw count", ["Time it", "Exact count"], default=default_mode, required=True,
                                   key=ek(rid, "mode"), on_change=save_editor, args=(pid, rid),
                                   help="Time a group session (throws estimated from pace) or type the exact count")
            mode = st.session_state.get(ek(rid, "mode"), default_mode)
            c2 = st.columns(4)
            if mode == "Time it":
                c2[0].time_input("Start", value=to_time(r["start_time"]), key=ek(rid, "start_time"), step=60, **cb)
                c2[1].time_input("End", value=to_time(r["end_time"]), key=ek(rid, "end_time"), step=60, **cb)
            else:
                c2[0].number_input("Throws (live + in-game WU)" if stype == "Game" else "Actual throws", 0, 400,
                                   none_if_nan(r["actual_throws"]) and int(r["actual_throws"]), 1,
                                   key=ek(rid, "actual_throws"), placeholder="e.g. 25", **cb)
            c2[2].number_input("Velo low (mph)", 0.0, 110.0, none_if_nan(r["velo_low"]), 1.0, format="%.1f", key=ek(rid, "velo_low"), placeholder="e.g. 75", **cb)
            c2[3].number_input("Velo high (mph)", 0.0, 110.0, none_if_nan(r["velo_high"]), 1.0, format="%.1f", key=ek(rid, "velo_high"), placeholder="e.g. 81", **cb)
            e1, e2 = st.columns(2)
            with e1.expander("Pen warm-up before entering (game days)", expanded=stype == "Game" or none_if_nan(r["warm_throws"]) is not None):
                st.caption("Scored at the Bullpen Mound Factor.")
                w = st.columns(3)
                w[0].number_input("Throws", 0, 200, none_if_nan(r["warm_throws"]) and int(r["warm_throws"]), 1, key=ek(rid, "warm_throws"), **cb)
                w[1].number_input("Velo low", 0.0, 110.0, none_if_nan(r["warm_velo_low"]), 1.0, format="%.1f", key=ek(rid, "warm_velo_low"), **cb)
                w[2].number_input("Velo high", 0.0, 110.0, none_if_nan(r["warm_velo_high"]), 1.0, format="%.1f", key=ek(rid, "warm_velo_high"), **cb)
            with e2.expander("Finished working back in at 60′", expanded=none_if_nan(r["sixty_throws"]) is not None):
                st.caption("Same entry, scored at the 60 ft Distance Factor.")
                w = st.columns(3)
                w[0].number_input("Throws", 0, 200, none_if_nan(r["sixty_throws"]) and int(r["sixty_throws"]), 1, key=ek(rid, "sixty_throws"), **cb)
                w[1].number_input("Velo low", 0.0, 110.0, none_if_nan(r["sixty_velo_low"]), 1.0, format="%.1f", key=ek(rid, "sixty_velo_low"), **cb)
                w[2].number_input("Velo high", 0.0, 110.0, none_if_nan(r["sixty_velo_high"]), 1.0, format="%.1f", key=ek(rid, "sixty_velo_high"), **cb)
        else:
            st.caption("Rest day. It's saved so the day counts as zero in your log.")
        st.text_input("Notes (arm feel, RPE, etc.)", value=r["notes"] or "", key=ek(rid, "notes"), **cb)

        cur = read_editor(rid, r)
        if rest:
            st.markdown("<div class='preview'>Rest day: workload 0</div>", unsafe_allow_html=True)
        else:
            cc = m.calc_row(cur, avg)
            est = f" <span style='color:#666'>({fmt(cc['duration_min'], 0)} min)</span>" if cc["duration_min"] is not None and cur.get("actual_throws") is None else ""
            off = f" <span style='color:#666'>({fmt(cc['velo_deficit'])} mph off)</span>" if cc["velo_deficit"] is not None else ""
            hint = "" if cc["set_workload"] is not None else "<div style='flex-basis:100%;color:#666;font-size:.85rem'>Add throws (or start + end time) and velo to see the workload.</div>"
            st.markdown(f"""<div class='preview'>
              <div><span class='k'>Set Workload</span><span class='big'>{fmt(cc['set_workload'])}</span></div>
              <div><span class='k'>Throws</span><b>{fmt(cc['throws_used'], 0)}</b>{est}</div>
              <div><span class='k'>{'Mound' if mound else 'Distance'} factor</span><b>{fmt(cc['dist_mound_factor'])}</b></div>
              <div><span class='k'>Intensity factor</span><b>{fmt(cc['intensity_factor'])}</b>{off}</div>{hint}</div>""", unsafe_allow_html=True)


def throw_log_tab(p, avg):
    pid = p["id"]
    a, b = st.columns([1, 3], vertical_alignment="center")
    a.button("＋ Log a session", type="primary", on_click=new_session, args=(pid,), key=f"new_{pid}", width="stretch")
    b.caption("Everything saves automatically as you type: press Enter or click out of a box.")
    editor(p, avg)

    st.markdown("### My throw log")
    log = calc_log(pid, avg)
    if log.empty:
        st.info("No sessions logged yet. Tap **＋ Log a session** after you throw. Your workload, ACWR and plan fill in from here.")
    else:
        view = pd.DataFrame({
            "Date": log["date"], "Session Type": log["session_type"], "Set Workload": log["set_workload"],
            "Distance": [("Mound" if s in m.MOUND_TYPES else ("" if pd.isna(d) else f"{d:.0f}")) for s, d in zip(log["session_type"], log["distance"])],
            "Start": log["start_time"].map(time_txt), "End": log["end_time"].map(time_txt), "Throws Used": log["throws_used"],
            "Velo": [("" if pd.isna(lo) else f"{lo:g}" + ("" if pd.isna(hi) else f"–{hi:g}")) for lo, hi in zip(log["velo_low"], log["velo_high"])],
            "Deficit": log["velo_deficit"], "Dist/Mound F.": log["dist_mound_factor"], "Intensity F.": log["intensity_factor"],
            "Pen WU": log["warm_throws"], "60′": log["sixty_throws"], "Notes": log["notes"].fillna("")})
        ids = list(log["id"])
        key = f"logtable_{pid}_{st.session_state.get(f'logsel_{pid}', 0)}"
        st.dataframe(view, hide_index=True, width="stretch", height=min(520, 38 + 35 * len(view)),
                     on_select=partial(pick_row, pid, key, ids), selection_mode="single-row", key=key,
                     column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD/YY"),
                                    "Set Workload": st.column_config.NumberColumn(format="%.1f"),
                                    "Throws Used": st.column_config.NumberColumn(format="%.0f"),
                                    "Deficit": st.column_config.NumberColumn(format="%.1f"),
                                    "Dist/Mound F.": st.column_config.NumberColumn(format="%.1f"),
                                    "Intensity F.": st.column_config.NumberColumn(format="%.1f"),
                                    "Pen WU": st.column_config.NumberColumn(format="%.0f"),
                                    "60′": st.column_config.NumberColumn(format="%.0f"),
                                    "Notes": st.column_config.TextColumn(width="large")})
        st.caption("Click a row (the box at its left edge) to edit it.")
    with st.expander("How to log (long toss, game days, 60′ finish)"):
        st.markdown("""
- **One entry per throwing set.** Long toss = two entries: *Long Toss* at the farthest distance working back, then *Compression/Pulldowns* at the working-in distance.
- **Time it or count it.** Start/End time estimates throws from pace (Long Toss 3/min, Compression 3/min, Moderate 3.5/min, Recovery 4.5/min). An exact count always overrides.
- **Bullpen / Game:** no distance. A flat Mound Factor is used (Bullpen 3.0, Game 3.2). Enter the exact pitch count.
- **Game day = one entry.** Throws = live pitches + in-game warm-ups (8 entering, +5 for each extra inning). Pen warm-ups before entering go in the *Pen warm-up* section.
- **Finished working back in at 60′?** Use the 60′ section on the same entry.
- **Velo:** enter a range, e.g. 70–74. The midpoint is compared to your Avg Top Velo to set intensity.""")


# ═════════════════════════ DASHBOARD ═════════════════════════
def dashboard_tab(p, avg, daily):
    as_of = st.date_input("As of date", value=today, key=f"asof_{p['id']}", format="MM/DD/YYYY")
    s = m.status(daily, as_of)
    c = st.columns(5)
    c[0].metric("Today's workload", fmt(s["today"]))
    c[1].metric("Acute · 7-day avg/day", fmt(s["acute"]))
    c[2].metric("Chronic · 28-day avg/day", fmt(s["chronic"]))
    c[3].metric("ACWR · acute ÷ chronic", fmt(s["acwr"], 2, "N/A"))
    c[4].metric("Spike · today ÷ chronic", fmt(s["spike"], 2, "N/A"))
    st.markdown(zone_box(s["zone"], s["guidance"]), unsafe_allow_html=True)
    if s["spike_flag"]:
        st.markdown(f"<div class='zone z-{'Sweet' if s['spike_flag'] == 'OK' else 'High'}'><b>Spike flag: {s['spike_flag']}</b></div>",
                    unsafe_allow_html=True)
    st.markdown("### 28-day trend")
    days = [as_of - timedelta(days=27 - i) for i in range(28)]
    trend = pd.DataFrame({"Day": [d.strftime("%m/%d") for d in days], "Weekday": [d.strftime("%a") for d in days],
                          "Daily Workload": [daily.get(d, 0.0) for d in days]})
    bars = alt.Chart(trend).mark_bar(color=DARK_GRAY, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Day:O", title=None, sort=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("Daily Workload:Q", title="Daily workload"),
        tooltip=["Weekday", "Day", alt.Tooltip("Daily Workload:Q", format=".1f")])
    lines = pd.DataFrame({"Line": [f"Acute (7d avg) {s['acute']:.1f}", f"Chronic (28d avg) {s['chronic']:.1f}"], "v": [s["acute"], s["chronic"]]})
    rules = alt.Chart(lines).mark_rule(strokeWidth=2.5).encode(
        y="v:Q", color=alt.Color("Line:N", scale=alt.Scale(range=[PURPLE, "#555555"]), legend=alt.Legend(title=None, orient="top")),
        strokeDash=alt.StrokeDash("Line:N", scale=alt.Scale(range=[[1, 0], [7, 5]]), legend=None))
    st.altair_chart((bars + rules).properties(height=300), width="stretch")


# ═════════════════════════ DAY TYPE TEMPLATES ═════════════════════════
def templates_tab(p, avg):
    st.caption(f"Velo targets shown for **{p['name']}**" + (f" (Avg Top Velo {fmt(avg)} mph)." if avg else " (set your Avg Top Velo to see mph targets).") +
               " Workloads come from distance and mph-deficit bands, so they're the same for every pitcher. Low, Medium and High "
               "Non-Bullpen days finish at 60 ft working all pitches; High Bullpen and Game days skip that finish.")
    rows = m.template_rows(avg or 0)
    plans = {}
    for r in rows:
        plans.setdefault((r["category"], r["example"]), []).append(m.segment_text(r, avg))
    summ = m.template_summary(avg)
    st.markdown("### Day type quick reference")
    st.dataframe(pd.DataFrame([{"Day Type": s["day_type"], "Avg Projected Workload": s["avg"],
                                "Example 1": "  +  ".join(plans[(s["day_type"], 1)]), "Ex 1": s["ex1"],
                                "Example 2": "  +  ".join(plans[(s["day_type"], 2)]), "Ex 2": s["ex2"]} for s in summ]),
                 hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.1f") for k in ("Avg Projected Workload", "Ex 1", "Ex 2")}
                 | {"Example 1": st.column_config.TextColumn(width="large"), "Example 2": st.column_config.TextColumn(width="large")})
    st.caption("Low Bullpen = low-intent mound work (feel pen, about 7–12 mph under Avg Top Velo). Same Mound Factor as any bullpen; "
               "the lower Intensity Factor keeps its workload near a Medium day.")
    st.markdown("### Segment detail")
    det = pd.DataFrame([{"Category": r["category"], "Ex": r["example"], "Seg": r["segment"], "Segment Type": r["segment_type"],
                         "Distance": "Mound" if r["distance"] is None else f"{r['distance']} ft",
                         "Throws": f"{r['throws_low']}–{r['throws_high']}", "Deficit (mph)": f"{r['deficit_low']}–{r['deficit_high']}",
                         "Velo (mph)": f"{r['velo_low']:.0f}–{r['velo_high']:.0f}" if avg else "—",
                         "Dist/Mound F.": r["factor"], "Intensity F.": r["intensity"], "Projected Workload": r["workload"]} for r in rows])
    st.dataframe(det, hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.1f") for k in ("Dist/Mound F.", "Intensity F.", "Projected Workload")})
    st.caption("Deficit = mph below Avg Top Velo: 0–3 max effort (×2.0), 4–6 compete (×1.5), 7–9 building (×1.0), 10+ easy/recovery (×0.6).")


# ═════════════════════════ NEXT OUTING PLANNER ═════════════════════════
def save_planner(pid):
    k = lambda f: st.session_state.get(f"pl_{pid}_{f}")
    fields = {"target_type": k("type"), "target_date": k("date")}
    if f"pl_{pid}_pitches" in st.session_state:
        fields["planned_pitches"] = k("pitches")
    if f"pl_{pid}_innings" in st.session_state:
        fields["planned_innings"] = k("innings")
    db.update_player(pid, **fields)
    st.session_state[f"plsaved_{pid}"] = f"✓ Saved {stamp()}"


def save_overrides(pid, key, dates):
    for i, ch in st.session_state[key]["edited_rows"].items():
        if "override" in ch:
            db.save_override(pid, dates[int(i)], ch["override"])
    st.session_state[f"plsaved_{pid}"] = f"✓ Override saved {stamp()}"
    bump(f"plv_{pid}")


def clear_all_overrides(pid):
    db.clear_overrides(pid)
    bump(f"plv_{pid}")
    st.session_state[f"plsaved_{pid}"] = "✓ Overrides cleared"


def planner_tab(p, avg, daily):
    pid = p["id"]
    cb = dict(on_change=save_planner, args=(pid,))
    c = st.columns([1.4, 1.2, 1, 1, 1.4], vertical_alignment="bottom")
    ttype = c[0].selectbox("Next high-intent day", m.HIGH_INTENT_TYPES, key=f"pl_{pid}_type",
                           index=m.HIGH_INTENT_TYPES.index(p["target_type"]) if p["target_type"] in m.HIGH_INTENT_TYPES else 0, **cb)
    tdate = c[1].date_input("Date", value=p["target_date"], key=f"pl_{pid}_date", format="MM/DD/YYYY", **cb)
    pitches, innings = p["planned_pitches"], p["planned_innings"]
    if ttype == "Game":
        pitches = c[2].number_input("Planned pitches", 0, 150, pitches and int(pitches), 1, key=f"pl_{pid}_pitches", placeholder="optional", **cb)
        innings = c[3].number_input("Planned innings", 0.0, 9.0, innings, 1.0, format="%.1f", key=f"pl_{pid}_innings", placeholder="optional", **cb)
    c[4].markdown(f"<span class='saved'>{st.session_state.get(f'plsaved_{pid}', '')}</span>", unsafe_allow_html=True)

    s = m.status(daily, today)
    za = m.zone_adjustment(s["zone"])
    st.markdown("### Current status, last 7 / last 28 days")
    cc = st.columns(4)
    cc[0].metric("Acute · 7-day", fmt(s["acute"]))
    cc[1].metric("Chronic · 28-day", fmt(s["chronic"]))
    cc[2].metric("ACWR", fmt(s["acwr"], 2, "N/A"))
    cc[3].metric("Zone adjustment", f"{za:+d}" if za else "0")
    st.markdown(zone_box(s["zone"], s["guidance"]), unsafe_allow_html=True)

    if not tdate:
        st.info("Pick the date of your next Game outing or High Bullpen day to build the plan.")
        return
    if tdate <= today:
        st.warning("That date is today or already past. Update it to your **next** outing or bullpen day and the whole plan regenerates.")
        return
    plan = m.build_plan(daily, today, tdate, za, db.load_overrides(pid), avg)
    st.markdown("### Quick glance")
    if plan:
        r0 = plan[0]
        st.markdown(f"<div class='plan'><b>Tomorrow, {r0['date']:%a %m/%d}: {r0['final']}</b><br>{r0['plan']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='plan'><b>Outing / bullpen day</b><br>{m.outing_text(ttype, tdate, avg, pitches, innings)}</div>",
                unsafe_allow_html=True)
    st.markdown("### This week's plan")
    if not plan:
        st.caption("Your High-Intent Day is tomorrow, so there are no days to plan in between.")
        return
    df = pd.DataFrame(plan)
    view = pd.DataFrame({"Date": df["date"], "Days until": df["days_until"], "Baseline": df["baseline"],
                         "Day type": df["final"], "override": df["override"], "Suggested plan (Example 1)": df["plan"]})
    key = f"plan_{pid}_{st.session_state.get(f'plv_{pid}', 0)}"
    st.data_editor(view, hide_index=True, width="stretch", key=key, on_change=save_overrides, args=(pid, key, list(df["date"])),
                   disabled=["Date", "Days until", "Baseline", "Day type", "Suggested plan (Example 1)"],
                   column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD"),
                                  "override": st.column_config.SelectboxColumn("Manual override ✎", options=m.OVERRIDE_CHOICES, required=True,
                                                                               help="Pick a day type. It saves and every day after re-plans around it."),
                                  "Suggested plan (Example 1)": st.column_config.TextColumn(width="large")})
    a, b = st.columns([1, 3])
    a.button("Clear all overrides", key=f"clr_{pid}", on_click=clear_all_overrides, args=(pid,))
    if b.toggle("Show the math behind each day", key=f"math_{pid}"):
        st.dataframe(pd.DataFrame({"Date": df["date"], "Baseline tier": df["baseline_tier"], "Prior day type": df["prior_type"],
                                   "Prior planned": df["prior_planned"], "Prior actual": df["prior_actual"], "Actual/planned": df["ratio"],
                                   "Prior-day adj": df["prior_adj"], "Plan shift": df["plan_shift"], "Zone adj": df["zone_adj"],
                                   "Combined": df["combined"], "Clamped": df["clamped"], "Final tier": df["final_tier"]}),
                     hide_index=True, width="stretch",
                     column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD"),
                                    "Prior planned": st.column_config.NumberColumn(format="%.1f"),
                                    "Prior actual": st.column_config.NumberColumn(format="%.1f"),
                                    "Actual/planned": st.column_config.NumberColumn(format="%.2f")})
    with st.expander("How the plan is built"):
        x, y = st.columns(2)
        x.dataframe(pd.DataFrame([{"Days until": k, "Default day type": v[0], "Why": v[1]} for k, v in m.TAPER_RULE.items()]), hide_index=True)
        y.dataframe(pd.DataFrame([{"(Days−6) mod 3": k, "Day type (6+ days out)": v[0], "Why": v[1]} for k, v in m.FAR_OUT_CYCLE.items()]), hide_index=True)
        st.markdown("""
- Each day starts from its baseline, then moves one tier (Low → Medium → High Non-Bullpen).
- **Prior-day plan shift:** if the day before ended harder or easier than its own baseline (for example from an override), that decides the adjustment on its own.
- Otherwise it takes the more conservative of: yesterday's actual logged workload vs. plan (more than 20% over = −1, more than 20% under = +1) and the zone (Caution/High Risk −1, Undertrained +1). A downgrade needs one signal; an upgrade needs both.
- The day before the high-intent day can only be downgraded. An upgrade out of Medium goes to High Non-Bullpen, never a bullpen.""")


# ═════════════════════════ PLAYER PAGE ═════════════════════════
def save_avg(pid):
    db.update_player(pid, avg_top_velo=st.session_state.get(f"avg_{pid}"))
    toast("Avg Top Velo saved")


def player_page(p):
    pid, avg = p["id"], none_if_nan(p["avg_top_velo"])
    daily = daily_of(pid, avg)
    s = m.status(daily, today)
    with st.container(border=True):
        h = st.columns([0.65, 2.4, 1.4, 1.15, 1.15, 1.25], vertical_alignment="center")
        h[0].markdown(f"<div class='jersey'>{p['number'] or ''}</div>", unsafe_allow_html=True)
        meta = " · ".join(x for x in (p.get("position"), p.get("year"), p.get("bt")) if x)
        h[1].markdown(f"<div class='pname'>{p['name']}</div><span class='pmeta'>{meta}</span>", unsafe_allow_html=True)
        h[2].number_input("Avg Top Velo (mph)", 40.0, 110.0, avg, 0.1, format="%.1f", key=f"avg_{pid}", placeholder="set this first",
                          on_change=save_avg, args=(pid,))
        h[3].metric("Today", fmt(s["today"]))
        h[4].metric("ACWR", fmt(s["acwr"], 2, "N/A"))
        h[5].markdown(f"<div style='font-size:.85rem;color:#666'>Zone</div>{pill(s['zone'])}", unsafe_allow_html=True)
    if not avg:
        st.warning("Enter your **Avg Top Velo** above (the average of your hardest, most competitive readings, not one peak). "
                   "Intensity and workload can't be calculated without it.")
    sub = st.segmented_control("Section", ["Throw Log", "Dashboard", "Day Type Templates", "Next Outing Planner"],
                               default="Throw Log", required=True, key="sub", label_visibility="collapsed")
    if sub == "Dashboard":
        dashboard_tab(p, avg, daily)
    elif sub == "Day Type Templates":
        templates_tab(p, avg)
    elif sub == "Next Outing Planner":
        planner_tab(p, avg, daily)
    else:
        throw_log_tab(p, avg)


# ═════════════════════════ TEAM ═════════════════════════
def open_player(key, labels):
    rows = st.session_state[key].selection.rows
    if rows:
        st.session_state[TAB_KEY] = labels[rows[0]]
        bump("teamsel")


def save_roster(key, ids):
    for i, ch in st.session_state[key]["edited_rows"].items():
        fields = {}
        for col, f in (("#", "number"), ("Position", "position"), ("Avg Top Velo", "avg_top_velo"), ("Peak Velo", "peak_velo")):
            if col in ch:
                fields[f] = ch[col]
        db.update_player(ids[int(i)], **fields)
    toast("Roster saved")


def team_page():
    st.markdown(f"### Staff overview · {today:%A, %b %d}")
    rows = []
    for p in players.to_dict("records"):
        avg = none_if_nan(p["avg_top_velo"])
        daily = daily_of(p["id"], avg)
        s = m.status(daily, today)
        nxt = tmr = "—"
        td = p["target_date"] if isinstance(p["target_date"], date) else None
        if td and td > today:
            nxt = f"{p['target_type'] or 'Game'} · {td:%a %m/%d}"
            plan = m.build_plan(daily, today, td, m.zone_adjustment(s["zone"]), db.load_overrides(p["id"]), avg)
            tmr = plan[0]["final"] if plan else (p["target_type"] or "Game")
        zone = zshort(s["zone"])
        rows.append({"#": p["number"], "Player": p["name"], "Pos": p["position"], "Avg Top Velo": avg,
                     "Sessions": len(db.load_log(p["id"])), "Today": s["today"], "ACWR": s["acwr"],
                     "Zone": {"Sweet Spot": "🟢 ", "Caution": "🟡 ", "High Risk": "🔴 ", "Undertrained": "🔵 "}.get(zone, "⚪ ") + zone,
                     "Spike": "🔴 Spike" if s["spike_flag"] not in ("", "OK") else (s["spike_flag"] or "—"),
                     "Next high-intent day": nxt, "Tomorrow": tmr})
    labels = [tab_label(p) for p in players.to_dict("records")]
    key = f"team_{st.session_state.get('teamsel', 0)}"
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=38 + 35 * len(rows), key=key,
                 on_select=partial(open_player, key, labels), selection_mode="single-row",
                 column_config={"Avg Top Velo": st.column_config.NumberColumn(format="%.1f"),
                                "Today": st.column_config.NumberColumn(format="%.1f"),
                                "ACWR": st.column_config.NumberColumn(format="%.2f")})
    st.caption("Click a player's row to open his tab.")

    st.markdown("### Roster")
    st.caption("**Avg Top Velo** drives the Intensity Factor: the average of several of his hardest, most competitive readings, "
               "not a single peak. Peak Velo is reference only. Edits save as soon as you leave the cell.")
    ros = pd.DataFrame({"#": players["number"], "Name": players["name"], "Position": players["position"],
                        "Avg Top Velo": players["avg_top_velo"], "Peak Velo": players["peak_velo"]})
    rkey = f"roster_{st.session_state.get('rosv', 0)}"
    st.data_editor(ros, hide_index=True, width="stretch", key=rkey, on_change=save_roster, args=(rkey, list(players["id"])),
                   disabled=["Name"], column_config={
                       "Avg Top Velo": st.column_config.NumberColumn("Avg Top Velo ✎", format="%.1f", min_value=40, max_value=110),
                       "Peak Velo": st.column_config.NumberColumn("Peak Velo ✎", format="%.1f", min_value=40, max_value=110),
                       "#": st.column_config.TextColumn("# ✎"), "Position": st.column_config.TextColumn("Position ✎")})
    a, b = st.columns(2)
    with a.form("add_player", clear_on_submit=True, border=True):
        st.markdown("**Add a player**")
        f = st.columns([1, 2.4, 1.2, 1.4])
        num = f[0].text_input("Jersey #")
        name = f[1].text_input("Name")
        pos = f[2].text_input("Position", "RHP")
        avg = f[3].number_input("Avg Top Velo", 40.0, 110.0, None, 0.1, format="%.1f")
        if st.form_submit_button("Add player", type="primary"):
            if name.strip():
                db.add_player(name, num.strip(), pos.strip() or "RHP", avg_top=avg)
                bump("rosv")
                toast(f"Added {name.strip()}")
                st.rerun()
            else:
                st.error("Type a name first.")
    with b.container(border=True):
        st.markdown("**Remove a player**")
        rm = st.selectbox("Player", ["—"] + list(players["name"]), key="rm_pick", label_visibility="collapsed")
        if rm != "—":
            if st.session_state.get("rm_confirm") == rm:
                x, y = st.columns(2)
                if x.button(f"Remove {rm}", type="primary"):
                    db.remove_player(players.loc[players["name"] == rm, "id"].iloc[0])
                    st.session_state.pop("rm_confirm", None)
                    toast(f"Removed {rm}. His log is kept and comes back if he's added again.")
                    st.rerun()
                if y.button("Keep"):
                    st.session_state.pop("rm_confirm", None)
                    st.rerun()
            elif st.button("Remove"):
                st.session_state["rm_confirm"] = rm
                st.rerun()
        st.caption("Removing hides his tab. His throw log is kept.")


# ═════════════════════════ LAYOUT ═════════════════════════
plist = players.to_dict("records")
labels = ["🏠 Team"] + [tab_label(p) for p in plist]
if st.session_state.get(TAB_KEY) not in labels:
    st.session_state.pop(TAB_KEY, None)
tabs = st.tabs(labels, key=TAB_KEY, on_change="rerun")
if tabs[0].open:
    with tabs[0]:
        team_page()
for tab, p in zip(tabs[1:], plist):
    if tab.open:
        with tab:
            player_page(p)
