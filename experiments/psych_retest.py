"""Psychological factors, retested on the v4 model (README section 9.14).
Earlier tests (section 9.4) added psychological situations as a separate 'resilience' score or as fairness
context, on the v1 model and one odd/even split. This script retests them on the v4 model with the v4
held-out design, and adds two new ways of using them that target the model's real weakness (too few
pressure balls per player):

  pool 0.5   : balls with a psychological flag and above-median leverage (not already pressure balls)
               are added to the pressure set at half weight  -> more pressure evidence per player
  pool 0.25  : the same at quarter weight
  boost 1.2  : leverage x1.2 on psychologically flagged balls before the top-25% cut (like the knockout boost)
  context    : the league-average effect of situations created by others is removed from ball values
  resilience 0.1 / 0.25 : a shrunk per-player 'handles psych situations' score added to the composite

All variants and the decision rule were fixed before running:
  adopt only if the mean gain is positive on BOTH tests, and the variant beats the current model in
  at least 14 of 20 random splits and 2 of 3 out-of-time folds.
The target is always the current one: each player's context residual on held-out pressure balls
(top-25% leverage), so every variant is judged on the same question.
Usage (after the main pipeline, from the repo root): python -I experiments/psych_retest.py out
Confirmation run for the variant that passed (fresh random splits, plus a control that pools the same share
of above-median-leverage balls WITHOUT a psychological flag, to separate psychology from sample size):
        python -I experiments/psych_retest.py out --confirm
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]; CONFIRM = "--confirm" in sys.argv; sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
# This test reproduces the decision, so it starts from the v4 model WITHOUT the pooling it led to (v5 adopted
# "pool 0.25" for bowlers): pooling is switched off here and applied only by the variants below.
r.PSY_POOL_WEIGHT = {"bat": 0.0, "bowl": 0.0}

b = pd.read_pickle(f"{OUT}/balls_scored.pkl").sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)
bw = b.legal | b.is_wide | b.is_nb
f = b.faced
G3 = ["match_id", "innings"]

# ---------------- psychological flags (same definitions as experiments/psych_factors_test.py) ----------------
# batter, self-inflicted
g = b[f].groupby(G3 + ["striker_id"])
b.loc[f, "bb"] = g.cumcount(); b.loc[f, "rb"] = g.bat_runs.cumsum() - b.loc[f, "bat_runs"]
dot = (b.loc[f, "bat_runs"] == 0).astype(int); keys = [b.loc[f, c] for c in G3 + ["striker_id"]]
grp = (dot != dot.groupby(keys).shift().fillna(-1)).cumsum()
b.loc[f, "dstreak"] = dot.groupby(grp).cumsum().groupby(keys).shift().fillna(0)
b["stuck"] = f & ((b.dstreak >= 3) | ((b.bb >= 10) & (100 * b.rb / b.bb.replace(0, np.nan) < 100)))
inns = b[f].groupby(["striker_id", "match_id"]).agg(d=("match_date", "first"), runs=("bat_runs", "sum")).reset_index().sort_values(["striker_id", "d", "match_id"])
inns["prev3"] = inns.groupby("striker_id").runs.transform(lambda s: s.shift().rolling(3, min_periods=3).mean())
b = b.merge(inns[["striker_id", "match_id", "prev3"]], on=["striker_id", "match_id"], how="left")
b["poor_form_bat"] = b.faced & (b.prev3 < 12)
f = b.faced; bw = b.legal | b.is_wide | b.is_nb
# batter, caused by others
b["new_at_crease"] = f & (b.bb < 5) & (b.batting_order >= 3)
key = b.set_index(G3 + ["legal_before"]).wkts_before; first_at = key[~key.index.duplicated()]
lag12 = pd.MultiIndex.from_arrays([b.match_id, b.innings, (b.legal_before - 12).clip(lower=0)])
b["collapse"] = f & ((b.wkts_before.values - first_at.reindex(lag12).values) >= 2)
tdot = ((b.total_runs == 0) & b.legal).astype(int)
tg = (tdot != tdot.groupby([b.match_id, b.innings]).shift().fillna(-1)).cumsum()
b["dot_pressure"] = f & (tdot.groupby(tg).cumsum().groupby([b.match_id, b.innings]).shift().fillna(0) >= 4)
ro = (b.wkt & b.dismissal_type.astype(str).str.contains("Run", case=False)).astype(int)
ro_cum = ro.groupby([b.match_id, b.innings]).cumsum() - ro
ro_key = pd.Series(ro_cum.values, index=pd.MultiIndex.from_arrays([b.match_id, b.innings, b.legal_before]))
ro_key = ro_key[~ro_key.index.duplicated()]
lag6 = pd.MultiIndex.from_arrays([b.match_id, b.innings, (b.legal_before - 6).clip(lower=0)])
b["partner_runout"] = f & ((ro_cum.values - ro_key.reindex(lag6).values) > 0)
# bowler
gk = [b.loc[bw, c] for c in G3 + ["bowler_id"]]
prev_bnd = (b.loc[bw, "is_four"] | b.loc[bw, "is_six"]).groupby(gk).shift().fillna(False).astype(bool)
prev_over = b.loc[bw, "overid"].groupby(gk).shift()
b.loc[bw, "just_hit"] = prev_bnd & (prev_over == b.loc[bw, "overid"]); b["just_hit"] = b.just_hit.fillna(False).astype(bool)
ov = b.groupby(G3 + ["overid"]).agg(bowler=("bowler_id", "first"), runs=("total_runs", "sum"), bruns=("bowler_runs", "sum")).reset_index()
ov["expensive_spell"] = ov.groupby(G3 + ["bowler"]).bruns.shift() >= 12
ov["teammate_bad_over"] = (ov.groupby(G3).runs.shift() >= 14) & (ov.groupby(G3).bowler.shift() != ov.bowler)
b = b.merge(ov[G3 + ["overid", "expensive_spell", "teammate_bad_over"]], on=G3 + ["overid"], how="left")
bw = b.legal | b.is_wide | b.is_nb
for c in ("expensive_spell", "teammate_bad_over"): b[c] = b[c].fillna(False).astype(bool) & bw
bm = b[bw].groupby(["bowler_id", "match_id"]).agg(d=("match_date", "first"), runs=("bowler_runs", "sum"), balls=("legal", "sum")).reset_index().sort_values(["bowler_id", "d", "match_id"])
rs = bm.groupby("bowler_id").runs.transform(lambda s: s.shift().rolling(3, min_periods=3).sum())
bl = bm.groupby("bowler_id").balls.transform(lambda s: s.shift().rolling(3, min_periods=3).sum())
bm["prev3_econ"] = 6 * rs / bl
b = b.merge(bm[["bowler_id", "match_id", "prev3_econ"]], on=["bowler_id", "match_id"], how="left")
b["poor_form_bowl"] = (b.legal | b.is_wide | b.is_nb) & (b.prev3_econ > 10)

FLAGS = {"bat": ["stuck", "poor_form_bat", "new_at_crease", "collapse", "dot_pressure", "partner_runout"],
         "bowl": ["just_hit", "expensive_spell", "poor_form_bowl", "teammate_bad_over"]}
OTHERS = {"bat": ["new_at_crease", "collapse", "dot_pressure", "partner_runout"], "bowl": ["teammate_bad_over"]}
for role in FLAGS: b["psy_" + role] = b[FLAGS[role]].any(axis=1)
b["li_pct"] = b.li.groupby(b.innings).rank(pct=True)
for role in FLAGS:
    boosted = b.li * np.where(b["psy_" + role], 1.2, 1.0)
    b["press_boost_" + role] = boosted.groupby(b.innings).rank(pct=True) >= 0.75
ROLE = {"bat": ("striker_id", "rv_bat", lambda d: d.faced), "bowl": ("bowler_id", "rv_bowl", lambda d: d.legal | d.is_wide | d.is_nb)}
print("flag shares:", {k: round(float(b[k][ROLE['bat' if k in FLAGS['bat'] else 'bowl'][2](b)].mean()), 3) for k in FLAGS["bat"] + FLAGS["bowl"]}, flush=True)
print("psych balls added by pooling (share of all balls):", {r_: round(float((b["psy_" + r_] & (b.li_pct >= 0.5) & ~b.pressure).mean()), 3) for r_ in FLAGS}, flush=True)

# ---------------- data variants (applied to the TRAINING half only) ----------------
def pool(h, role, wt):
    h = h.copy(); ext = h["psy_" + role] & (h.li_pct >= 0.5) & ~h.pressure
    h["pressure"] = h.pressure | ext; h["w"] = h.w * np.where(ext, wt, 1.0); return h
def pool_any(h, role, wt, frac):
    """control: a random share `frac` of non-pressure balls with above-median leverage, no psych flag needed"""
    h = h.copy(); u = np.random.default_rng(99).random(len(h))
    ext = (h.li_pct >= 0.5) & ~h.pressure & (u < frac)
    h["pressure"] = h.pressure | ext; h["w"] = h.w * np.where(ext, wt, 1.0); return h
def boost(h, role):
    h = h.copy(); h["pressure"] = h["press_boost_" + role]; return h
def context(h, role):
    """remove the league-average effect of situations created by others (fitted on this half)"""
    h = h.copy(); pid, val, mask = ROLE[role]; m = mask(h); x = h[m]
    res = x[val] - x.groupby(r.CTX)[val].transform("mean")
    cell = x[OTHERS[role]].astype(int).astype(str).agg("".join, axis=1)
    h.loc[m, val] = h.loc[m, val] - (res.groupby(cell).transform("mean") - res.mean()); return h
def resilience(h, role):
    """shrunk per-player effect in psych situations vs his own other balls, pooled over flags"""
    pid, val, mask = ROLE[role]; d = h[mask(h)]; d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    parts, wts = [], []
    for fl in FLAGS[role]:
        g_ = d.groupby([pid, fl]).res.agg(["mean", "size", "var"]).unstack()
        if True not in g_["mean"].columns: continue
        delta = g_["mean"][True] - g_["mean"][False]; n = g_["size"][True]; sig2 = np.nanmean(g_["var"][True]); big = n >= 30
        tau2 = max(np.nanvar(delta[big]) - np.nanmean(sig2 / n[big]), 1e-8)
        parts.append((delta * n / (n + sig2 / tau2)).fillna(0)); wts.append(n.fillna(0))
    P = pd.concat(parts, axis=1).fillna(0); W = pd.concat(wts, axis=1).fillna(0)
    return (P * W).sum(axis=1) / W.sum(axis=1).replace(0, np.nan)

DATA_VARS = {"current": None, "pool 0.5": lambda h, ro: pool(h, ro, 0.5), "pool 0.25": lambda h, ro: pool(h, ro, 0.25),
             "boost 1.2": boost, "context": context}
RES_LAMBDAS = {"resilience 0.1": 0.1, "resilience 0.25": 0.25}
if CONFIRM:
    # same number of added balls as psych pooling: psych share among above-median non-pressure balls
    mid = (b.li_pct >= 0.5) & ~b.pressure
    FR = {ro: float(b.loc[mid, "psy_" + ro].mean()) for ro in FLAGS}
    print("psych share of above-median non-pressure balls:", {k: round(v, 3) for k, v in FR.items()}, flush=True)
    DATA_VARS = {"current": None, "pool 0.25": lambda h, ro: pool(h, ro, 0.25), "pool 0.5": lambda h, ro: pool(h, ro, 0.5),
                 "control: pool any 0.25": lambda h, ro: pool_any(h, ro, 0.25, FR[ro]),
                 "control: pool any 0.5": lambda h, ro: pool_any(h, ro, 0.5, FR[ro])}
    RES_LAMBDAS = {}

def z(s): return ((s - s.mean()) / s.std()).fillna(0.0)
def comp(j, role): return sum(w * z(j[c]) for c, w in r.WEIGHTS[role].items())
def role_table(h, role):
    t = r.player_table(h, role)[0]
    if role == "bowl": t = t.join(r.execution_component(h, wcol="w")[["execution"]])
    return t
def tables(h):
    h = h.assign(w=r.rating_weights(h, r.READY_OLD_WEIGHT), recent=h.age_days <= r.RECENT_DAYS); T = {}
    for role in ("bat", "bowl"):
        for v, fn in DATA_VARS.items():
            T[(role, v)] = role_table(h if fn is None else fn(h, role), role)
        if RES_LAMBDAS: T[(role, "psy")] = resilience(h, role)
    return T
def target(d, role):
    pid, val, mask = ROLE[role]; d = d[mask(d)]
    d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    return d[d.pressure].groupby(pid).res.agg(["mean", "size"])
def evaluate(T, tg, keep, role, tag, fold, rows):
    for v in DATA_VARS:
        j = T[(role, v)].reindex(keep).join(tg)
        rows.append(dict(test=tag, fold=fold, role=role, variant=v, r=comp(j, role).corr(j["mean"])))
    if not RES_LAMBDAS: return
    j = T[(role, "current")].reindex(keep).join(tg).join(T[(role, "psy")].rename("psy"))
    for v, lam in RES_LAMBDAS.items():
        rows.append(dict(test=tag, fold=fold, role=role, variant=v, r=(z(comp(j, role)) + lam * z(j.psy)).corr(j["mean"])))

rows = []
rng = np.random.default_rng(11 if CONFIRM else 7); mids = b.match_id.unique()
for s in range(10):
    A = set(rng.choice(mids, len(mids) // 2, replace=False))
    H = [b[b.match_id.isin(A)].copy(), b[~b.match_id.isin(A)].copy()]
    T = [tables(h) for h in H]
    for role in ("bat", "bowl"):
        TG = [target(h, role) for h in H]
        for a, c in [(0, 1), (1, 0)]:
            base, basec = T[a][(role, "current")], T[c][(role, "current")]
            keep = base.index[base.pb >= 50].intersection(basec.index[basec.pb >= 50]).intersection(TG[c].index)
            evaluate(T[a], TG[c], keep, role, "cross-half", f"{s}{a}", rows)
    print("split", s, flush=True)
for cut in ["2024-01-01", "2025-01-01", "2026-01-01"]:
    cut = pd.Timestamp(cut)
    tr = b[b.match_date < cut].copy(); te = b[(b.match_date >= cut) & (b.match_date < cut + pd.Timedelta(days=366))]
    tr["age_days"] = (cut - tr.match_date).dt.days
    T = tables(tr)
    for role in ("bat", "bowl"):
        tg = target(te, role); tg = tg[tg["size"] >= 40]
        base = T[(role, "current")]; keep = base.index[base.pb >= 60].intersection(tg.index)
        evaluate(T, tg, keep, role, "out-of-time", str(cut.date()), rows)
    print("cut", cut.date(), flush=True)

TAG = "_confirm" if CONFIRM else ""
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/psych_retest{TAG}.csv", index=False)
summary = []
for role in ("bat", "bowl"):
    p = R[R.role == role].pivot_table(index=["test", "fold"], columns="variant", values="r")
    print(f"\n== {role}: mean r"); print(R[R.role == role].pivot_table(index="variant", columns="test", values="r", aggfunc="mean").round(3).to_string())
    d = p.drop(columns="current").sub(p["current"], axis=0)
    for v in d.columns:
        ch, ot = d.loc["cross-half", v], d.loc["out-of-time", v]
        ok = ch.mean() > 0 and ot.mean() > 0 and (ch > 0).sum() >= 14 and (ot > 0).sum() >= 2
        summary.append(dict(role=role, variant=v, cross_half=f"{ch.mean():+.3f} ({(ch > 0).sum()}/20)",
                            out_of_time=f"{ot.mean():+.3f} ({(ot > 0).sum()}/3)", passes=ok))
S = pd.DataFrame(summary); print("\n== gain over the current model, and the pre-set rule"); print(S.to_string(index=False))
