"""Psychological-pressure factors: build per-ball flags, then test them in three stages.
  Stage 1  league-wide effect: do players perform differently in the situation? (match-clustered SE)
  Stage 2  player-level repeatability: do players differ consistently? (split-half)
  Stage 3  model improvement: does adding a psych component improve cross-half prediction?
Usage (after the main pipeline, from the repo root): python -I experiments/psych_factors_test.py out "<data_dir>"
"""
import sys, importlib.util, json, numpy as np, pandas as pd
import os
OUT, D = sys.argv[1], sys.argv[2]; RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py")
sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
rng = np.random.default_rng(7)

b = pd.read_pickle(f"{OUT}/balls_scored.pkl").sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)
b["recent"] = b.age_days <= 365
m = pd.read_csv(f"{D}/matches.csv")
pe = pd.read_csv(f"{D}/playing_eleven.csv")

# ======================= 1. STADIUM / OCCASION =======================
UK = {"England", "Scotland", "Ireland"}
CARIB = {"West Indies", "Jamaica", "Barbados", "Trinidad and Tobago", "Guyana", "Antigua and Barbuda",
         "St Lucia", "Saint Lucia", "St Kitts and Nevis", "Grenada", "Dominica", "St Vincent"}
mm = m.set_index("match_id")
ipl_m = mm[mm.index.isin(b[b.league == "IPL"].match_id.unique())]
# an IPL team's real home grounds: venues hosting >=20% of its designated home games in 2023-26
hv = (ipl_m[pd.to_datetime(ipl_m.match_date) >= "2023-01-01"].groupby("home_team_id").venue_id
      .value_counts(normalize=True))
home_venues = {t: set(v.index[v >= 0.2]) for t, v in hv.groupby(level=0) for v in [v.droplevel(0)]}
def is_home(team_id, team_name, mid):
    row = mm.loc[mid]
    if mid in ipl_m.index:
        return row.venue_id in home_venues.get(team_id, set())
    vc = str(row.venue_country)
    return (vc == team_name) or (team_name in UK and vc == "United Kingdom") or (team_name == "West Indies" and vc in CARIB | {"West Indies"})
tname = pd.concat([m[["home_team_id", "home_team"]].set_axis(["id", "n"], axis=1),
                   m[["away_team_id", "away_team"]].set_axis(["id", "n"], axis=1)]).drop_duplicates("id").set_index("id").n
side = {}
for mid in b.match_id.unique():
    row = mm.loc[mid]
    for t in (row.home_team_id, row.away_team_id):
        side[(mid, t)] = is_home(t, tname.get(t, ""), mid)
def venue_state(team_col, opp_col):
    h = np.array([side.get((a, t), False) for a, t in zip(b.match_id, b[team_col])])
    o = np.array([side.get((a, t), False) for a, t in zip(b.match_id, b[opp_col])])
    return np.where(h, "home", np.where(o, "away", "neutral"))
b["bat_venue"] = venue_state("batting_team_id", "bowling_team_id")
b["bowl_venue"] = venue_state("bowling_team_id", "batting_team_id")
BIG = {"Final", "Qualifier", "Eliminator", "Semi Final", "Super 4"}
b["big_occasion"] = b.match_id.map(mm.stage).isin(BIG) | (b.knock_out == 1)

# ======================= 2. SELF-INFLICTED (batter) =======================
f = b.faced
g = b[f].groupby(["match_id", "innings", "striker_id"])
b.loc[f, "bat_balls_before"] = g.cumcount()
b.loc[f, "bat_runs_before"] = g.bat_runs.cumsum() - b.loc[f, "bat_runs"]
dot = (b.loc[f, "bat_runs"] == 0).astype(int)
grp = (dot != dot.groupby([b.loc[f, "match_id"], b.loc[f, "innings"], b.loc[f, "striker_id"]]).shift().fillna(-1)).cumsum()
run_len = dot.groupby(grp).cumsum()                                      # consecutive dots incl. this ball
b.loc[f, "bat_dot_streak"] = run_len.groupby([b.loc[f, "match_id"], b.loc[f, "innings"], b.loc[f, "striker_id"]]).shift().fillna(0)
sr_so_far = 100 * b.bat_runs_before / b.bat_balls_before.replace(0, np.nan)
b["stuck"] = f & ((b.bat_dot_streak >= 3) | ((b.bat_balls_before >= 10) & (sr_so_far < 100)))
b["milestone"] = f & b.bat_runs_before.between(40, 49)
# poor recent form: average of the batter's previous 3 innings (any format) below 12
inns = (b[f].groupby(["striker_id", "match_id"]).agg(d=("match_date", "first"), runs=("bat_runs", "sum"))
        .reset_index().sort_values(["striker_id", "d", "match_id"]))
inns["prev3"] = inns.groupby("striker_id").runs.transform(lambda s: s.shift().rolling(3, min_periods=3).mean())
b = b.merge(inns[["striker_id", "match_id", "prev3"]], on=["striker_id", "match_id"], how="left")
b["poor_form_bat"] = f & (b.prev3 < 12)

# ======================= 3. CAUSED BY OTHERS (batter) =======================
b["new_at_crease"] = f & (b.bat_balls_before < 5) & (b.batting_order >= 3)
gi = b.groupby(["match_id", "innings"])
# wickets in the last 12 legal balls before this ball
key = b.set_index(["match_id", "innings", "legal_before"]).wkts_before
first_at = key[~key.index.duplicated()]
lag = pd.MultiIndex.from_arrays([b.match_id, b.innings, (b.legal_before - 12).clip(lower=0)])
b["wkts_last12"] = b.wkts_before.values - first_at.reindex(lag).values
b["collapse"] = f & (b.wkts_last12 >= 2)
# team dot-ball streak (legal balls with no run) before this ball
tdot = ((b.total_runs == 0) & b.legal).astype(int)
tg = (tdot != tdot.groupby([b.match_id, b.innings]).shift().fillna(-1)).cumsum()
b["team_dot_streak"] = tdot.groupby(tg).cumsum().groupby([b.match_id, b.innings]).shift().fillna(0)
b["dot_pressure"] = f & (b.team_dot_streak >= 4)
# a run-out in the previous 6 legal balls
ro = (b.wkt & b.dismissal_type.astype(str).str.contains("Run", case=False)).astype(int)
ro_cum = ro.groupby([b.match_id, b.innings]).cumsum() - ro
ro_key = pd.Series(ro_cum.values, index=pd.MultiIndex.from_arrays([b.match_id, b.innings, b.legal_before]))
ro_key = ro_key[~ro_key.index.duplicated()]
b["partner_runout"] = f & ((ro_cum.values - ro_key.reindex(lag.set_levels(lag.levels[2], level=2)).values) > 0)
lag6 = pd.MultiIndex.from_arrays([b.match_id, b.innings, (b.legal_before - 6).clip(lower=0)])
b["partner_runout"] = f & ((ro_cum.values - ro_key.reindex(lag6).values) > 0)

# ======================= BOWLER FACTORS =======================
bw = b.legal | b.is_wide | b.is_nb
gb = b[bw].groupby(["match_id", "innings", "bowler_id"])
prev_bnd = (b.loc[bw, "is_four"] | b.loc[bw, "is_six"]).groupby([b.loc[bw, "match_id"], b.loc[bw, "innings"], b.loc[bw, "bowler_id"]]).shift().fillna(False).astype(bool)
prev_over = b.loc[bw, "overid"].groupby([b.loc[bw, "match_id"], b.loc[bw, "innings"], b.loc[bw, "bowler_id"]]).shift()
b.loc[bw, "just_hit"] = prev_bnd & (prev_over == b.loc[bw, "overid"])
b["just_hit"] = b.just_hit.fillna(False).astype(bool)
ov = b.groupby(["match_id", "innings", "overid"]).agg(bowler=("bowler_id", "first"), runs=("total_runs", "sum"), bruns=("bowler_runs", "sum")).reset_index()
ov["prev_own"] = ov.groupby(["match_id", "innings", "bowler"]).bruns.shift()
ov["prev_team_runs"] = ov.groupby(["match_id", "innings"]).runs.shift()
ov["prev_team_bowler"] = ov.groupby(["match_id", "innings"]).bowler.shift()
ov["expensive_spell"] = ov.prev_own >= 12
ov["teammate_bad_over"] = (ov.prev_team_runs >= 14) & (ov.prev_team_bowler != ov.bowler)
b = b.merge(ov[["match_id", "innings", "overid", "expensive_spell", "teammate_bad_over"]], on=["match_id", "innings", "overid"], how="left")
for c in ("expensive_spell", "teammate_bad_over"): b[c] = b[c].fillna(False).astype(bool) & bw
# bowler poor form: economy over his previous 3 matches above 10
bm = (b[bw].groupby(["bowler_id", "match_id"]).agg(d=("match_date", "first"), runs=("bowler_runs", "sum"), balls=("legal", "sum"))
      .reset_index().sort_values(["bowler_id", "d", "match_id"]))
bm["prev3_econ"] = bm.groupby("bowler_id").apply(lambda s: 6 * s.runs.shift().rolling(3, min_periods=3).sum() / s.balls.shift().rolling(3, min_periods=3).sum(), include_groups=False).reset_index(level=0, drop=True)
b = b.merge(bm[["bowler_id", "match_id", "prev3_econ"]], on=["bowler_id", "match_id"], how="left")
b["poor_form_bowl"] = bw & (b.prev3_econ > 10)

# captaincy
cap = set(map(tuple, pe[pe.is_captain.astype(str).str.lower().isin(["true", "1"])][["match_id", "player_id"]].values))
b["captain_bat"] = f & pd.Series([(a, s) in cap for a, s in zip(b.match_id, b.striker_id)])
b["captain_bowl"] = bw & pd.Series([(a, s) in cap for a, s in zip(b.match_id, b.bowler_id)])
b["away_bat"] = f & (b.bat_venue == "away"); b["away_bowl"] = bw & (b.bowl_venue == "away")
b["big_bat"] = f & b.big_occasion; b["big_bowl"] = bw & b.big_occasion

FACT = {"bat": [("Stadium", "away_bat", "Away ground (opponent's home)"), ("Stadium", "big_bat", "Big occasion (playoffs/finals)"),
                ("Self", "stuck", "Stuck at the crease"), ("Self", "milestone", "On 40-49 (approaching fifty)"),
                ("Self", "poor_form_bat", "Poor recent form (last 3 inns avg < 12)"), ("Self", "captain_bat", "Batting as captain"),
                ("Others", "new_at_crease", "New at crease after a wicket (first 5 balls)"), ("Others", "collapse", "Collapse (2+ wkts in last 12 balls)"),
                ("Others", "dot_pressure", "Team dot streak (4+ dots)"), ("Others", "partner_runout", "Run-out in last 6 balls")],
        "bowl": [("Stadium", "away_bowl", "Away ground (opponent's home)"), ("Stadium", "big_bowl", "Big occasion (playoffs/finals)"),
                 ("Self", "just_hit", "Ball after conceding a 4/6"), ("Self", "expensive_spell", "Over after own expensive over (12+)"),
                 ("Self", "poor_form_bowl", "Poor recent form (econ > 10, last 3)"), ("Self", "captain_bowl", "Bowling as captain"),
                 ("Others", "teammate_bad_over", "Over after a teammate's 14+ over")]}

# residual value vs average player in same context (same as the main model, before player adjustments)
CTX = r.CTX
b["res_bat"] = np.where(b.faced, b.rv_bat - b[b.faced].groupby(CTX).rv_bat.transform("mean").reindex(b.index), np.nan)
b["res_bowl"] = np.where(bw, b.rv_bowl - b[bw].groupby(CTX).rv_bowl.transform("mean").reindex(b.index), np.nan)

# ---------- Stage 1: league-wide effect, match-clustered bootstrap SE ----------
def cluster_diff(d, flag, val, B=300):
    s = d.groupby(["match_id", flag])[val].agg(["sum", "count"]).unstack(fill_value=0)
    S1, N1, S0, N0 = s["sum"][True].values, s["count"][True].values, s["sum"][False].values, s["count"][False].values
    est = 100 * (S1.sum() / N1.sum() - S0.sum() / N0.sum())
    k = len(S1); boots = []
    for _ in range(B):
        i = rng.integers(0, k, k)
        boots.append(100 * (S1[i].sum() / max(N1[i].sum(), 1) - S0[i].sum() / N0[i].sum()))
    return est, float(np.std(boots))
s1 = []
for role in ("bat", "bowl"):
    d = b[b.faced] if role == "bat" else b[bw]
    val = "res_" + role
    for grp_, fl, label in FACT[role]:
        if d[fl].sum() < 500: continue
        est, se = cluster_diff(d, fl, val)
        row = dict(role=role, group=grp_, factor=label, flag=fl, share_pct=round(100 * d[fl].mean(), 1), effect_runs_per100=round(est, 2), se=round(se, 2), t=round(est / se, 1))
        if role == "bat":
            x = d.groupby(fl).agg(sr=("bat_runs", "mean"), out=("striker_out", "mean"))
            row.update(SR_flag=round(100 * x.sr[True], 1), SR_other=round(100 * x.sr[False], 1), out_pct_flag=round(100 * x.out[True], 2), out_pct_other=round(100 * x.out[False], 2))
        else:
            x = d.groupby(fl).agg(r=("bowler_runs", "sum"), bl=("legal", "sum"), w=("bowler_wkt", "sum"))
            row.update(econ_flag=round(6 * x.r[True] / x.bl[True], 2), econ_other=round(6 * x.r[False] / x.bl[False], 2), wkt_pct_flag=round(100 * x.w[True] / x.bl[True], 2), wkt_pct_other=round(100 * x.w[False] / x.bl[False], 2))
        s1.append(row)
s1 = pd.DataFrame(s1)
s1["stage1_pass"] = s1.t.abs() >= 2.8              # ~ Bonferroni for 17 tests at 5%

# ---------- Stage 2: player repeatability of the factor effect (split-half) ----------
def player_delta(d, flag, val, pid, minn):
    g_ = d.groupby([pid, flag])[val].agg(["mean", "size"]).unstack()
    ok = (g_["size"][True] >= minn) & (g_["size"][False] >= 3 * minn)
    return (g_["mean"][True] - g_["mean"][False])[ok]
s2 = []
for row in s1.itertuples():
    role = row.role; d = b[b.faced] if role == "bat" else b[bw]; pid = "striker_id" if role == "bat" else "bowler_id"
    minn = 30
    h = [player_delta(d[(d.match_id % 2) == k], row.flag, "res_" + role, pid, minn) for k in (0, 1)]
    j = pd.concat(h, axis=1, join="inner").dropna()
    rr = j.iloc[:, 0].corr(j.iloc[:, 1]) if len(j) > 10 else np.nan
    tt = rr * np.sqrt(len(j) - 2) / np.sqrt(max(1 - rr ** 2, 1e-9)) if len(j) > 10 else np.nan
    s2.append(dict(flag=row.flag, players=len(j), split_half_r=round(rr, 3) if rr == rr else None, t2=round(tt, 1) if tt == tt else None))
s2 = pd.DataFrame(s2)
res = s1.merge(s2, on="flag")
res["stage2_pass"] = (res.split_half_r >= 0.15) & (res.t2 >= 2.0)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(res.to_string(index=False), flush=True)

# ---------- Stage 3: does a psych component improve cross-half prediction of pressure performance? ----------
def psych_component(d, role, flags):
    """shrunk player effect under each flag (vs his own other balls), averaged by flagged-ball count"""
    pid = "striker_id" if role == "bat" else "bowler_id"; val = "res_" + role
    parts, wts = [], []
    for fl in flags:
        g_ = d.groupby([pid, fl])[val].agg(["mean", "size", "var"]).unstack()
        delta = (g_["mean"][True] - g_["mean"][False])
        n = g_["size"][True]; sig2 = np.nanmean(g_["var"][True])
        big = n >= 30
        tau2 = max(np.nanvar(delta[big]) - np.nanmean(sig2 / n[big]), 1e-8)
        parts.append((delta * n / (n + sig2 / tau2)).fillna(0)); wts.append(n.fillna(0))
    P = pd.concat(parts, axis=1).fillna(0); W = pd.concat(wts, axis=1).fillna(0)
    return (P * W).sum(axis=1) / W.sum(axis=1).replace(0, np.nan)
def target(half, role):
    pid = "striker_id" if role == "bat" else "bowler_id"
    d = half[half.faced] if role == "bat" else half[half.legal | half.is_wide | half.is_nb]
    p = d[d.pressure]; return p.groupby(pid)["res_" + role].agg(["mean", "size"])
s3 = []
for role in ("bat", "bowl"):
    all_flags = [fl for _, fl, _ in FACT[role]]
    s1_pass = list(res[(res.role == role) & res.stage1_pass].flag)
    halves = {k: b[(b.match_id % 2) == k].copy() for k in (0, 1)}
    for h in halves.values(): h["w"] = h.w_recency
    base = {k: r.player_table(halves[k], role)[0] for k in (0, 1)}
    tg = {k: target(halves[k], role) for k in (0, 1)}
    for setname, flags in [("all factors", all_flags), ("stage-1 passers", s1_pass)]:
        if not flags: continue
        d = {k: (halves[k][halves[k].faced] if role == "bat" else halves[k][halves[k].legal | halves[k].is_wide | halves[k].is_nb]) for k in (0, 1)}
        psy = {k: psych_component(d[k], role, flags) for k in (0, 1)}
        for lam in (0.0, 0.1, 0.25, 0.5):
            cors = []
            for a, c in ((0, 1), (1, 0)):
                t = base[a][["press_skill", "pb"]].join(psy[a].rename("psy")).join(tg[c], how="inner").join(base[c][["pb"]].rename(columns={"pb": "pbB"}))
                t = t[(t.pb >= 50) & (t.pbB >= 50)].copy(); t["psy"] = t.psy.fillna(0)
                z = lambda s: (s - s.mean()) / s.std()
                cors.append((z(t.press_skill) + lam * z(t.psy)).corr(t["mean"]))
            s3.append(dict(role=role, factor_set=setname, weight_on_psych=lam, predicts_other_half=round(float(np.mean(cors)), 3), n=len(t)))
s3 = pd.DataFrame(s3)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(res.to_string(index=False)); print(); print(s3.to_string(index=False))
res.to_csv(f"{OUT}/psych_factors.csv", index=False); s3.to_csv(f"{OUT}/psych_model_test.csv", index=False)
b[["match_id", "innings", "innings_ball_num"] + [fl for v in FACT.values() for _, fl, _ in v]].to_pickle(f"{OUT}/psych_flags.pkl")
