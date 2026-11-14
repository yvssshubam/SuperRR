"""Out-of-time test of the recency half-life: rate players on pre-2026 data with different half-lives,
correlate with their (context-adjusted) value on pressure balls in 2026.
Usage (after the main pipeline, from the repo root): python -I experiments/half_life_test.py out"""
import sys, os, importlib.util, pandas as pd
out = sys.argv[1]; sys.argv = [sys.argv[0], out]
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(__file__), "..", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = pd.read_pickle(f"{out}/balls_scored.pkl"); cut = pd.Timestamp("2026-01-01")
train = b[b.match_date < cut].copy(); test = b[b.match_date >= cut]
train["age_days"] = (cut - train.match_date).dt.days; train["recent"] = train.age_days <= 365
rows = []
for role, pid, val, mask in [("bat", "striker_id", "rv_bat", lambda d: d.faced), ("bowl", "bowler_id", "rv_bowl", lambda d: d.legal | d.is_wide | d.is_nb)]:
    t = test[mask(test)].copy(); t["res"] = t[val] - t.groupby(r.CTX)[val].transform("mean")
    tp = t[t.pressure].groupby(pid).res.agg(["mean", "size"]); tp = tp[tp["size"] >= 40]
    for hl in [180, 365, 548, 730, 1095, None]:
        tr = train.copy(); tr["w"] = 1.0 if hl is None else 0.5 ** (tr.age_days / hl); tr["w_recency"] = tr.w
        tab, _, _ = r.player_table(tr, role, role_hl=False)
        j = tab.join(tp, how="inner"); j = j[j.pb >= 60]
        rows.append(dict(role=role, half_life_days=hl or "none", players=len(j), r_pressure_rating=round(j.press_skill.corr(j["mean"]), 3)))
print(pd.DataFrame(rows).to_string(index=False))
