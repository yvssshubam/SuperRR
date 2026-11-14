"""Where does the spin edge under pressure come from? Bowler's-view value per 100 balls, spin minus pace,
on pressure balls, with controls added one at a time. Standard errors clustered by match.
Usage (after the main pipeline, from the repo root): python -I experiments/spin_edge_test.py out
Writes out/spin_edge_test.csv (control, spin-minus-pace gap, SE) for the figure."""

import sys, os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = sys.argv[1]; sys.argv = [sys.argv[0], OUT]
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
r = _load(os.path.join(HERE, "..", "03_ratings.py"), "r"); pt = _load(os.path.join(HERE, "additions_lib.py"), "additions_lib").pt
b = r.b
b["w"] = 1.0
b = b.sort_values(["match_id", "innings", "innings_ball_num"])
b["bf_before"] = b.groupby(["match_id", "innings", "striker_id"]).faced.cumsum() - b.faced
b["settled"] = np.select([b.bf_before < 5, b.bf_before < 15], [0, 1], 2)
_, _, d = pt(r, b, "bowl", cond="vm", oppteam=False)
d["spin"] = (d.pace_or_spin == "Spin").astype(int)
def gap(d, col, by=None):
    """spin - pace mean of col, optionally after removing cell means of `by`; SE clustered by match."""
    x = d[col] if by is None else d[col] - d.groupby(by)[col].transform("mean")
    s = d.spin - (d.spin.mean() if by is None else d.groupby(by).spin.transform("mean"))
    beta = (x * s).sum() / (s * s).sum()
    res = (x - beta * s) * s; cl = res.groupby(d.match_id).sum()
    se = np.sqrt((cl ** 2).sum()) / (s * s).sum()
    return 100 * beta, 100 * se
P = d[d.pressure]
print("pressure balls: spin share by phase", P.groupby("ph").spin.mean().round(3).to_dict(), " overall", round(P.spin.mean(), 3), " non-pressure", round(d[~d.pressure].spin.mean(), 3))
print("share of pressure balls bowled to a batter on <5 balls: spin", round((P[P.spin == 1].settled == 0).mean(), 3), "pace", round((P[P.spin == 0].settled == 0).mean(), 3))
P = P.assign(a_opp=P.r0 - P._o, a_cond=P.r0 - P._m, a_both=P.r0 - P._o - P._m)
rows = []
for name, col, by in [("context cell only (current baseline)", "r0", None),
                      ("+ opponent batter quality", "a_opp", None),
                      ("+ match/venue level", "a_both", None),
                      ("+ batter new/settled (within phase)", "a_both", ["ph", "settled"]),
                      ("+ same match and innings", "a_opp", ["match_id", "innings"]),
                      ("+ same match, innings, phase, batter new/settled", "a_opp", ["match_id", "innings", "ph", "settled"])]:
    g, se = gap(P, col, by); rows.append((name, round(g, 1), round(se, 1)))
print(pd.DataFrame(rows, columns=["control", "spin - pace (runs/100 balls)", "se"]).to_string(index=False))
csv_rows = [dict(group="pressure", control=n, gap=g, se=e) for n, g, e in rows]
for ph, nm in [(0, "powerplay"), (1, "middle"), (2, "death")]:
    q = P[P.ph == ph]; print(nm, "n spin", int(q.spin.sum()), "gap raw", [round(v, 1) for v in gap(q, "r0")], " within match+innings+settled", [round(v, 1) for v in gap(q, "a_opp", ["match_id", "innings", "settled"])])
    g, e = gap(q, "r0"); csv_rows.append(dict(group="phase", control=nm, gap=round(g, 1), se=round(e, 1)))
N = d[~d.pressure].assign(a_opp=lambda x: x.r0 - x._o)
print("non-pressure balls: raw gap", [round(v, 1) for v in gap(N, "r0")], " within match+innings+phase+settled", [round(v, 1) for v in gap(N, "a_opp", ["match_id", "innings", "ph", "settled"])])
for n, (g, e) in [("context cell only", gap(N, "r0")), ("same match, innings, phase, batter new/settled", gap(N, "a_opp", ["match_id", "innings", "ph", "settled"]))]:
    csv_rows.append(dict(group="normal", control=n, gap=round(g, 1), se=round(e, 1)))
pd.DataFrame(csv_rows).to_csv(f"{OUT}/spin_edge_test.csv", index=False)   # read by 06_figures.py
# decomposition of the edge: runs vs wickets vs extras
for nm, q in [("pressure", P), ("non-pressure", N)]:
    g = q.groupby("spin").agg(runs=("bowler_runs", "mean"), wkt=("bowler_wkt", "mean"), wide_nb=("legal", lambda x: 1 - x.mean()), dot=("total_runs", lambda x: (x == 0).mean()))
    print(nm, (100 * g).round(1).to_dict("index"))
