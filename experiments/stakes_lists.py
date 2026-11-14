import sys, os, importlib.util, numpy as np, pandas as pd
"""Top-10 lists if pressure were stakes-weighted (alternative view, not adopted).
Usage (from the repo root): python -I experiments/stakes_lists.py out out/match_stakes.csv"""
OUT, STK = sys.argv[1], sys.argv[2]; RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"); sys.argv=[sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = pd.read_pickle(f"{OUT}/balls_scored.pkl"); b["recent"] = b.age_days <= 365; b["w"] = b.w_recency
st = pd.read_csv(STK).set_index(["match_id","team_id"])
for side, col in (("bat","batting_team_id"),("bowl","bowling_team_id")):
    M = st.M.reindex(pd.MultiIndex.from_arrays([b.match_id, b[col]])).fillna(1.0).values
    b["press_"+side] = ((b.li/np.where(b.knock_out==1,1.2,1.0))*M).groupby(b.innings).rank(pct=True) >= 0.75
names = {"bat": b.groupby("striker_id").striker_name.last(), "bowl": b.groupby("bowler_id").bowler_name.last()}
for role in ("bat","bowl"):
    cur = pd.read_csv(f"{OUT}/{role}_final.csv", index_col=0)
    bb = b.assign(pressure=b["press_"+role])
    t = r.player_table(bb, role)[0]
    if role == "bowl": t = t.join(r.execution_component(bb))
    e = r.composite(t, r.WEIGHTS[role], list(cur.index))
    common = cur.index.intersection(e.index)
    print(role, "overlap", len(set(e.index[:10]) & set(cur.index[:10])), "spearman", round(cur.loc[common,"score"].rank().corr(e.loc[common,"score"].rank()),3))
    print("  stakes-weighted top 10:", [names[role][i] for i in e.index[:10]])
    print("  in:", [names[role][i] for i in e.index[:10] if i not in cur.index[:10]], " out:", [names[role][i] for i in cur.index[:10] if i not in e.index[:10]])
