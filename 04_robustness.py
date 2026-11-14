"""Step 4: robustness of the submitted (Current Pressure Readiness) top-10 lists to modelling choices,
and pressure-definition validation.
Usage: python -I 04_robustness.py <out_dir>
"""
import sys, json, importlib.util, numpy as np, pandas as pd
OUT = sys.argv[1]
spec = importlib.util.spec_from_file_location("r", __file__.replace("04_robustness.py", "03_ratings.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

b = pd.read_pickle(f"{OUT}/balls_scored.pkl")
b["recent"] = b.age_days <= 365
main = {role: pd.read_csv(f"{OUT}/{role}_ratings.csv", index_col=0) for role in ["bat", "bowl"]}
top = {role: list(main[role].index[:10]) for role in main}
elig = {role: list(main[role].index) for role in main}
EXEC = pd.read_csv(f"{OUT}/bowl_execution.csv", index_col=0)[["execution"]]

EQUAL = None   # equal weights are set per role below
RW = lambda d, a0: r.rating_weights(d, a0)
scen = {
    "Pressure = top 20% leverage":  dict(pressure=lambda d: d.li_pct >= 0.80),
    "Pressure = top 30% leverage":  dict(pressure=lambda d: d.li_pct >= 0.70),
    "Pressure = top 10% (extreme)": dict(pressure=lambda d: d.li_pct >= 0.90),
    "Conventional RRR/wickets index": dict(pressure=lambda d: d.alt_pressure),
    "Career Ability (all matches equal)": dict(w=lambda d: RW(d, 1.0)),
    "Older matches weight 0.25":    dict(w=lambda d: RW(d, 0.25)),
    "Older matches weight 0.75":    dict(w=lambda d: RW(d, 0.75)),
    "Last 12 months only":          dict(w=lambda d: RW(d, 0.0)),
    "Previous recency (18-month half-life)": dict(w=lambda d: 0.5 ** (d.age_days / 548)),
    "Equal component weights":      dict(weights=EQUAL),
    "Pressure rating only":         dict(weights={"press_skill": 1.0}),
    "Without bowler execution component": dict(weights_bowl={k: v / (1 - r.WEIGHTS["bowl"]["execution"])
                                                             for k, v in r.WEIGHTS["bowl"].items() if k != "execution"}),
    "IPL only":                     dict(filt=lambda d: d.league == "IPL"),
    "T20I only":                    dict(filt=lambda d: d.league == "T20I"),
}
rows = []
for name, s in scen.items():
    d = b.copy()
    if "filt" in s: d = d[s["filt"](d)]
    if "pressure" in s: d["pressure"] = s["pressure"](d)
    d["w"] = s["w"](d) if "w" in s else RW(d, r.READY_OLD_WEIGHT)
    for role in ["bat", "bowl"]:
        t, _, _ = r.player_table(d, role)
        if role == "bowl": t = t.join(EXEC)
        wts = s.get("weights", s.get("weights_bowl") if role == "bowl" and "weights_bowl" in s else r.WEIGHTS[role])
        if wts is None: wts = {k: 1 / len(r.WEIGHTS[role]) for k in r.WEIGHTS[role]}
        e = r.composite(t, wts, elig[role])
        e = e[e.pb >= 30] if "filt" in s else e
        new_top = list(e.index[:10])
        common = main[role].index.intersection(e.index)
        rho = main[role].loc[common, "score"].rank().corr(e.loc[common, "score"].rank())
        rows.append(dict(scenario=name, role=role, overlap_top10=len(set(new_top) & set(top[role])),
                         spearman=round(rho, 3),
                         main_top10_median_rank=float(pd.Series(range(1, len(e) + 1), index=e.index).reindex(top[role]).median())))
rob = pd.DataFrame(rows)
rob.to_csv(f"{OUT}/robustness.csv", index=False)
print(rob.pivot(index="scenario", columns="role", values=["overlap_top10", "spearman"]))

# ---------- does Leverage pick out the matches/moments that decide games? ----------
m = b.groupby(["match_id"]).agg(first=("first_score", "first"), bat2=("batting_team_id", "last"),
                                 win=("win_team_id", "first"))
last2 = b[b.innings == 2].groupby("match_id").agg(r2=("total_runs", "sum"), wl=("wkt", "sum"), bl=("legal", "sum"))
m = m.join(last2)
m["chase_won"] = m.bat2 == m.win
m["close"] = np.where(m.chase_won, (m.bl >= 114) | (m.wl >= 7), (m["first"] - m.r2) <= 12)
press_share = b.groupby("match_id").li.apply(lambda s: (s >= b.li.quantile(0.75)).mean())
val = dict(pressure_share_close=round(float(press_share[m.close[m.close].index.intersection(press_share.index)].mean()), 3),
           pressure_share_one_sided=round(float(press_share[m.close[~m.close].index.intersection(press_share.index)].mean()), 3),
           n_close=int(m.close.sum()), n_one_sided=int((~m.close).sum()))
# league-wide behaviour under pressure vs not (batting)
f = b[b.faced]
beh = f.groupby("pressure").agg(SR=("bat_runs", lambda x: 100 * x.mean()), out_pct=("striker_out", lambda x: 100 * x.mean()),
                                dot_pct=("bat_runs", lambda x: 100 * (x == 0).mean()),
                                abs_wpa=("wpa_bat", lambda x: 100 * x.abs().mean())).round(2)
beh_alt = f.groupby("alt_pressure").agg(abs_wpa=("wpa_bat", lambda x: 100 * x.abs().mean())).round(2)
# mean WP when flagged: conventional index flags hopeless chases, leverage does not
lost_cause = b[b.innings == 2]
lc = dict(leverage_share_wp_below_10=round(float((lost_cause[lost_cause.pressure].wp_before < 0.10).mean()), 3),
          conventional_share_wp_below_10=round(float((lost_cause[lost_cause.alt_pressure].wp_before < 0.10).mean()), 3))
val.update(lc)
json.dump(dict(validation=val, behaviour=beh.reset_index().to_dict("records"),
               abs_wpa_conventional=beh_alt.reset_index().to_dict("records")), open(f"{OUT}/validation.json", "w"), indent=1, default=str)
print(val); print(beh); print(beh_alt)
