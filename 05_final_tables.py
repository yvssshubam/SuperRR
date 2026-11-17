"""Step 5: final tables for both ratings (adds last team / last match and national team).
Usage: python -I 05_final_tables.py <out_dir> <data_dir>

The submitted top 10s are the pure performance ranking (`rank`): no player is removed for nationality or
availability, because Round 1 asks who performs best under pressure, not who a franchise could pick.
`national_team` (the team a player represents in T20Is in the data) is kept for reference only."""
import sys, pandas as pd
OUT, D = sys.argv[1], sys.argv[2]
b = pd.read_pickle(f"{OUT}/balls_scored.pkl").sort_values("match_date")
tn = pd.read_csv(f"{D}/teams.csv").drop_duplicates("team_id").set_index("team_id").team_name
t20i = b[b.league == "T20I"]
nat = {"bat": t20i.groupby("striker_id").batting_team_id.agg(lambda s: s.mode().iloc[0]).map(tn),
       "bowl": t20i.groupby("bowler_id").bowling_team_id.agg(lambda s: s.mode().iloc[0]).map(tn)}
last = {"bat": (b.groupby("striker_id").match_date.max(), b.groupby("striker_id").batting_team_id.last()),
        "bowl": (b.groupby("bowler_id").match_date.max(), b.groupby("bowler_id").bowling_team_id.last())}
for stem in ["", "_career"]:          # "" = Current Pressure Readiness (submitted), "_career" = Career Pressure Ability
    for r in ["bat", "bowl"]:
        e = pd.read_csv(f"{OUT}/{r}{stem}_ratings.csv", index_col=0).join(pd.read_csv(f"{OUT}/{r}{stem}_bootstrap.csv", index_col=0))
        e["last_match"] = last[r][0].reindex(e.index).dt.date
        e["last_team"] = last[r][1].reindex(e.index).map(tn)
        e["national_team"] = nat[r].reindex(e.index)
        e.to_csv(f"{OUT}/{r}{stem}_final.csv")
