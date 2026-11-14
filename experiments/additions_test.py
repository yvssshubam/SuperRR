"""Held-out tests of three candidate additions (match/venue conditions, required-rate band in the
chase baseline, opponent effects shrunk toward team level).
Usage (after the main pipeline, from the repo root): python -I experiments/additions_test.py out
 Readiness weights (older balls 0.5).
Splits: (1) 10 random 50/50 match splits; (2) 10 venue-disjoint splits (no venue in both halves);
(3) cross-format (rate on IPL, score on T20I and the reverse). Both directions each.
Targets (mean per pressure ball in the held-out part, players with >= 50 pressure balls in each part):
  raw  - context residual only (the criterion used so far)
  cond - raw minus the leave-player-out venue+match level of the held-out matches
  full - cond minus the opponent effect (team-level prior)
  rb   - context residual with the required-rate band in the context cell"""
import sys, os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = sys.argv[1]; sys.argv = [sys.argv[0], OUT]
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
r = _load(os.path.join(HERE, "..", "03_ratings.py"), "r"); pt = _load(os.path.join(HERE, "additions_lib.py"), "additions_lib").pt
b = r.b
from multiprocessing import Pool
b["w"] = r.rating_weights(b, 0.5)
b["rb4"] = np.where(b.innings == 2, np.searchsorted([1.1, 1.5, 2.1], b.need.fillna(0) / np.maximum(b.balls_rem, 1)), 0)
VAR = {"base": {}, "cond_match": dict(cond=True), "cond_venue": dict(cond="v"), "cond_venue+match": dict(cond="vm"),
       "rb8": dict(rbctx="rb"), "rb4": dict(rbctx="rb4"), "oppteam": dict(oppteam=True),
       "all (vm+rb4+oppteam)": dict(cond="vm", rbctx="rb4", oppteam=True)}
PID = {"bat": "striker_id", "bowl": "bowler_id"}
def zcomp(j, wts): return sum(w * ((j[c] - j[c].mean()) / j[c].std()).fillna(0.0) for c, w in wts.items())
def targets(h, role):
    _, _, d = pt(r, h, role, cond="vm", oppteam=True); P = d[d.pressure]; g = P.groupby(PID[role])
    _, _, d2 = pt(r, h, role, rbctx="rb4"); P2 = d2[d2.pressure]
    return pd.DataFrame({"raw": g.r0.mean(), "cond": (P.r0 - P._m).groupby(P[PID[role]]).mean(),
                         "full": (P.r0 - P._m - P._o).groupby(P[PID[role]]).mean(),
                         "rb": P2.groupby(PID[role]).r0.mean(), "n": g.size()})
def one(args):
    kind, sid, A, B = args; rows = []
    H = [b[b.match_id.isin(A)], b[b.match_id.isin(B)]]
    for role in ["bat", "bowl"]:
        TG = [targets(h, role) for h in H]
        T = [{v: pt(r, h, role, **o)[0] for v, o in VAR.items()} for h in H]
        if role == "bowl":
            for i, h in enumerate(H):
                ex = r.execution_component(h, wcol="w")[["execution"]]
                for v in T[i]: T[i][v] = T[i][v].join(ex)
        for a, c in [(0, 1), (1, 0)]:
            keep = T[a]["base"].index[T[a]["base"].pb >= 50].intersection(TG[c].index[TG[c].n >= 50])
            for v in VAR:
                j = T[a][v].reindex(keep).join(TG[c].reindex(keep))
                preds = {"rating": j.press_skill, "composite": zcomp(j, r.WEIGHTS[role])}
                for pn, p in preds.items():
                    for tn in ["raw", "cond", "full", "rb"]:
                        rows.append(dict(kind=kind, split=f"{sid}{a}", role=role, variant=v, pred=pn, target=tn, r=p.corr(j[tn]), n=len(j)))
    return rows
if __name__ == "__main__":
    rng = np.random.default_rng(7); mids = b.match_id.unique(); jobs = []
    for s in range(10):
        A = set(rng.choice(mids, len(mids) // 2, replace=False)); jobs.append(("match", s, A, set(mids) - A))
    mv = b.groupby("match_id").venue_id.first(); venues = mv.unique()
    for s in range(10):
        va = set(rng.choice(venues, len(venues) // 2, replace=False)); A = set(mv.index[mv.isin(va)]); jobs.append(("venue", s, A, set(mids) - A))
    ml = b.groupby("match_id").league.first(); A = set(ml.index[ml == "IPL"]); jobs.append(("format(a=IPL)", 0, A, set(mids) - A))
    with Pool(4) as p: res = p.map(one, jobs)
    R = pd.DataFrame([x for rr in res for x in rr]); R.to_csv(f"{OUT}/additions_test.csv", index=False)
    print("players per split:"); print(R.groupby(["kind", "role"]).n.mean().round(0).unstack())
    order = list(VAR)
    for kind in ["match", "venue"]:
        x = R[(R.kind == kind) & (R.pred == "composite")]
        print(f"\n== {kind}-split, composite score: mean r by target")
        print(x.pivot_table(index="variant", columns=["role", "target"], values="r", aggfunc="mean").reindex(order).round(3).to_string())
        p = x.pivot_table(index=["role", "target", "split"], columns="variant", values="r"); d = p.drop(columns="base").sub(p["base"], axis=0)
        print("gain over the current model (splits better)")
        print(d.groupby(level=[0, 1]).agg(lambda c: f"{c.mean():+.3f} ({(c > 0).sum()}/{c.notna().sum()})")[order[1:]].T.to_string())
