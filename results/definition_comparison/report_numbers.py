"""Report revision brief: numbers for the report, regenerated from the data.
1. Split-half repeatability on 20 random match splits (seed 21), for the v5 components (Readiness and Career)
   and for the clutch and pressure-rating rows of the three-definition table (v5, v6, v7).
2. Margin of error for the v7 behaviour finding (500 match resamples, seed 42).
3. The three-definition table and the two marker tables.
Usage: python -I experiments/report_numbers.py <v7_out> <v6_out> <v5_out> <result_dir>
"""
import sys, os, json, importlib.util, numpy as np, pandas as pd
O7, O6, O5, RES = sys.argv[1:5]; sys.argv = [sys.argv[0], O7]
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = r.b.copy()
MODELS = {"v5": dict(DEF="leverage", pool=0.25), "v6": dict(DEF="failure_cost", pool=0.0), "v7": dict(DEF="v7", pool=0.0)}
def use(v):
    r.PRESSURE_DEF = MODELS[v]["DEF"]; r.PSY_POOL_WEIGHT = {"bat": 0.0, "bowl": MODELS[v]["pool"]}; r.UNIT_SFX = ""
UNIT = {("v5", "bat"): "pressure_li", ("v5", "bowl"): "pressure_li", ("v6", "bat"): "press_inn_bat", ("v6", "bowl"): "press_over_bowl",
        ("v7", "bat"): "unit_v7_bat", ("v7", "bowl"): "press_v7_over"}
OUTD = {"v5": O5, "v6": O6, "v7": O7}
PID = {"bat": "striker_id", "bowl": "bowler_id"}
bowl_mask = b.legal | b.is_wide | b.is_nb
out = {}; txt = []
def show(title, df): txt.append(f"\n== {title}\n" + df.to_string(index=False)); print(txt[-1], flush=True)

# ---------- 1. 20 random splits ----------
NSPLIT, FLOORS = 20, (50, 30)
rng = np.random.default_rng(21); mids = np.sort(b.match_id.unique())
SPL = [set(rng.choice(mids, len(mids) // 2, replace=False)) for _ in range(NSPLIT)]
COMP = ["press_skill", "baseline", "win_impact", "consistency", "clutch_delta"]
def split_corrs(model, rating_w, role):
    use(model); b["w"] = r.rating_weights(b, rating_w); res = {f: {c: [] for c in COMP} | {"n": []} for f in FLOORS}
    for A in SPL:
        T = [r.player_table(b[b.match_id.isin(A)], role)[0], r.player_table(b[~b.match_id.isin(A)], role)[0]]
        j0 = T[0].join(T[1], lsuffix="_a", rsuffix="_b", how="inner")
        for f in FLOORS:
            j = j0[(j0.pb_a >= f) & (j0.pb_b >= f)]
            for c in COMP: res[f][c].append(j[c + "_a"].corr(j[c + "_b"]))
            res[f]["n"].append(len(j))
    return res
rows = []
for model, ratings in [("v5", {"Readiness": r.READY_OLD_WEIGHT, "Career": 1.0}), ("v6", {"Readiness": r.READY_OLD_WEIGHT}), ("v7", {"Readiness": r.READY_OLD_WEIGHT})]:
    for rating, rw in ratings.items():
        for role in ("bat", "bowl"):
            res = split_corrs(model, rw, role)
            for f in FLOORS:
                row = dict(model=model, rating=rating, role=role, floor=f, players=int(np.median(res[f]["n"])))
                for c in COMP:
                    v = np.array(res[f][c]); row[c] = round(float(np.nanmean(v)), 3); row[c + "_lo"] = round(float(np.nanmin(v)), 2); row[c + "_hi"] = round(float(np.nanmax(v)), 2)
                rows.append(row)
            print(model, rating, role, "splits done", flush=True)
rep = pd.DataFrame(rows); rep.to_csv(f"{RES}/repeatability_20splits.csv", index=False)
show("20 random splits: mean split-half correlation (range in the csv)", rep[["model", "rating", "role", "floor", "players"] + COMP])

# ---------- 2. behaviour finding with a margin of error ----------
b["dot"] = (b.total_runs == 0) & b.legal; b["bnd"] = b.is_four | b.is_six
b["err"] = b.is_wide | b.is_nb | b.delivery_style.fillna("").isin(["Full Toss", "Beamer"])
MET = {"bat": [("dismissal", "striker_out"), ("dot", "dot"), ("boundary", "bnd")],
       "bowl": [("error", "err"), ("dot", "dot"), ("boundary conceded", "bnd"), ("wicket", "bowler_wkt")]}
NB = 500; brng = np.random.default_rng(42); midx = {m: i for i, m in enumerate(mids)}
BW = np.vstack([np.ones(len(mids))] + [np.bincount(brng.integers(0, len(mids), len(mids)), minlength=len(mids)) for _ in range(NB)])
def shift(tab, mw):
    """Check-4 statistic: flagged minus unflagged rate within player x innings x phase cells (>= 10 balls each side)."""
    w = mw[tab.mi.values]; t = tab.assign(s=tab.s * w, n=tab.n * w).groupby(["p", "inn", "ph", "fl"])[["s", "n"]].sum().unstack("fl")
    t = t[(t[("n", True)] >= 10) & (t[("n", False)] >= 10)]
    wt = np.minimum(t[("n", True)], t[("n", False)])
    return 100 * float(((t[("s", True)] / t[("n", True)] - t[("s", False)] / t[("n", False)]) * wt).sum() / wt.sum())
rows = []
for model in ("v7", "v5"):
    for role in ("bat", "bowl"):
        d = b[b.faced] if role == "bat" else b[bowl_mask]; fl = UNIT[(model, role)]
        for lab, col in MET[role]:
            tab = d.groupby([PID[role], "innings", "ph", fl, "match_id"])[col].agg(["sum", "size"]).reset_index()
            tab.columns = ["p", "inn", "ph", "fl", "m", "s", "n"]; tab["mi"] = tab.m.map(midx); tab["s"] = tab.s.astype(float)
            vals = np.array([shift(tab, BW[k]) for k in range(NB + 1)])
            lo, hi = np.percentile(vals[1:], [2.5, 97.5])
            rows.append(dict(model=model, role=role, measure=lab, shift_pp=round(vals[0], 2), lo95=round(lo, 2), hi95=round(hi, 2),
                             includes_zero=bool(lo <= 0 <= hi)))
            print(model, role, lab, rows[-1], flush=True)
beh = pd.DataFrame(rows); beh.to_csv(f"{RES}/behaviour_shift_ci.csv", index=False)
show(f"Behaviour shift on flagged vs other balls, same player, innings and phase, with 95% range over {NB} match resamples (percentage points)", beh)

# ---------- 3. tables ----------
FIN = {(v, role): pd.read_csv(f"{OUTD[v]}/{role}_final.csv", index_col=0) for v in MODELS for role in ("bat", "bowl")}
def shares(v):
    d = b[b.faced]; m = d[UNIT[(v, "bat")]]; f = d[m]
    free = ((f.innings == 1) & (f.ph == 2) & (f.wih >= 6)) | ((f.ph == 0) & (f.wih >= 9))
    return m.mean(), free.mean(), ((f.wp_before < .1) | (f.wp_before > .9)).mean()
tot = {}  # total shift from check 4 (point estimate, all measures)
for model in MODELS:
    for role in ("bat", "bowl"):
        d = b[b.faced] if role == "bat" else b[bowl_mask]; fl = UNIT[(model, role)]; t = 0
        for lab, col in MET[role]:
            g = d.groupby([PID[role], "innings", "ph", fl])[col].agg(["mean", "size"]).unstack(fl)
            g = g[(g[("size", True)] >= 10) & (g[("size", False)] >= 10)]; wt = np.minimum(g[("size", True)], g[("size", False)])
            t += abs(100 * float(((g[("mean", True)] - g[("mean", False)]) * wt).sum() / wt.sum()))
        tot[(model, role)] = t
R50 = rep[(rep.rating == "Readiness") & (rep.floor == 50)].set_index(["model", "role"])
rows = []
for v in MODELS:
    rated, free, dead = shares(v)
    sub = {role: FIN[(v, role)].sort_values("rank").head(10) for role in ("bat", "bowl")}   # submitted lists = pure performance rank
    rows.append({"model": v, "batter balls rated as pressure": f"{rated:.0%}", "free swings among them": f"{free:.1%}",
                 "from decided games (batters)": f"{dead:.1%}",
                 "behaviour change bat / bowl (pp)": f"{tot[(v, 'bat')]:.1f} / {tot[(v, 'bowl')]:.1f}",
                 "clutch repeat bat / bowl (20 splits, 50+)": f"{R50.loc[(v, 'bat'), 'clutch_delta']:.2f} / {R50.loc[(v, 'bowl'), 'clutch_delta']:.2f}",
                 "rating repeat bat / bowl (20 splits, 50+)": f"{R50.loc[(v, 'bat'), 'press_skill']:.2f} / {R50.loc[(v, 'bowl'), 'press_skill']:.2f}",
                 "players in splits bat / bowl": f"{R50.loc[(v, 'bat'), 'players']} / {R50.loc[(v, 'bowl'), 'players']}",
                 "eligible bat / bowl": f"{len(FIN[(v, 'bat')])} / {len(FIN[(v, 'bowl')])}",
                 "top-10 bootstrap share bat / bowl": f"{sub['bat'].top10_freq.mean():.0%} / {sub['bowl'].top10_freq.mean():.0%}"})
three = pd.DataFrame(rows).set_index("model").T.reset_index().rename(columns={"index": "row"})
three.to_csv(f"{RES}/three_definitions.csv", index=False); show("Three-definition table", three)

MARK = {3: "Firm", 2: "Fairly firm", 1: "Depends on the definition"}
for role in ("bat", "bowl"):
    s5 = FIN[("v5", role)]; s5 = s5[s5["rank"] <= 10].sort_values("rank"); rows = []
    for pid, x in s5.iterrows():
        rk = {}
        for v in ("v6", "v7"):
            f = FIN[(v, role)]; rk[v] = int(f.loc[pid, "rank"]) if pid in f.index and pd.notna(f.loc[pid, "rank"]) else None
        n = 1 + sum(1 for v in rk.values() if v is not None and v <= 10)
        rows.append(dict(submitted_rank=int(x["rank"]), name=x["name"], v6_rank=rk["v6"] or "Not eligible", v7_rank=rk["v7"] or "Not eligible",
                         marker=MARK[n], clutch_delta=round(x.clutch_delta, 1), top10_freq=f"{x.top10_freq:.0%}"))
    mk = pd.DataFrame(rows); mk.to_csv(f"{RES}/markers_{role}.csv", index=False); show(f"Marker table, {role}", mk)

open(f"{RES}/report_numbers.txt", "w").write("\n".join(txt))
