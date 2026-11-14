"""Step 1: clean data and build ball-level match state.
Usage: python -I 01_state.py <data_dir> <out_dir>
"""
import os, sys, numpy as np, pandas as pd

D, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
comp = pd.read_csv(f"{D}/competitions.csv")
m = pd.read_csv(f"{D}/matches.csv").merge(comp, on="comp_id")
b = pd.read_csv(f"{D}/ball_by_ball.csv", low_memory=False, keep_default_na=False,
                na_values=[""])

# ---------- competition class ----------
def cls(r):
    if r.comp_name.startswith("IPL"): return "IPL"
    if r.match_format == "T20I": return "T20I"
    return "Other"          # emerging-team Asia Cups: kept out of ratings
m["league"] = m.apply(cls, axis=1)
m["match_date"] = pd.to_datetime(m.match_date)

# ---------- match exclusions ----------
m["no_result"] = m.result.str.contains("No Result|Abandon", case=False, na=True) | m.win_team_id.isna()
m["rain_affected"] = m[["first_inn_revised_overs", "second_inn_revised_overs", "revised_target"]].notna().any(axis=1)
keep = m[(~m.no_result) & (~m.rain_affected) & (m.league != "Other")]
excl = {"total_matches": len(m), "no_result": int(m.no_result.sum()),
        "rain_affected": int((m.rain_affected & ~m.no_result).sum()),
        "other_comp": int(((m.league == "Other") & ~m.no_result & ~m.rain_affected).sum())}

b = b[b.innings.isin([1, 2]) & b.match_id.isin(keep.match_id)].copy()
excl["no_ball_data"] = int(len(keep) - b.match_id.nunique())
b = b.merge(keep[["match_id", "comp_id", "league", "season", "match_date", "knock_out",
                  "win_team_id", "stage", "venue_id"]], on="match_id")
b = b.sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)

# ---------- delivery semantics ----------
b["extras_type"] = b.extras_type.fillna("None")
b["is_wide"] = b.extras_type.eq("wide")
b["is_nb"] = b.extras_type.isin(["Overstep", "other"])
b["legal"] = ~(b.is_wide | b.is_nb)
b["faced"] = ~b.is_wide                                   # batter faced it
b["bat_runs"] = b.runs.astype(int)
b["extras"] = b.extras1_runs.astype(int) + b.extras_2_runs.astype(int)
b["total_runs"] = b.bat_runs + b.extras
# runs charged to bowler: bat runs + wide/no-ball penalty runs (not byes/leg-byes)
b["bowler_runs"] = b.bat_runs + np.where(b.is_wide | b.is_nb, b.extras1_runs.astype(int), 0)
b["is_wicket"] = b.is_wicket.astype(str).str.lower().eq("true")
not_wkt = b.dismissal_type.isin(["Retire Out"])
b["wkt"] = b.is_wicket & ~not_wkt
bowler_modes = ["Caught", "Bowled", "LBW", "Stump", "Hit Wicket"]
b["bowler_wkt"] = b.wkt & b.dismissal_type.isin(bowler_modes)
b["striker_out"] = b.wkt & (b.dismissed_player_id.astype(float) == b.striker_id.astype(float))
b["is_four"] = b.is_four.astype(str).str.lower().eq("true")
b["is_six"] = b.is_six.astype(str).str.lower().eq("true")

# ---------- state BEFORE each ball ----------
g = b.groupby(["match_id", "innings"])
b["runs_before"] = g.total_runs.cumsum() - b.total_runs
b["wkts_before"] = g.wkt.cumsum() - b.wkt
b["legal_before"] = g.legal.cumsum() - b.legal
b["balls_rem"] = 120 - b.legal_before
b["wih"] = 10 - b.wkts_before                              # wickets in hand
b["over"] = b.legal_before // 6 + 1
b["phase"] = pd.cut(b.over, [0, 6, 15, 20], labels=["PP", "Middle", "Death"]).astype(str)

inn = g.agg(inn_runs=("total_runs", "sum"), bat_team=("batting_team_id", "first")).reset_index()
first = inn[inn.innings == 1][["match_id", "inn_runs"]].rename(columns={"inn_runs": "first_score"})
b = b.merge(first, on="match_id", how="left")
b["target"] = np.where(b.innings == 2, b.first_score + 1, np.nan)
b["need"] = b.target - b.runs_before
b["bat_won"] = (b.batting_team_id == b.win_team_id).astype(int)

# scoring environment ("par"): mean first-innings score of that league-season
par = b[b.innings == 1].groupby(["match_id"]).agg(league=("league", "first"),
       season=("season", "first"), fs=("first_score", "first")).groupby(["league", "season"]).fs.mean()
b["par"] = b.set_index(["league", "season"]).index.map(par).values

# recency weight: half-life 18 months, anchored at the last match in the data
end = b.match_date.max()
b["age_days"] = (end - b.match_date).dt.days
b["w_recency"] = 0.5 ** (b.age_days / 548)

b.to_pickle(f"{OUT}/balls_state.pkl")
pd.Series(excl).to_json(f"{OUT}/exclusions.json")
print(excl, "balls kept:", len(b), "matches:", b.match_id.nunique(), "end date:", end.date())
print(b.groupby("league").match_id.nunique())
