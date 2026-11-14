"""Shot composure (batters) and execution errors (bowlers) under pressure.

Batters - does a player play shots under pressure he would almost never play otherwise?
  * His repertoire = shot mix on non-pressure balls (smoothed toward the league mix).
  * Everyone shifts toward big shots at the death, so his EXPECTED pressure mix is simulated:
    his own normal mix re-weighted by the league-wide pressure shift for the same phase.
  * Unusual-shot excess = share of his pressure balls with shots rare in his own repertoire (<3%)
    minus the share expected from the simulated mix.
  * Shot-mix deviation z = divergence (JSD) between his actual and simulated pressure mix,
    compared with a Monte Carlo null (200 simulated pressure innings of the same size drawn
    from the simulated mix) -> z-score that is fair across sample sizes.
Bowlers - the same for execution errors (wide, no-ball, full toss, beamer) and delivery mix.

Stages: 1 league-wide effect, 2 player repeatability (split-half), 3 held-out prediction.
Usage (after the main pipeline, from the repo root): python -I experiments/composure_test.py out
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]
RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py")
sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
rng = np.random.default_rng(5)

b = pd.read_pickle(f"{OUT}/balls_scored.pkl"); b["recent"] = b.age_days <= 365; b["w"] = b.w_recency
MERGE = {"Defense": "Frontfoot defensive", "Glance": "Leg Glance", "Intentional Padding": "No shot"}
b["shot"] = b.stroke.fillna("No shot").replace(MERGE)
b["dlv"] = b.delivery_style.fillna("Unknown")
b["error"] = b.is_wide | b.is_nb | b.dlv.isin(["Full Toss", "Beamer"])
BAT = b[b.faced].copy(); BOWL = b[b.legal | b.is_wide | b.is_nb].copy()
for d, val in ((BAT, "rv_bat"), (BOWL, "rv_bowl")):
    d["res"] = d[val] - d.groupby(r.CTX)[val].transform("mean")

def jsd(p, q):
    p = np.asarray(p, float); q = np.asarray(q, float); m = (p + q) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(p > 0, p * np.log(p / m), 0).sum(); c = np.where(q > 0, q * np.log(q / m), 0).sum()
    return (a + c) / 2

def composure_features(d, pid, cat, minP=30, minN=100, alpha=20, nsim=200):
    """Per player: unusual-category excess and simulated-null z of mix deviation under pressure."""
    cats = sorted(d[cat].unique()); ci = {c: i for i, c in enumerate(cats)}; K = len(cats)
    d = d.assign(_c=d[cat].map(ci))
    league_N = np.bincount(d.loc[~d.pressure, "_c"], minlength=K) + 1.0; league_N /= league_N.sum()
    # league pressure shift by phase
    L = {}
    for ph, g in d.groupby("ph"):
        pP = np.bincount(g.loc[g.pressure, "_c"], minlength=K) + 1.0; pN = np.bincount(g.loc[~g.pressure, "_c"], minlength=K) + 1.0
        L[ph] = (pP / pP.sum()) / (pN / pN.sum())
    rows = {}
    for p, g in d.groupby(pid):
        N, P = g[~g.pressure], g[g.pressure]
        if len(P) < minP or len(N) < minN: continue
        cN = np.bincount(N._c, minlength=K); pN = (cN + alpha * league_N) / (cN.sum() + alpha)
        rare = (cN / cN.sum()) < 0.03
        # simulated expected pressure mix: own normal mix x league shift for each pressure ball's phase
        ph_counts = P.ph.value_counts()
        q = sum(n * (pN * L[ph] / (pN * L[ph]).sum()) for ph, n in ph_counts.items()) / len(P)
        cP = np.bincount(P._c, minlength=K); obs = cP / cP.sum()
        excess_unusual = obs[rare].sum() - q[rare].sum()
        sims = rng.multinomial(len(P), q, size=nsim) / len(P)
        null = np.array([jsd(s, q) for s in sims]); dev = jsd(obs, q)
        rows[p] = dict(excess_unusual=excess_unusual, dev_z=(dev - null.mean()) / (null.std() + 1e-12), nP=len(P),
                       obs_unusual=obs[rare].sum(), exp_unusual=q[rare].sum())
    return pd.DataFrame.from_dict(rows, orient="index")

def error_features(d, pid, minP=30, minN=100, nsim=2000):
    """Bowlers: excess execution-error rate under pressure vs his own rate x league pressure shift."""
    lr = {ph: g.loc[g.pressure, "error"].mean() / g.loc[~g.pressure, "error"].mean() for ph, g in d.groupby("ph")}
    lgN = d.loc[~d.pressure, "error"].mean(); rows = {}
    for p, g in d.groupby(pid):
        N, P = g[~g.pressure], g[g.pressure]
        if len(P) < minP or len(N) < minN: continue
        eN = (N.error.sum() + 20 * lgN) / (len(N) + 20)
        e_exp = np.clip((P.ph.map(lambda ph: eN * lr[ph])).mean(), 1e-4, 0.99)
        sims = rng.binomial(len(P), e_exp, size=nsim) / len(P)
        e_obs = P.error.mean()
        rows[p] = dict(excess_error=e_obs - e_exp, error_z=(e_obs - sims.mean()) / (sims.std() + 1e-12), obs_err=e_obs, exp_err=e_exp, nP=len(P))
    return pd.DataFrame.from_dict(rows, orient="index")


def target(half, role):
    pid, val = ("striker_id", "rv_bat") if role == "bat" else ("bowler_id", "rv_bowl")
    d = half[half.faced] if role == "bat" else half[half.legal | half.is_wide | half.is_nb]
    d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    return d[d.pressure].groupby(pid).res.mean()
z = lambda s: (s - s.mean()) / s.std()
FEATS = {"bat": ["excess_unusual", "dev_z"], "bowl": ["excess_error", "error_z", "dev_z"]}
mids = b.match_id.unique(); out = []
for seed in range(10):
    g = np.random.default_rng(100 + seed); half_of = pd.Series(g.integers(0, 2, len(mids)), index=mids)
    for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
        D = BAT if role == "bat" else BOWL; feats = {}
        for h in (0, 1):
            Dh = D[D.match_id.map(half_of) == h]
            F = composure_features(Dh, pid, "shot" if role == "bat" else "dlv", nsim=100)
            if role == "bowl": F = F.join(error_features(Dh, pid, nsim=500)[["excess_error", "error_z"]], how="outer")
            feats[h] = F
        res = {lam: [] for lam in (0, 0.1, 0.25, 0.5)}
        for a, c in ((0, 1), (1, 0)):
            HA, HC = b[b.match_id.map(half_of) == a], b[b.match_id.map(half_of) == c]
            TA, TC = r.player_table(HA, role)[0], r.player_table(HC, role)[0]
            f = TA[["press_skill", "pb"]].join(feats[a][FEATS[role]], how="left").join(target(HC, role).rename("y"), how="inner").join(TC[["pb"]].rename(columns={"pb": "pbB"}))
            f = f[(f.pb >= 50) & (f.pbB >= 50)].copy()
            for f_ in FEATS[role]: f[f_] = f[f_].fillna(f[f_].median())
            comp = -sum(z(f[f_]) for f_ in FEATS[role]) / len(FEATS[role])
            for lam in res: res[lam].append((z(f.press_skill) + lam * z(comp)).corr(f.y))
        out.append(dict(seed=seed, role=role, **{f"lam_{k}": round(float(np.mean(v)), 3) for k, v in res.items()}))
o = pd.DataFrame(out)
for lam in ("lam_0.1", "lam_0.25", "lam_0.5"): o["gain_" + lam[4:]] = (o[lam] - o.lam_0).round(3)
pd.set_option("display.width", 200); print(o.to_string(index=False))
print(o.groupby("role")[[c for c in o if c.startswith("gain")]].agg(["mean", lambda s: (s > 0).sum()]).round(3))
