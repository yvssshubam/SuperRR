"""Section 4.5: does Cost of failure's higher lift come from chasing?
Re-runs the 20-split lift (clutch delta) repeatability on chase balls only (innings 2: both pressure and
normal balls), next to the all-innings figure, with the same splits as repeatability_splits.py (seed 21),
Readiness weights and floors of 50 and 30 pressure balls in each half.
Like report_numbers.py, it needs the 03_ratings.py of the definition being tested: the Cost of failure
version (PRESSURE_DEF = "failure_cost") lives in the v6 test code, which is not part of this repository;
for Stakes, point it at this repository.
Usage: python -I chase_lift_check.py <dir_with_03_ratings.py> <out_dir> <label>
Output: chase_lift_<label>.csv (combined here as chase_lift_check.csv)."""
import sys, os, importlib.util, numpy as np, pandas as pd
REPO, OUT, LABEL = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", os.path.join(REPO, "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = r.b.copy(); b["w"] = r.rating_weights(b, r.READY_OLD_WEIGHT)
print(LABEL, "innings values:", b.innings.value_counts().to_dict(), flush=True)
rng = np.random.default_rng(21); mids = np.sort(b.match_id.unique())
SPL = [set(rng.choice(mids, len(mids) // 2, replace=False)) for _ in range(20)]   # same splits as repeatability_splits.py
rows = []
for cond, sub in (("all", b), ("chase_only", b[b.innings == 2])):
    for role in ("bat", "bowl"):
        res = {f: [] for f in (50, 30)}; n = {f: [] for f in (50, 30)}
        for A in SPL:
            T0 = r.player_table(sub[sub.match_id.isin(A)], role)[0]; T1 = r.player_table(sub[~sub.match_id.isin(A)], role)[0]
            j = T0.join(T1, lsuffix="_a", rsuffix="_b", how="inner")
            for f in res:
                k = j[(j.pb_a >= f) & (j.pb_b >= f)]
                res[f].append(k.clutch_delta_a.corr(k.clutch_delta_b)); n[f].append(len(k))
        for f in res:
            v = np.array(res[f]); rows.append(dict(defn=LABEL, cond=cond, role=role, floor=f, players=int(np.median(n[f])),
                 lift_rep=round(float(np.nanmean(v)), 3), lo=round(float(np.nanmin(v)), 2), hi=round(float(np.nanmax(v)), 2)))
        print(rows[-2], rows[-1], flush=True)
pd.DataFrame(rows).to_csv(f"chase_lift_{LABEL}.csv", index=False)
