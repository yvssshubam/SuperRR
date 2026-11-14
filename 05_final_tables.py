"""Step 5: final tables for both ratings (adds last team / last match). Usage: python -I 05_final_tables.py <out_dir> <data_dir>"""
import sys, pandas as pd
OUT, D = sys.argv[1], sys.argv[2]
b = pd.read_pickle(f"{OUT}/balls_scored.pkl").sort_values("match_date")
tn = pd.read_csv(f"{D}/teams.csv").drop_duplicates("team_id").set_index("team_id").team_name
last = {"bat": (b.groupby("striker_id").match_date.max(), b.groupby("striker_id").batting_team_id.last()),
        "bowl": (b.groupby("bowler_id").match_date.max(), b.groupby("bowler_id").bowling_team_id.last())}
for stem in ["", "_career"]:          # "" = Current Pressure Readiness (submitted), "_career" = Career Pressure Ability
    for r in ["bat", "bowl"]:
        e = pd.read_csv(f"{OUT}/{r}{stem}_ratings.csv", index_col=0).join(pd.read_csv(f"{OUT}/{r}{stem}_bootstrap.csv", index_col=0))
        e["last_match"] = last[r][0].reindex(e.index).dt.date
        e["last_team"] = last[r][1].reindex(e.index).map(tn)
        e.to_csv(f"{OUT}/{r}{stem}_final.csv")
