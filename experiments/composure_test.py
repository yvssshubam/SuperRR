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

# ======================= STAGE 1: league-wide =======================
def cluster_diff(d, flag, val="res", B=300):
    s = d.groupby(["match_id", flag])[val].agg(["sum", "count"]).unstack(fill_value=0)
    S1, N1, S0, N0 = s["sum"][True].values, s["count"][True].values, s["sum"][False].values, s["count"][False].values
    est = 100 * (S1.sum() / N1.sum() - S0.sum() / N0.sum()); k = len(S1)
    bs = [100 * (S1[i].sum() / max(N1[i].sum(), 1) - S0[i].sum() / N0[i].sum()) for i in (rng.integers(0, k, k) for _ in range(B))]
    return round(est, 2), round(float(np.std(bs)), 2)
# out-of-repertoire flag on every pressure ball: shot type that batter plays on <3% of his non-pressure balls
rep = BAT[~BAT.pressure].groupby(["striker_id", "shot"]).size() / BAT[~BAT.pressure].groupby("striker_id").size()
nN = BAT[~BAT.pressure].groupby("striker_id").size()
k = pd.MultiIndex.from_arrays([BAT.striker_id, BAT.shot])
BAT["share_in_rep"] = rep.reindex(k).fillna(0).values
BAT["unusual"] = (BAT.share_in_rep < 0.03) & BAT.striker_id.map(nN).fillna(0).ge(100)
Pb = BAT[BAT.pressure & BAT.striker_id.map(nN).fillna(0).ge(100)]
s1 = {}
s1["bat: share of pressure balls with out-of-repertoire shots"] = f"{100 * Pb.unusual.mean():.1f}%"
e, se = cluster_diff(Pb, "unusual"); s1["bat: value of out-of-repertoire shot vs usual shot, pressure balls (runs/100)"] = f"{e} (se {se}, t {e / se:.1f})"
x = Pb.groupby("unusual").agg(sr=("bat_runs", "mean"), out=("striker_out", "mean"))
s1["bat: SR / dismissal %, unusual vs usual shots"] = f"SR {100 * x.sr[True]:.0f} vs {100 * x.sr[False]:.0f}; out {100 * x.out[True]:.1f}% vs {100 * x.out[False]:.1f}%"
s1["bowl: execution-error rate, pressure vs other"] = f"{100 * BOWL[BOWL.pressure].error.mean():.1f}% vs {100 * BOWL[~BOWL.pressure].error.mean():.1f}%"
e, se = cluster_diff(BOWL[BOWL.pressure], "error"); s1["bowl: value of an error ball vs other, pressure balls (runs/100)"] = f"{e} (se {se}, t {e / se:.1f})"
print("STAGE 1 - league-wide"); [print(f"  {k_}: {v}") for k_, v in s1.items()]

# ======================= STAGE 2 + 3 =======================
def target(half, role):
    pid, val = ("striker_id", "rv_bat") if role == "bat" else ("bowler_id", "rv_bowl")
    d = half[half.faced] if role == "bat" else half[half.legal | half.is_wide | half.is_nb]
    d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    return d[d.pressure].groupby(pid).res.mean()
z = lambda s: (s - s.mean()) / s.std()
FEATS = {"bat": ["excess_unusual", "dev_z"], "bowl": ["excess_error", "error_z", "dev_z"]}
s2rows, s3rows, boot = [], [], []
for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
    D = BAT if role == "bat" else BOWL
    halves = {}
    for h in (0, 1):
        Dh = D[(D.match_id % 2) == h]
        F = composure_features(Dh, pid, "shot" if role == "bat" else "dlv")
        if role == "bowl": F = F.join(error_features(Dh, pid)[["excess_error", "error_z", "obs_err", "exp_err"]], how="outer")
        halves[h] = F
    # stage 2: repeatability
    j = halves[0].join(halves[1], lsuffix="_a", rsuffix="_b", how="inner")
    for f_ in FEATS[role]:
        jj = j[[f_ + "_a", f_ + "_b"]].dropna(); rr = jj.iloc[:, 0].corr(jj.iloc[:, 1])
        s2rows.append(dict(role=role, feature=f_, players=len(jj), split_half_r=round(rr, 3), t=round(rr * np.sqrt(len(jj) - 2) / np.sqrt(1 - rr ** 2), 1)))
    # stage 3: held-out prediction
    frames = []
    for a, c in ((0, 1), (1, 0)):
        HA, HC = b[(b.match_id % 2) == a], b[(b.match_id % 2) == c]
        TA, TC = r.player_table(HA, role)[0], r.player_table(HC, role)[0]
        f = TA[["press_skill", "pb"]].join(halves[a][FEATS[role]], how="left").join(target(HC, role).rename("y"), how="inner").join(TC[["pb"]].rename(columns={"pb": "pbB"}))
        f = f[(f.pb >= 50) & (f.pbB >= 50)].copy()
        for f_ in FEATS[role]: f[f_] = f[f_].fillna(f[f_].median())
        # composure = negative of deviation / errors (higher = more composed)
        f["composure"] = -sum(z(f[f_]) for f_ in FEATS[role]) / len(FEATS[role])
        frames.append(f)
    score = lambda fn: float(np.mean([fn(f).corr(f.y) for f in frames]))
    base = lambda f: z(f.press_skill)
    V = {"current model": base, "composure alone": lambda f: f.composure}
    for f_ in FEATS[role]: V[f"{f_} alone (sign: lower is better)"] = (lambda f_: (lambda f: -f[f_]))(f_)
    for lam in (0.1, 0.25, 0.5):
        V[f"current + composure ({lam})"] = (lambda lam: (lambda f: base(f) + lam * z(f.composure)))(lam)
    for k_, fn in V.items(): s3rows.append(dict(role=role, variant=k_, predicts_other_half=round(score(fn), 3), players=len(frames[0])))
    best = max([k_ for k_ in V if k_.startswith("current +")], key=lambda k_: score(V[k_]))
    diffs = []
    for _ in range(1000):
        ds = []
        for f in frames:
            fb = f.iloc[rng.integers(0, len(f), len(f))]; ds.append(V[best](fb).corr(fb.y) - base(fb).corr(fb.y))
        diffs.append(np.mean(ds))
    diffs = np.array(diffs)
    boot.append(dict(role=role, best=best, gain=round(score(V[best]) - score(base), 3), ci95=f"{np.percentile(diffs, 2.5):+.3f} to {np.percentile(diffs, 97.5):+.3f}", share_better=round(float((diffs > 0).mean()), 2)))
    s3rows.append(dict(role=role, variant="(corr composure vs current rating)", predicts_other_half=round(float(np.mean([f.composure.corr(f.press_skill) for f in frames])), 3), players=len(frames[0])))

pd.set_option("display.width", 220)
print("\nSTAGE 2 - repeatability"); print(pd.DataFrame(s2rows).to_string(index=False))
print("\nSTAGE 3 - held-out prediction"); print(pd.DataFrame(s3rows).to_string(index=False))
print(); print(pd.DataFrame(boot).to_string(index=False))
# full-data profile for the current top 10s (descriptive)
for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
    D = BAT if role == "bat" else BOWL
    F = composure_features(D, pid, "shot" if role == "bat" else "dlv")
    if role == "bowl": F = F.join(error_features(D, pid)[["excess_error", "error_z", "obs_err", "exp_err"]], how="outer")
    top = pd.read_csv(f"{OUT}/{role}_final.csv", index_col=0).head(10)[["name"]]
    print(f"\n{role} top 10 composure profile"); print(top.join(F).round(3).to_string())
pd.DataFrame(s2rows).to_csv(f"{OUT}/composure_stage2.csv", index=False); pd.DataFrame(s3rows).to_csv(f"{OUT}/composure_stage3.csv", index=False)
pd.DataFrame(boot).to_csv(f"{OUT}/composure_bootstrap.csv", index=False)
