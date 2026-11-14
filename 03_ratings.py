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

def _wsums(df, key, val, w):
    """Weighted sums per key. A ball's weight w = f x a: f is a bootstrap frequency (column 'f', default 1:
    a resampled copy is a real extra observation) and a is the rating weight (1 recent, READY_OLD_WEIGHT older).
    The effective number of balls of the weighted mean is (sum w)^2 / sum(f a^2) = (sum w)^2 / sum(w^2 / f):
    with a = 1 it is the plain ball count, with f = 1 it is Kish's effective sample size."""
    f = df["f"] if "f" in df else 1.0
    return df.assign(_wv=df[val] * df[w], _w=df[w], _w2f=df[w] ** 2 / f).groupby(key)[["_wv", "_w", "_w2f"]].sum()

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
    t["raw_press"] = P.groupby(pid).adj.mean() * 100
    # raw descriptive stats
    agg = dict(pb=("adj", "size"), pm=("match_id", "nunique"))
    raw = P.groupby(pid).agg(**agg)
    t = t.join(raw, how="left")
    t["recent_pb"] = P[P.recent].groupby(pid).size().reindex(t.index).fillna(0).astype(int)
    t["active"] = t.index.isin(d.loc[d.recent, pid])
    t["n_matches_all"] = d.groupby(pid).match_id.nunique()
    return t, kA, d

# Component weights, the same in both ratings. They are the earlier weights with the separate
# 12-month form component (25% batting, 18% bowling) removed and the rest rescaled to sum to 1:
# recency now enters only through the Readiness ball weights, so each ball is counted once.
# Weights are role-specific: components that failed the split-half test for a role get less weight.
# Bowlers also get an execution-under-pressure component; it passed all three tests
# (experiments/composure_test.py, experiments/composure_splits.py), the batting equivalent did not.
_W0 = {"bat":  {"press_skill": 0.45, "clutch_delta": 0.10, "consistency": 0.10, "win_impact": 0.10},
       "bowl": {"press_skill": 0.36, "clutch_delta": 0.135, "consistency": 0.09, "win_impact": 0.135, "execution": 0.10}}
WEIGHTS = {r: {k: v / sum(w.values()) for k, v in w.items()} for r, w in _W0.items()}

# ---------------------------------------------------------------------------------------------
# Execution under pressure (bowlers). An execution error is a wide, a no-ball, a full toss or a
# beamer. A bowler's EXPECTED error rate and delivery mix under pressure are simulated from his
# own non-pressure record re-weighted by the league-wide pressure shift for the same phase, so
# only deviation beyond what an average bowler shows counts. z-scores use a Monte Carlo null.
# ---------------------------------------------------------------------------------------------
EXEC_SEED = 5
def _jsd_rows(P, q):
    """Jensen-Shannon divergence of each row of P against distribution q."""
    M = (P + q) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(P > 0, P * np.log(P / M), 0).sum(1); c = np.where(q > 0, q * np.log(q / M), 0).sum(1)
    return (a + c) / 2
def execution_component(b, minP=30, minN=100, alpha=20, nsim=200, wcol=None):
    """wcol: optional per-ball rating weight (e.g. Readiness weights); None = every ball counts 1.
    Counts, rates and the size of the simulated pressure spell use the weighted ball counts."""
    rng = np.random.default_rng(EXEC_SEED)
    d = b[b.legal | b.is_wide | b.is_nb].copy()
    d["_w"] = 1.0 if wcol is None else d[wcol].astype(float)
    d = d[d._w > 0]
    d["dlv"] = d.delivery_style.fillna("Unknown")
    d["error"] = d.is_wide | d.is_nb | d.dlv.isin(["Full Toss", "Beamer"])
    cats = sorted(d.dlv.unique()); ci = {c: i for i, c in enumerate(cats)}; K = len(cats); d["_c"] = d.dlv.map(ci)
    bc = lambda g: np.bincount(g._c, weights=g._w, minlength=K)
    wmean = lambda g, c: float(np.average(g[c], weights=g._w))
    lgN = bc(d[~d.pressure]) + 1.0; lgN /= lgN.sum()
    L, LR = {}, {}
    for ph, g in d.groupby("ph"):
        pP = bc(g[g.pressure]) + 1.0; pN = bc(g[~g.pressure]) + 1.0
        L[ph] = (pP / pP.sum()) / (pN / pN.sum())
        LR[ph] = wmean(g[g.pressure], "error") / wmean(g[~g.pressure], "error")
    errN = wmean(d[~d.pressure], "error"); rows = {}
    for p, g in d.groupby("bowler_id"):
        N, P = g[~g.pressure], g[g.pressure]
        if len(P) < minP or len(N) < minN: continue
        nPw = P._w.sum(); nNw = N._w.sum(); nS = max(int(round(nPw)), 1)   # weighted spell size
        phc = P.groupby("ph")._w.sum()
        # delivery-mix deviation vs simulated expectation
        cN = bc(N); pN = (cN + alpha * lgN) / (cN.sum() + alpha)
        q = sum(n * (pN * L[ph] / (pN * L[ph]).sum()) for ph, n in phc.items()) / nPw
        obs = bc(P) / nPw
        null = _jsd_rows(rng.multinomial(nS, q, size=nsim) / nS, q)
        dev_z = (_jsd_rows(obs[None, :], q)[0] - null.mean()) / (null.std() + 1e-12)
        # execution-error rate vs simulated expectation
        eN = ((N.error * N._w).sum() + 20 * errN) / (nNw + 20)
        e_exp = float(np.clip(sum(n * eN * LR[ph] for ph, n in phc.items()) / nPw, 1e-4, 0.99))
        sims = rng.binomial(nS, e_exp, size=2000) / nS; e_obs = wmean(P, "error")
        rows[p] = dict(err_P=e_obs, err_expected=e_exp, excess_error=e_obs - e_exp,
                       error_z=(e_obs - sims.mean()) / (sims.std() + 1e-12), delivery_dev_z=dev_z)
    F = pd.DataFrame.from_dict(rows, orient="index")
    zf = lambda s: (s - s.mean()) / s.std()
    # higher = better execution under pressure
    F["execution"] = -(zf(F.excess_error) + zf(F.error_z) + zf(F.delivery_dev_z)) / 3
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
