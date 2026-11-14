"""Cross-half predictive test of candidate improvements (venue, leverage weighting, batting split).
Usage (after the main pipeline, from the repo root): python -I experiments/candidate_test.py out
Score = corr( rating built on half A , raw context-adjusted pressure value in half B ), averaged both ways,
for players with >=50 pressure balls in each half. Also reports split-half reliability of the rating."""
import sys, importlib.util, numpy as np, pandas as pd
import os
data = sys.argv[1]; code = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"); sys.argv = [sys.argv[0], data]
spec = importlib.util.spec_from_file_location("r", code); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = pd.read_pickle(f"{data}/balls_scored.pkl"); ER = np.load(f"{data}/ER.npy")
b["w"] = b.w_recency; b["recent"] = b.age_days <= 365
lg = b.legal.values.astype(int)
# batting split: value without the dismissal, and the dismissal's extra cost
R = lambda br, w: ER[b.env.values, np.clip(br, 0, 120), np.clip(w, 0, 10)]
b["rv_bat_noW"] = np.where(b.faced, b.bat_runs + R(b.balls_rem.values - lg, b.wih.values) - R(b.balls_rem.values, b.wih.values), 0.0)
b["rv_bat_W"] = b.rv_bat - b.rv_bat_noW
orig_pt = r.player_table

def target(half, role):
    """raw context-adjusted pressure value per ball (the thing we want to predict)"""
    pid, val, mask = ("striker_id", "rv_bat", half.faced) if role == "bat" else ("bowler_id", "rv_bowl", half.legal | half.is_wide | half.is_nb)
    d = half[mask]; d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    p = d[d.pressure]; return p.groupby(pid).res.agg(["mean", "size"])

def variant_table(df, role, v):
    if v == "venue":
        d = df.copy()
        for col in ("rv_bat", "rv_bowl"):
            # venue effect estimated on non-pressure balls of the same innings (scoring level of the ground)
            res = d[col] - d.groupby(r.CTX)[col].transform("mean")
            eff = res.groupby([d.venue_id, d.innings]).transform("mean")
            n = res.groupby([d.venue_id, d.innings]).transform("size")
            d[col] = d[col] - eff * n / (n + 2000)          # shrink venue effect (prior strength 2000 balls)
        return orig_pt(d, role)
    if v == "li_weight":
        d = df.copy(); thr = d[d.pressure].groupby("innings").li.transform("min")
        m = d.pressure
        d.loc[m, "w"] = d.loc[m, "w"] * np.clip(d.loc[m, "li"] / d.loc[m].groupby("innings").li.transform("median"), 0.5, 3.0)
        return orig_pt(d, role)
    if v == "bat_split" and role == "bat":
        tR, _, _ = orig_pt(df.assign(rv_bat=df.rv_bat_noW), role)
        tW, _, _ = orig_pt(df.assign(rv_bat=df.rv_bat_W), role)
        t, k, d = orig_pt(df, role)
        t["press_skill"] = tR.press_skill.reindex(t.index) + tW.press_skill.reindex(t.index)
        return t, k, d
    return orig_pt(df, role)

rows = []
for v in ["baseline", "venue", "li_weight", "bat_split"]:
    for role in ["bat", "bowl"]:
        if v == "bat_split" and role == "bowl": continue
        res = {}
        for h in (0, 1):
            t, _, _ = variant_table(b[(b.match_id % 2) == h], role, v)
            res[h] = (t, target(b[(b.match_id % 2) == h], role))
        pred, rel = [], []
        for a, c in [(0, 1), (1, 0)]:
            ta, tgt = res[a][0], res[c][1]
            j = ta[["press_skill", "pb"]].join(tgt, how="inner").join(res[c][0][["pb"]].rename(columns={"pb": "pbB"}), how="inner")
            j = j[(j.pb >= 50) & (j.pbB >= 50)]
            pred.append(j.press_skill.corr(j["mean"]))
        j = res[0][0][["press_skill", "pb"]].join(res[1][0][["press_skill", "pb"]], lsuffix="_a", rsuffix="_b").dropna()
        j = j[(j.pb_a >= 50) & (j.pb_b >= 50)]
        rows.append(dict(variant=v, role=role, n=len(j), predict_other_half=round(np.mean(pred), 3), reliability=round(j.press_skill_a.corr(j.press_skill_b), 3)))
print(pd.DataFrame(rows).to_string(index=False))
