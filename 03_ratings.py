"""Step 3: player ratings under pressure -- two separate ratings.
Usage: python -I 03_ratings.py <out_dir> [n_boot]

  Career Pressure Ability  : every match in the data counts equally (no recency weighting).
  Current Pressure Readiness: matches in the last 12 months count fully; older matches count at
                              READY_OLD_WEIGHT each, so they act only as a starting point (prior) that the
                              last 12 months update. Every ball is used once in each rating, and recent
                              form enters only through this weighting (no separate form component).
The two ratings are never combined into one score.
Produces rating tables, bootstrap top-10 frequencies and split-half reliability for both ratings.
"""
import sys, json, numpy as np, pandas as pd

OUT = sys.argv[1]; NBOOT = int(sys.argv[2]) if len(sys.argv) > 2 else 300
b = pd.read_pickle(f"{OUT}/balls_scored.pkl")
END = b.match_date.max()
b["recent"] = b.age_days <= 365
MIN_PB, MIN_PM = 120, 10          # eligibility: pressure balls, matches with pressure involvement

CTX = ["env", "innings", "ph", "wb", "pressure"]
RECENT_DAYS = 365
# Readiness: weight of one ball older than 12 months, relative to a recent ball. Chosen by the
# out-of-time and cross-half tests in experiments/readiness_test.py (README section 9.2).
READY_OLD_WEIGHT = 0.5
RATINGS = {"readiness": READY_OLD_WEIGHT, "career": 1.0}

def rating_weights(b, old_weight, recent_days=RECENT_DAYS):
    """Per-ball weight: 1 for balls in the last `recent_days`, `old_weight` for older balls."""
    return np.where(b.age_days <= recent_days, 1.0, old_weight)
# matchup adjustment applies to batters only: what a batter faces is set by the opposition,
# whereas a bowler's type is part of his own skill (adjusting for it would compare elite
# death-over spinners only with other elite spinners).
USE_MATCHUP = {"bat": True, "bowl": False}
# Psychological pressure pooling (bowlers only; README sections 6.5 and 9.14). A bowler delivery that is
# not a pressure ball but has above-median leverage AND a psychological pressure situation (psy_bowl, set in
# 02_pressure.py: just hit for 4/6, after his own 12+ over, poor recent form, after a teammate's 14+ over)
# is added to his pressure balls at PSY_POOL_WEIGHT of a full ball. Eligibility, ball counts and the
# descriptive pressure stats still use real pressure balls only. Batters: no pooling (no held-out gain).
PSY_POOL_WEIGHT = {"bat": 0.0, "bowl": 0.25}
def psych_pool(d, role, wcol):
    """Return d with pressure_real (the leverage flag) kept, and pooled balls added to `pressure` at reduced weight."""
    d = d.copy(); d["pressure_real"] = d.pressure
    wt = PSY_POOL_WEIGHT[role]
    if wt > 0 and "psy_" + role in d.columns:
        ext = d["psy_" + role] & (d.li_pct >= 0.5) & ~d.pressure
        d["pressure"] = d.pressure | ext
        if wcol is not None: d[wcol] = d[wcol] * np.where(ext, wt, 1.0)
        else: d["_poolw"] = np.where(ext, wt, 1.0)
    return d

def _wsums(df, key, val, w):
    """Weighted sums per key. A ball's weight w = f x a: f is a bootstrap frequency (Poisson(1) per match) and
    a is the rating weight (1 recent, READY_OLD_WEIGHT older). The effective number of balls of the weighted
    mean is Kish's (sum w)^2 / sum w^2, over the combined weight. In a bootstrap resample this counts a
    duplicated match as only partly new evidence, which matches the extra noise that resampling adds to every
    player's mean; counting copies as fully independent inflated tau and deflated beta in the resamples
    (README section 9.13). On the full data (f = 1) it is the plain ball count when a = 1."""
    return df.assign(_wv=df[val] * df[w], _w=df[w], _w2f=df[w] ** 2).groupby(key)[["_wv", "_w", "_w2f"]].sum()

def shrink_mean(df, key, val, w, k=None):
    """Empirical-Bayes shrunk weighted mean per key (toward 0). Returns series, k, n_eff."""
    g = _wsums(df, key, val, w)
    mean = g._wv / g._w
    neff = g._w ** 2 / g._w2f                          # effective number of balls (see _wsums)
    if k is None:
        sig2 = np.average((df[val] - df[key].map(mean)) ** 2, weights=df[w])
        big = neff >= 50
        tau2 = max(np.average(mean[big] ** 2, weights=neff[big]) - sig2 * np.average(1 / neff[big], weights=neff[big]), 1e-8)
        k = sig2 / tau2                                # prior strength in balls
    return mean * neff / (neff + k), k, neff

def hier(P, N, pid, val, w, beta=None, tau2=None):
    """Hierarchical estimate of each player's true per-ball value under pressure.
    Prior: mu_i ~ N(beta * baseline_i, tau2_c) where baseline_i = shrunk non-pressure value.
    Returns posterior mean, clutch part, baseline, beta, tau2, n_eff."""
    B, _, _ = shrink_mean(N, pid, val, w)
    g = _wsums(P, pid, val, w)
    Pm = g._wv / g._w; nP = g._w ** 2 / g._w2f
    sig2 = np.average((P[val] - P[pid].map(Pm)) ** 2, weights=P[w])
    Bp = B.reindex(Pm.index).fillna(0.0)
    big = nP >= 50
    if beta is None:
        beta = float(np.sum(nP[big] * Pm[big] * Bp[big]) / np.sum(nP[big] * Bp[big] ** 2))
    if tau2 is None:
        resid = Pm - beta * Bp
        tau2 = max(float(np.average(resid[big] ** 2, weights=nP[big]) - sig2 * np.average(1 / nP[big], weights=nP[big])), 1e-6)
    s = nP / (nP + sig2 / tau2)
    clutch = s * (Pm - beta * Bp)
    return beta * Bp + clutch, clutch, Bp, beta, tau2, nP

def player_table(b, role, wcol="w", role_hl=None):
    """role 'bat' or 'bowl'. b must contain weight column wcol (rating weight x bootstrap weight).
    role_hl is accepted for backward compatibility with older experiment scripts and ignored."""
    b = b[b[wcol] > 0]
    if role == "bat":
        d = b[b.faced].copy(); pid, val, wpa = "striker_id", "rv_bat", "wpa_bat"; opp = "bowler_id"
    else:
        d = b[b.legal | b.is_wide | b.is_nb].copy(); pid, val, wpa = "bowler_id", "rv_bowl", "wpa_bowl"; opp = "striker_id"
    d = psych_pool(d, role, wcol)
    # 1) context residual: value relative to the average player in the same situation
    # matchup: pace/spin x bowling arm x batter hand (8 types), adjusted additively within phase
    arm = np.where(d.bowling_type.str.lower().str.startswith("left") | d.bowling_type.str.contains("left-arm", case=False), "L", "R")
    d["matchup"] = d.pace_or_spin.astype(str) + "-" + arm + "-" + d.batting_type.astype(str)
    for v in (val, wpa):
        d[v + "_r"] = d[v] - d.groupby(CTX)[v].transform("mean")
        if USE_MATCHUP[role]:
            d[v + "_r"] = d[v + "_r"] - d.groupby(["matchup", "ph"])[v + "_r"].transform("mean")
    # 2) opposition adjustment: alternating shrunk effects (player vs opponent), all balls
    eff_p = pd.Series(0.0, index=d[pid].unique()); eff_o = pd.Series(0.0, index=d[opp].unique())
    for _ in range(3):
        d["_t"] = d[val + "_r"] - d[pid].map(eff_p)
        eff_o, _, _ = shrink_mean(d, opp, "_t", wcol)
        d["_t"] = d[val + "_r"] - d[opp].map(eff_o)
        eff_p, _, _ = shrink_mean(d, pid, "_t", wcol)
    d["adj"] = d[val + "_r"] - d[opp].map(eff_o)
    d["wpa_adj"] = d[wpa + "_r"]
    P, N = d[d.pressure], d[~d.pressure]
    A, clutch, base, beta, tau2, nA = hier(P, N, pid, "adj", wcol)  # pressure rating (hierarchical)
    kA = dict(beta=round(beta, 3), clutch_sd_per100=round(100 * np.sqrt(tau2), 2))
    # a player with no (weighted) pressure balls falls back to the prior: beta x his normal level
    Bn, _, _ = shrink_mean(N, pid, "adj", wcol)
    allp = A.index.union(Bn.index)
    A = A.reindex(allp).fillna(beta * Bn.reindex(allp).fillna(0.0)); clutch = clutch.reindex(allp).fillna(0.0)
    base = base.reindex(allp).fillna(Bn.reindex(allp)).fillna(0.0)
    Wi, _, _ = shrink_mean(P, pid, "wpa_adj", wcol)                  # win impact under pressure
    Wi = Wi.reindex(allp).fillna(0.0)
    # consistency: share of matches whose pressure-ball value is positive (>=3 pressure balls)
    pm = P.groupby([pid, "match_id"]).agg(v=("adj", "sum"), n=("adj", "size"), w=(wcol, "first"))
    pm = pm[pm.n >= 3]
    prior = (pm.v > 0).mean()
    cons = pm.assign(pos=(pm.v > 0) * pm.w).groupby(level=0).agg(pos=("pos", "sum"), w=("w", "sum"))
    C = (cons.pos + 6 * prior) / (cons.w + 6)
    C = C.reindex(allp).fillna(prior)
    t = pd.DataFrame({"press_skill": A * 100, "baseline": base * 100, "win_impact": Wi * 1000,
                      "consistency": C, "clutch_delta": clutch * 100})
    t["raw_press"] = d[d.pressure_real].groupby(pid).adj.mean() * 100
    # raw descriptive stats
    agg = dict(pb=("adj", "size"), pm=("match_id", "nunique"))
    Pr = d[d.pressure_real]                                          # real pressure balls only
    raw = Pr.groupby(pid).agg(**agg)
    t = t.join(raw, how="left")
    t["recent_pb"] = Pr[Pr.recent].groupby(pid).size().reindex(t.index).fillna(0).astype(int)
    t["active"] = t.index.isin(d.loc[d.recent, pid])
    t["n_matches_all"] = d.groupby(pid).match_id.nunique()
    return t, kA, d

# Component weights, the same in both ratings (README sections 6.3 and 9.13).
# - No separate 12-month form component: recency enters only through the Readiness ball weights.
# - No separate clutch-delta component: clutch delta is already inside the pressure rating
#   (beta x usual level + shrunk clutch delta), so adding it again counted it twice.
# - Batters: the pressure rating alone. Consistency and win impact did not improve held-out prediction
#   for batters (experiments/review_test.py), so by the section 9 rule they are reported, not scored.
# - Bowlers: consistency, win impact and the rebuilt execution component each improve held-out
#   prediction, so they stay, with the earlier relative weights.
_W0 = {"bat":  {"press_skill": 1.0},
       "bowl": {"press_skill": 0.36, "consistency": 0.09, "win_impact": 0.135, "execution": 0.10}}
WEIGHTS = {r: {k: v / sum(w.values()) for k, v in w.items()} for r, w in _W0.items()}

# ---------------------------------------------------------------------------------------------
# Execution under pressure (bowlers). An execution error is a wide, a no-ball, a full toss or a beamer.
# A bowler's EXPECTED error count on his pressure balls is built phase by phase from his own normal
# (non-pressure) error rate IN THE SAME PHASE, shrunk toward the league's normal rate for that phase,
# times the league-wide pressure/normal ratio within that phase. The death overs carry far more
# errors for everyone (about 16.6% of normal balls, against about 6% earlier), so comparing a death
# bowler with his own all-phase rate would penalise workload, not execution. The score is the shrunk
# excess error rate (observed minus expected, divided by pressure balls + ALPHA_EXEC), so a small
# sample is pulled toward zero instead of growing with sample size as a z-score would.
# (The previous version also scored delivery-mix deviation; that term was direction-blind and
# mostly measured workload, so it is dropped: README section 9.13.)
# ---------------------------------------------------------------------------------------------
ALPHA_EXEC = 20          # pseudo-balls, the same smoothing strength the previous version used
def execution_component(b, minP=30, minN=100, alpha=ALPHA_EXEC, wcol=None):
    """wcol: optional per-ball rating weight (e.g. Readiness weights); None = every ball counts 1."""
    d = psych_pool(b[b.legal | b.is_wide | b.is_nb], "bowl", wcol)    # same pooled pressure set as the rating
    d["_w"] = (1.0 if wcol is None else d[wcol].astype(float)) * (d["_poolw"] if "_poolw" in d.columns else 1.0)
    d = d[d._w > 0]
    d["error"] = (d.is_wide | d.is_nb | d.delivery_style.fillna("").isin(["Full Toss", "Beamer"])).astype(float)
    d["_we"] = d._w * d.error
    lg = d.groupby(["ph", "pressure"])[["_we", "_w"]].sum()
    rate = (lg._we / lg._w).unstack()                       # league error rate by phase x pressure
    errN_ph = rate[False]; LR = rate[True] / rate[False]    # normal rate per phase; within-phase pressure shift
    by = d.groupby(["bowler_id", "pressure", "ph"])[["_we", "_w"]].sum()
    cnt = d.groupby(["bowler_id", "pressure"]).size().unstack(fill_value=0)
    rows = {}
    for p in cnt.index[(cnt.get(True, 0) >= minP) & (cnt.get(False, 0) >= minN)]:
        g = by.loc[p]
        P = g.loc[True] if True in g.index.get_level_values(0) else None
        N = g.loc[False]
        exp_cnt, obs_cnt, nP = 0.0, float(P._we.sum()), float(P._w.sum())
        for ph, row in P.iterrows():
            nN, eN = (N.loc[ph, "_w"], N.loc[ph, "_we"]) if ph in N.index else (0.0, 0.0)
            e_ph = (eN + alpha * errN_ph[ph]) / (nN + alpha)          # his normal rate in this phase, shrunk
            exp_cnt += row._w * e_ph * LR[ph]
        rows[p] = dict(err_P=obs_cnt / nP, err_expected=exp_cnt / nP, excess_error=(obs_cnt - exp_cnt) / nP,
                       excess_shrunk=(obs_cnt - exp_cnt) / (nP + alpha))
    F = pd.DataFrame.from_dict(rows, orient="index")
    F["execution"] = -(F.excess_shrunk - F.excess_shrunk.mean()) / F.excess_shrunk.std()   # higher = better
    return F
def composite(t, weights, elig=None):
    if elig is None:
        e = t[(t.pb >= MIN_PB) & (t.pm >= MIN_PM) & t.active].copy()
    else:                                   # bootstrap: eligibility fixed from the full sample
        e = t.loc[t.index.intersection(elig)].copy()
    z = {c: (e[c] - e[c].mean()) / e[c].std() for c in weights}
    e["score"] = sum(w * (z[c].fillna(0.0) if c == "execution" else z[c]) for c, w in weights.items())
    for c in weights: e["z_" + c] = z[c].fillna(0.0) if c == "execution" else z[c]
    return e.sort_values("score", ascending=False)

def descr(d, role, pid):
    """Readable stats under pressure vs otherwise."""
    rows = []
    for p, g in d.groupby("pressure"):
        if role == "bat":
            s = g.groupby(pid).agg(balls=("legal", "size"), runs=("bat_runs", "sum"), outs=("striker_out", "sum"),
                                   dots=("bat_runs", lambda x: (x == 0).sum()), bnd=("is_four", "sum"), six=("is_six", "sum"))
            s["SR"] = 100 * s.runs / s.balls; s["avg"] = s.runs / s.outs.replace(0, np.nan)
            s["dot%"] = 100 * s.dots / s.balls; s["bdry%"] = 100 * (s.bnd + s.six) / s.balls
            s = s[["balls", "runs", "outs", "SR", "avg", "dot%", "bdry%"]]
        else:
            s = g.groupby(pid).agg(balls=("legal", "sum"), runs=("bowler_runs", "sum"), wkts=("bowler_wkt", "sum"),
                                   dots=("total_runs", lambda x: (x == 0).sum()))
            s["econ"] = 6 * s.runs / s.balls; s["SR"] = s.balls / s.wkts.replace(0, np.nan)
            s["dot%"] = 100 * s.dots / s.balls
            s = s[["balls", "runs", "wkts", "econ", "SR", "dot%"]]
        s.columns = [f"{c}_{'P' if p else 'N'}" for c in s.columns]
        rows.append(s)
    return pd.concat(rows, axis=1)

# output file stem per rating: Readiness is the submitted rating, so it keeps the original names
STEM = {"readiness": "", "career": "_career"}

if __name__ == "__main__":
    names_bat = b.groupby("striker_id").striker_name.last(); names_bowl = b.groupby("bowler_id").bowler_name.last()
    res = {}; ELIG = {}; EXEC = {}
    for rating, a0 in RATINGS.items():
        b["w"] = rating_weights(b, a0)
        # execution computed once per rating on the full data (held fixed in the bootstrap)
        EXEC[rating] = execution_component(b, wcol="w")
        EXEC[rating].to_csv(f"{OUT}/bowl_execution{STEM[rating]}.csv")
        res[rating] = {}
        for role, pid, names in [("bat", "striker_id", names_bat), ("bowl", "bowler_id", names_bowl)]:
            t, k, d = player_table(b, role)
            if role == "bowl": t = t.join(EXEC[rating][["execution"]])
            # eligibility (pressure balls, matches, active) uses unweighted counts, so both ratings rank the same pool
            e = composite(t, WEIGHTS[role], ELIG.get(role))
            ELIG[role] = list(e.index)
            e.insert(0, "name", e.index.map(names))
            e = e.join(descr(d, role, pid), how="left")
            for lg in ["IPL", "T20I"]:   # league split, unshrunk descriptive
                x = d[d.pressure & (d.league == lg)].groupby(pid).agg(v=("adj", "mean"), n=("adj", "size"))
                e[f"press_{lg}"] = x.v * 100; e[f"pb_{lg}"] = x.n
            e["rank"] = range(1, len(e) + 1)
            e.to_csv(f"{OUT}/{role}{STEM[rating]}_ratings.csv")
            res[rating][role] = dict(prior=k, eligible=len(e))
            print(rating.upper(), role.upper(), k, "eligible =", len(e))
            cols = ["name", "score", "press_skill", "baseline", "clutch_delta", "consistency", "win_impact", "pb", "recent_pb"]
            print(e[cols].head(12).round(2).to_string())

    # ---------- split-half reliability (odd/even match ids) ----------
    rel = {}
    for rating, a0 in RATINGS.items():
        b["w"] = rating_weights(b, a0); rel[rating] = {}
        for role in ["bat", "bowl"]:
            halves = [player_table(b[(b.match_id % 2) == h], role)[0] for h in (0, 1)]
            j = halves[0].join(halves[1], lsuffix="_a", rsuffix="_b", how="inner")
            j = j[(j.pb_a >= 50) & (j.pb_b >= 50)]
            rel[rating][role] = {c: round(float(j[c + "_a"].corr(j[c + "_b"])), 3) for c in
                                 ["press_skill", "baseline", "clutch_delta", "win_impact", "consistency"]}
            rel[rating][role]["n_players"] = int(len(j))
    print("split-half reliability", json.dumps(rel, indent=1))

    # ---------- bootstrap (resample matches, Poisson weights; same resamples for both ratings) ----------
    rng = np.random.default_rng(42)
    mids = b.match_id.unique()
    top10 = {(g, r_): {} for g in RATINGS for r_ in ["bat", "bowl"]}; ranks = {k: [] for k in top10}
    for it in range(NBOOT):
        pw = b.match_id.map(pd.Series(rng.poisson(1.0, len(mids)), index=mids)).values
        for rating, a0 in RATINGS.items():
            bb = b.assign(w=rating_weights(b, a0) * pw, f=pw)
            for role in ["bat", "bowl"]:
                t, _, _ = player_table(bb, role)
                if role == "bowl": t = t.join(EXEC[rating][["execution"]])
                e = composite(t, WEIGHTS[role], ELIG[role])
                ranks[(rating, role)].append(pd.Series(range(1, len(e) + 1), index=e.index))
                for p in e.index[:10]:
                    top10[(rating, role)][p] = top10[(rating, role)].get(p, 0) + 1
        if it % 50 == 0: print("boot", it, flush=True)
    for (rating, role), rl in ranks.items():
        rk = pd.concat(rl, axis=1)
        out = pd.DataFrame({"top10_freq": pd.Series(top10[(rating, role)]) / NBOOT,
                            "median_rank": rk.median(axis=1), "rank_p10": rk.quantile(0.1, axis=1),
                            "rank_p90": rk.quantile(0.9, axis=1)})
        out.to_csv(f"{OUT}/{role}{STEM[rating]}_bootstrap.csv")
    json.dump(dict(ready_old_weight=READY_OLD_WEIGHT, weights=WEIGHTS, res=res, reliability=rel),
              open(f"{OUT}/ratings_info.json", "w"), indent=1)
