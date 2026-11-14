"""Choose the Readiness weight for older matches, and compare the new ratings with the previous model.
Usage (after the main pipeline, from the repo root):
    python -I experiments/readiness_test.py out [previous_03_ratings.py]

1) Rolling out-of-time test: for each cut-off (1 Jan 2024, 2025, 2026) the ratings are built only from
   matches before the cut-off and correlated with each player's context-adjusted value per pressure
   ball in the following 12 months (players with >= 60 pressure balls before and >= 40 after).
2) Cross-half test: 10 random 50/50 match splits; the rating built on one half is correlated with
   pressure value in the other half (players with >= 50 pressure balls in each half), both directions.
Predictors: pressure rating alone and the full composite score.
Variants: Readiness with older-ball weight a0 in {0, 0.1, 0.25, 0.5}; Career (a0 = 1); and, if the
previous 03_ratings.py is given, the previous model (18-month half-life + separate 12-month form)."""
import sys, os, importlib.util, numpy as np, pandas as pd
out = sys.argv[1]; prev = sys.argv[2] if len(sys.argv) > 2 else None; sys.argv = [sys.argv[0], out]
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
r = load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"), "r")
o = load(prev, "o") if prev else None
b = pd.read_pickle(f"{out}/balls_scored.pkl")
ROLE = {"bat": ("striker_id", "rv_bat", lambda d: d.faced), "bowl": ("bowler_id", "rv_bowl", lambda d: d.legal | d.is_wide | d.is_nb)}
A0S = [0.0, 0.1, 0.25, 0.5, 1.0]

def target(d, role):
    pid, val, mask = ROLE[role]; d = d[mask(d)].copy()
    d["res"] = d[val] - d.groupby(r.CTX)[val].transform("mean")
    return d[d.pressure].groupby(pid).res.agg(["mean", "size"])

def zcomp(j, wts):
    return sum(w * ((j[c] - j[c].mean()) / j[c].std()).fillna(0.0) for c, w in wts.items())

def tables(tr):
    """{variant: {role: table}} for one training set (age_days / recent already set relative to its end)."""
    res = {}
    for a0 in A0S:
        d = tr.assign(w=r.rating_weights(tr, a0)); ex = r.execution_component(d, wcol="w")[["execution"]]
        res[f"a0={a0}"] = {"bat": r.player_table(d, "bat")[0], "bowl": r.player_table(d, "bowl")[0].join(ex)}
    if o is not None:
        d = tr.assign(w=0.5 ** (tr.age_days / 548)); d["w_recency"] = d.w
        ex = o.execution_component(d)[["execution"]]
        res["previous"] = {"bat": o.player_table(d, "bat", role_hl=False)[0],
                           "bowl": o.player_table(d, "bowl", role_hl=False)[0].join(ex)}
    return res

def score(tab, role, variant, j):
    W = (o.WEIGHTS if variant == "previous" else r.WEIGHTS)[role]
    return {"pressure rating": j.press_skill, "composite": zcomp(j, W)}

rows = []
# ---- 1) rolling out-of-time ----
for cut in ["2024-01-01", "2025-01-01", "2026-01-01"]:
    cut = pd.Timestamp(cut)
    tr = b[b.match_date < cut].copy(); te = b[(b.match_date >= cut) & (b.match_date < cut + pd.Timedelta(days=366))]
    tr["age_days"] = (cut - tr.match_date).dt.days; tr["recent"] = tr.age_days <= 365
    T = tables(tr)
    for role in ["bat", "bowl"]:
        tg = target(te, role); tg = tg[tg["size"] >= 40]
        base = T["a0=1.0"][role]; keep = base.index[base.pb >= 60].intersection(tg.index)   # same players for every variant
        for v, tabs in T.items():
            j = tabs[role].reindex(keep).join(tg, how="inner")
            for k, s in score(tabs, role, v, j).items():
                rows.append(dict(test="out-of-time", fold=str(cut.date()), role=role, variant=v, predictor=k, r=s.corr(j["mean"]), n=len(j)))
    print("cut", cut.date(), "done", flush=True)
# ---- 2) cross-half ----
rng = np.random.default_rng(7); mids = b.match_id.unique()
b["recent"] = b.age_days <= 365
for s_ in range(10):
    A = set(rng.choice(mids, len(mids) // 2, replace=False))
    H = [b[b.match_id.isin(A)].copy(), b[~b.match_id.isin(A)].copy()]
    T = [tables(h) for h in H]; TG = {role: [target(h, role) for h in H] for role in ["bat", "bowl"]}
    for role in ["bat", "bowl"]:
        for a, c in [(0, 1), (1, 0)]:
            ba, bc_ = T[a]["a0=1.0"][role], T[c]["a0=1.0"][role]       # same players for every variant
            keep = ba.index[ba.pb >= 50].intersection(bc_.index[bc_.pb >= 50]).intersection(TG[role][c].index)
            for v in T[a]:
                ta = T[a][v][role]; j = ta.reindex(keep).join(TG[role][c], how="inner")
                for k, sc in score(ta, role, v, j).items():
                    rows.append(dict(test="cross-half", fold=f"{s_}{a}", role=role, variant=v, predictor=k, r=sc.corr(j["mean"]), n=len(j)))
    print("split", s_, "done", flush=True)
R = pd.DataFrame(rows); R.to_csv(f"{out}/readiness_test.csv", index=False)
print("players per fold:", R.groupby(["test", "role"]).n.mean().round(0).to_dict())
for t in ["out-of-time", "cross-half"]:
    x = R[R.test == t].pivot_table(index=["role", "predictor", "fold"], columns="variant", values="r")
    if "previous" in x:
        d = x.drop(columns="previous").sub(x["previous"], axis=0)
        print(f"\n{t}: mean gain over previous model (folds better)")
        print(d.groupby(level=[0, 1]).agg(lambda c: f"{c.mean():+.3f} ({(c > 0).sum()}/{c.notna().sum()})").to_string())
for t in ["out-of-time", "cross-half"]:
    x = R[R.test == t].pivot_table(index=["predictor", "variant"], columns="role", values="r", aggfunc="mean").round(3)
    print(f"\n{t} (mean r over folds)\n", x.to_string())
