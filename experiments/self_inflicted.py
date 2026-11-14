"""Self-inflicted pressure diagnostic: do batters look clutch partly because their own slow starts
created the pressure they later bat in?
For each batter-innings with pressure balls:
  pre  = his balls in that innings BEFORE his first pressure ball (where he may have built the pressure)
  post = his pressure balls
  self_wpa = win probability his own pre-pressure balls cost his team (sum of WPA, negative = cost)
Per batter: share of pressure balls that came after he had himself cost his team > 3 win-% points
earlier in the innings ('self-inflicted'), and an innings-netted pressure value that charges the
pre-pressure balls of the same innings to his pressure ledger.
Usage (from the repo root): python -I experiments/self_inflicted.py out
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]; RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py"); sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
b = pd.read_pickle(f"{OUT}/balls_scored.pkl"); b["recent"] = b.age_days <= 365; b["w"] = r.rating_weights(b, r.READY_OLD_WEIGHT)
t, _, d = r.player_table(b, "bat")                       # d has 'adj' = context+matchup+opposition-adjusted value
d = d.sort_values(["match_id", "innings", "innings_ball_num"])
g = d.groupby(["match_id", "innings", "striker_id"])
d["first_p"] = g.pressure.transform(lambda s: s.values.argmax() if s.any() else -1)
d["k"] = g.cumcount()
d["pre"] = (d.first_p >= 0) & (d.k < d.first_p)
inn = d[d.first_p >= 0].groupby(["match_id", "innings", "striker_id"]).agg(
    pre_balls=("pre", "sum"), pre_runs=("bat_runs", lambda s: 0), pre_adj=("adj", lambda s: 0))
pre = d[d.pre].groupby(["match_id", "innings", "striker_id"]).agg(pre_balls=("adj", "size"), pre_adj=("adj", "sum"), pre_runs=("bat_runs", "sum"),
                                                                    pre_dots=("bat_runs", lambda s: (s == 0).sum()), self_wpa=("wpa_bat", "sum"))
pp = d[d.pressure].groupby(["match_id", "innings", "striker_id"]).agg(p_balls=("adj", "size"), p_adj=("adj", "sum"), p_runs=("bat_runs", "sum"))
I = pp.join(pre, how="left").fillna(0)
I["self_inflicted"] = I.self_wpa < -0.03                  # he personally cost his side >3 win-% points before the pressure began
# league-level: within innings, do worse pre-pressure starts go with better pressure batting (catch-up)?
x = I[I.pre_balls >= 6]
print("League: innings with >=6 pre-pressure balls:", len(x),
      "| corr(pre value per ball, pressure value per ball) =", round((x.pre_adj / x.pre_balls).corr(x.p_adj / x.p_balls), 3))
print("Share of all batters' pressure balls that were self-inflicted:", round(100 * I.loc[I.self_inflicted, "p_balls"].sum() / I.p_balls.sum(), 1), "%")
S = I.groupby(level="striker_id").apply(lambda s: pd.Series({
    "press_balls": s.p_balls.sum(),
    "self_inflicted_share": s.loc[s.self_inflicted, "p_balls"].sum() / s.p_balls.sum(),
    "pre_SR": 100 * s.pre_runs.sum() / max(s.pre_balls.sum(), 1),
    "pre_dot_pct": 100 * s.pre_dots.sum() / max(s.pre_balls.sum(), 1),
    "press_SR": 100 * s.p_runs.sum() / s.p_balls.sum(),
    "press_value": 100 * s.p_adj.sum() / s.p_balls.sum(),
    "netted_value": 100 * (s.p_adj.sum() + s.pre_adj.sum()) / (s.p_balls.sum() + s.pre_balls.sum()),
}), include_groups=False)
S0 = S
for stem, label in [("", "Current Pressure Readiness"), ("_career", "Career Pressure Ability")]:
    fin = pd.read_csv(f"{OUT}/bat{stem}_final.csv", index_col=0)
    S = S0.reindex(fin.index).copy(); S.insert(0, "name", fin.name); S.insert(1, "rank", range(1, len(S) + 1))
    print(f"\n=== {label} ===")
    print("League (eligible batters) median self-inflicted share:", round(100 * S.self_inflicted_share.median(), 1), "%")
    pd.set_option("display.width", 200)
    print(S.head(14).round(2).to_string())
    print("Spearman(pressure value, innings-netted value) among eligible:", round(S.press_value.corr(S.netted_value, method="spearman"), 3))
    S.to_csv(f"{OUT}/self_inflicted{stem}.csv")
