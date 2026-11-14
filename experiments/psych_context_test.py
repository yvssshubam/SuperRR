"""Test psych situations as CONTEXT (fairness adjustment), not as a skill score.
Situational factors a player did not create are added to the expected-value baseline.
Usage (after psych_factors_test.py, from the repo root): python -I experiments/psych_context_test.py out"""
import sys, importlib.util, numpy as np, pandas as pd
import os
OUT = sys.argv[1]; RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"); sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = pd.read_pickle(f"{OUT}/balls_scored.pkl").sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)
fl = pd.read_pickle(f"{OUT}/psych_flags.pkl")
b = b.merge(fl, on=["match_id", "innings", "innings_ball_num"], how="left")
b["recent"] = b.age_days <= 365; b["w"] = b.w_recency
CTX = r.CTX
# only situations created by others (not the player's own state or own performance)
SIT = {"bat": ["new_at_crease", "collapse", "dot_pressure", "partner_runout"], "bowl": ["teammate_bad_over"]}
def adjust(df, role):
    """subtract the league-average effect of the situation cell from the ball value"""
    d = df.copy(); val = "rv_bat" if role == "bat" else "rv_bowl"
    mask = d.faced if role == "bat" else (d.legal | d.is_wide | d.is_nb)
    x = d[mask]; res = x[val] - x.groupby(CTX)[val].transform("mean")
    cell = x[SIT[role]].astype(int).astype(str).agg("".join, axis=1)
    eff = res.groupby(cell).transform("mean") - res.mean()
    d.loc[mask, val] = d.loc[mask, val] - eff
    return d
def target(half, role, adjusted):
    h = adjust(half, role) if adjusted else half
    pid, val = ("striker_id", "rv_bat") if role == "bat" else ("bowler_id", "rv_bowl")
    d = h[h.faced] if role == "bat" else h[h.legal | h.is_wide | h.is_nb]
    d = d.assign(res=d[val] - d.groupby(CTX)[val].transform("mean"))
    return d[d.pressure].groupby(pid).res.mean()
rows = []
for role in ("bat", "bowl"):
    H = {k: b[(b.match_id % 2) == k] for k in (0, 1)}
    for model in ("current", "with situation context"):
        T = {k: r.player_table(adjust(H[k], role) if model != "current" else H[k], role)[0] for k in (0, 1)}
        for tname, tadj in (("raw pressure value", False), ("situation-adjusted pressure value", True)):
            cors = []; rel = []
            for a, c in ((0, 1), (1, 0)):
                t = T[a][["press_skill", "pb"]].join(target(H[c], role, tadj).rename("y"), how="inner").join(T[c][["pb"]].rename(columns={"pb": "pbB"}))
                t = t[(t.pb >= 50) & (t.pbB >= 50)]; cors.append(t.press_skill.corr(t.y))
            j = T[0][["press_skill", "pb"]].join(T[1][["press_skill", "pb"]], lsuffix="a", rsuffix="b").dropna(); j = j[(j.pba >= 50) & (j.pbb >= 50)]
            rows.append(dict(role=role, model=model, target=tname, predicts_other_half=round(float(np.mean(cors)), 3), reliability=round(j.press_skilla.corr(j.press_skillb), 3), n=len(t)))
print(pd.DataFrame(rows).to_string(index=False))
# effect on full-data rankings
for role in ("bat", "bowl"):
    cur = r.composite(r.player_table(b, role)[0], r.WEIGHTS[role])
    new = r.composite(r.player_table(adjust(b, role), role)[0], r.WEIGHTS[role], list(cur.index))
    names = b.groupby("striker_id").striker_name.last() if role == "bat" else b.groupby("bowler_id").bowler_name.last()
    print(role, "top10 overlap", len(set(cur.index[:10]) & set(new.index[:10])), "spearman", round(cur.score.rank().corr(new.score.reindex(cur.index).rank()), 3))
    print("  new top10:", [names[i] for i in new.index[:10]])
