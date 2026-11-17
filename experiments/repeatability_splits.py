"""Split-half repeatability on 20 random match splits (replaces the single odd/even split in section 8.1).
Each split rates the two halves of the matches separately and correlates each component across halves,
for players with at least 50 (and, as a check, 30) pressure balls in each half.
Usage: python -I experiments/repeatability_splits.py out
Writes out/repeatability_20splits.csv (mean, lowest and highest correlation over the 20 splits).
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = r.b.copy()
NSPLIT, FLOORS = 20, (50, 30)
rng = np.random.default_rng(21); mids = np.sort(b.match_id.unique())
SPL = [set(rng.choice(mids, len(mids) // 2, replace=False)) for _ in range(NSPLIT)]
COMP = ["press_skill", "baseline", "win_impact", "consistency", "clutch_delta"]
rows = []
for rating, rw in r.RATINGS.items():
    b["w"] = r.rating_weights(b, rw)
    for role in ("bat", "bowl"):
        res = {f: {c: [] for c in COMP} | {"n": []} for f in FLOORS}
        for A in SPL:
            T = [r.player_table(b[b.match_id.isin(A)], role)[0], r.player_table(b[~b.match_id.isin(A)], role)[0]]
            j0 = T[0].join(T[1], lsuffix="_a", rsuffix="_b", how="inner")
            for f in FLOORS:
                j = j0[(j0.pb_a >= f) & (j0.pb_b >= f)]
                for c in COMP: res[f][c].append(j[c + "_a"].corr(j[c + "_b"]))
                res[f]["n"].append(len(j))
        for f in FLOORS:
            row = dict(rating=rating, role=role, floor=f, players=int(np.median(res[f]["n"])))
            for c in COMP:
                v = np.array(res[f][c]); row[c] = round(float(np.nanmean(v)), 3)
                row[c + "_lo"] = round(float(np.nanmin(v)), 2); row[c + "_hi"] = round(float(np.nanmax(v)), 2)
            rows.append(row)
        print(rating, role, "done", flush=True)
t = pd.DataFrame(rows); t.to_csv(f"{OUT}/repeatability_20splits.csv", index=False)
print(t[["rating", "role", "floor", "players"] + COMP].to_string(index=False))
