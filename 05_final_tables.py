"""Step 5: final tables for both ratings (adds last team / last match, national team and IPL eligibility).
Usage: python -I 05_final_tables.py <out_dir> <data_dir>

IPL eligibility (README section 7): the brief asks for players Rajasthan Royals could back at the IPL 2027
auction, so a player who cannot play in the IPL at all is not submitted. Pakistan nationals have not been
part of the IPL since 2008. Nationality is read from the data: the team a player represents in T20Is.
`rank` is the performance rank among all eligible-by-sample players; `submitted_rank` is the rank after
removing players who cannot play in the IPL (blank for them). The ratings themselves are unchanged."""
import sys, pandas as pd
OUT, D = sys.argv[1], sys.argv[2]
NOT_IN_IPL = {"Pakistan"}
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
        e["ipl_eligible"] = ~e.national_team.isin(NOT_IN_IPL)
        e["submitted_rank"] = pd.Series(range(1, int(e.ipl_eligible.sum()) + 1), index=e.index[e.ipl_eligible]).reindex(e.index)
        e.to_csv(f"{OUT}/{r}{stem}_final.csv")
        if stem == "":
            out = e[~e.ipl_eligible].head(30)
            if len(out): print(r, "not IPL-eligible in the top 30:", list(zip(out["name"], out["rank"])))
