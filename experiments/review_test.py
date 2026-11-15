"""Held-out tests behind README section 9.13 (review fixes):
  bowlers: previous execution score (with the delivery-mix term) vs the rebuilt phase-matched score vs none,
           and the bowling composite with and without its separate clutch-delta component;
  batters: the previous 4-component composite vs the pressure rating alone.
Also scores each execution sub-measure on its own.
Usage (after the main pipeline, from the repo root): python -I experiments/review_test.py out
Same design as readiness_test.py: 10 random 50/50 match splits (both directions = 20 comparisons) and
3 out-of-time folds (1 Jan 2024/2025/2026 -> next 12 months); Readiness weights; same players for every variant."""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]; sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
# Reproduces the v4 decision, so psychological pooling (added later, in v5) is switched off here.
r.PSY_POOL_WEIGHT = {"bat": 0.0, "bowl": 0.0}
_jsd_rows = None

# ---- the previous (v2/v3) execution score, kept verbatim for comparison ----
EXEC_SEED = 5
def _jsd_rows(P, q):
    """Jensen-Shannon divergence of each row of P against distribution q."""
    M = (P + q) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(P > 0, P * np.log(P / M), 0).sum(1); c = np.where(q > 0, q * np.log(q / M), 0).sum(1)
    return (a + c) / 2
def old_execution_component(b, minP=30, minN=100, alpha=20, nsim=200, wcol=None):
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

b = pd.read_pickle(f"{OUT}/balls_scored.pkl")
ROLE = {"bat": ("striker_id", "rv_bat", lambda d: d.faced), "bowl": ("bowler_id", "rv_bowl", lambda d: d.legal | d.is_wide | d.is_nb)}
def norm(w): s = sum(w.values()); return {k: v / s for k, v in w.items()}
WB_PREV = {"press_skill": 0.36, "clutch_delta": 0.135, "consistency": 0.09, "win_impact": 0.135, "execution": 0.10}
VARS = {
    "bowl": {"previous execution": (norm(WB_PREV), "old"), "rebuilt execution": (norm(WB_PREV), "new"),
             "no execution": (norm({k: v for k, v in WB_PREV.items() if k != "execution"}), None),
             "rebuilt execution, no separate clutch": (norm({k: v for k, v in WB_PREV.items() if k != "clutch_delta"}), "new"),
             "previous execution, no separate clutch": (norm({k: v for k, v in WB_PREV.items() if k != "clutch_delta"}), "old"),
             "pressure rating only": ({"press_skill": 1.0}, None),
             "rebuilt execution alone": ({"execution": 1.0}, "new"), "previous execution alone": ({"execution": 1.0}, "old"),
             "previous mix term alone": ({"mix": 1.0}, "old"), "previous excess error alone": ({"exc": 1.0}, "old")},
    "bat": {"previous composite (60/13/13/13)": (norm({"press_skill": 0.45, "clutch_delta": 0.10, "consistency": 0.10, "win_impact": 0.10}), None),
            "composite without separate clutch": (norm({"press_skill": 0.45, "consistency": 0.10, "win_impact": 0.10}), None),
            "pressure rating only": ({"press_skill": 1.0}, None)}}

def target(d, role):
    pid, val, mask = ROLE[role]; d = d[mask(d)].copy()
    d["res"] = d[val] - d.groupby(r.CTX)[val].transform("mean")
    return d[d.pressure].groupby(pid).res.agg(["mean", "size"])
def z(s): return ((s - s.mean()) / s.std()).fillna(0.0)
def score(j, wts): return sum(w * z(j[c]) for c, w in wts.items())
def tables(h):
    h = h.assign(w=r.rating_weights(h, r.READY_OLD_WEIGHT))
    tb = r.player_table(h, "bat")[0]; tw = r.player_table(h, "bowl")[0]
    newx = r.execution_component(h, wcol="w")[["execution"]]
    oldx = old_execution_component(h)
    oldx = oldx.assign(mix=-oldx.delivery_dev_z, exc=-oldx.excess_error)[["execution", "mix", "exc"]]
    return {"bat": tb, "bowl_new": tw.join(newx), "bowl_old": tw.join(oldx)}
def evaluate(TA, tg, keep, role, tag, rows, extra):
    for v, (wts, ex) in VARS[role].items():
        t = TA["bat"] if role == "bat" else TA["bowl_old" if ex == "old" else "bowl_new"]
        j = t.reindex(keep).join(tg)
        rows.append(dict(test=tag, role=role, variant=v, r=score(j, wts).corr(j["mean"]), n=len(j), **extra))
rows = []
rng = np.random.default_rng(7); mids = b.match_id.unique()
for s in range(10):
    A = set(rng.choice(mids, len(mids) // 2, replace=False))
    H = [b[b.match_id.isin(A)].copy(), b[~b.match_id.isin(A)].copy()]
    for h in H: h["recent"] = h.age_days <= 365
    T = [tables(h) for h in H]
    for role in ["bat", "bowl"]:
        TG = [target(h, role) for h in H]
        for a, c in [(0, 1), (1, 0)]:
            base = T[a]["bat"] if role == "bat" else T[a]["bowl_new"]; basec = T[c]["bat"] if role == "bat" else T[c]["bowl_new"]
            keep = base.index[base.pb >= 50].intersection(basec.index[basec.pb >= 50]).intersection(TG[c].index)
            evaluate(T[a], TG[c], keep, role, "cross-half", rows, dict(fold=f"{s}{a}"))
    print("split", s, flush=True)
for cut in ["2024-01-01", "2025-01-01", "2026-01-01"]:
    cut = pd.Timestamp(cut)
    tr = b[b.match_date < cut].copy(); te = b[(b.match_date >= cut) & (b.match_date < cut + pd.Timedelta(days=366))]
    tr["age_days"] = (cut - tr.match_date).dt.days; tr["recent"] = tr.age_days <= 365
    TA = tables(tr)
    for role in ["bat", "bowl"]:
        tg = target(te, role); tg = tg[tg["size"] >= 40]
        base = TA["bat"] if role == "bat" else TA["bowl_new"]
        keep = base.index[base.pb >= 60].intersection(tg.index)
        evaluate(TA, tg, keep, role, "out-of-time", rows, dict(fold=str(cut.date())))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/review_test.csv", index=False)
print("players per fold:", R.groupby(["test", "role"]).n.mean().round(0).to_dict())
for role in ["bat", "bowl"]:
    x = R[R.role == role]; p = x.pivot_table(index=["test", "fold"], columns="variant", values="r")
    ref = "previous composite (60/13/13/13)" if role == "bat" else "previous execution"
    out = pd.DataFrame({"mean r": x.groupby(["test", "variant"]).r.mean().unstack(0).round(3).stack()}).unstack(1)
    print(f"\n== {role}: mean r"); print(x.pivot_table(index="variant", columns="test", values="r", aggfunc="mean").round(3).to_string())
    d = p.drop(columns=ref).sub(p[ref], axis=0)
    print(f"gain over '{ref}' (folds better)")
    print(d.groupby(level=0).agg(lambda c: f"{c.mean():+.3f} ({(c > 0).sum()}/{c.notna().sum()})").T.to_string())
