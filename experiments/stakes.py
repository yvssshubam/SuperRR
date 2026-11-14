"""Match stakes: how much does winning THIS match change a team's chance of its competition goal?
  IPL league     : P(top 4 | win) - P(top 4 | lose). Points table and net run rate are rebuilt before
                   every match from all earlier results; the rest of the season is simulated
                   (N_SIM runs). Remaining matches are 50/50; each simulated result's runs/overs are
                   drawn from that season's real completed matches, so NRR moves realistically and
                   teams level on points are separated by NRR.
  IPL playoffs   : Eliminator, Qualifier 2, Final = 1 (lose and you are out / title on the line);
                   Qualifier 1 = 0.5 (the loser gets a second chance).
  T20I bilateral : P(win series | win) - P(win series | lose), from the series score and matches
                   left (drawn series = half). One-off matches = 0.5.
  T20I tournaments: knockouts and finals = 1; group / league / Super 4 = 0.5 (not simulated).
Output: one row per (match, team): stakes in [0, 1] and multiplier M = 0.5 + stakes
scaled within competition type: M = clip(0.5 + 0.5 * stakes / mean stakes of that type, 0.5, 2);
eliminations / finals = 2, IPL Qualifier 1 = 1.5, tournament group games and one-offs = 1.
Usage (from the repo root): python -I experiments/stakes.py "<data_dir>" out
"""
import sys, itertools, numpy as np, pandas as pd
D, OUT = sys.argv[1], sys.argv[2]
N_SIM = 4000
rng = np.random.default_rng(2026)
m = pd.read_csv(f"{D}/matches.csv").merge(pd.read_csv(f"{D}/competitions.csv"), on="comp_id")
m["match_date"] = pd.to_datetime(m.match_date)
m = m.sort_values(["match_date", "match_number", "match_id"])
bb = pd.read_csv(f"{D}/ball_by_ball.csv", low_memory=False,
                 usecols=["match_id", "innings", "batting_team_id", "runs", "extras1_runs", "extras_2_runs", "extras_type", "is_wicket", "dismissal_type"])
bb = bb[bb.innings.isin([1, 2])]
bb["legal"] = ~bb.extras_type.isin(["wide", "Overstep", "other"])
bb["tot"] = bb.runs + bb.extras1_runs + bb.extras_2_runs
bb["w"] = bb.is_wicket.astype(str).str.lower().eq("true") & ~bb.dismissal_type.eq("Retire Out")
inn = bb.groupby(["match_id", "innings"]).agg(team=("batting_team_id", "first"), runs=("tot", "sum"), balls=("legal", "sum"), wk=("w", "sum")).reset_index()
inn.loc[inn.wk >= 10, "balls"] = 120                          # NRR rule: all out counts the full 20 overs
no_result = m.result.str.contains("No Result|Abandon", case=False, na=True) | m.win_team_id.isna()
rows = []

# ======================= IPL =======================
ipl = m[m.comp_name.str.startswith("IPL")]
for season, S in ipl.groupby("season"):
    L = S[S.stage == "League"].copy()
    teams = sorted(set(L.home_team_id) | set(L.away_team_id)); ti = {t: i for i, t in enumerate(teams)}; T = len(teams)
    # real innings figures for NRR (runs for, balls faced; per team per match)
    I = inn[inn.match_id.isin(L.match_id)]
    # pool of completed results to sample margins: (winner runs, winner balls, loser runs, loser balls)
    pool = []
    for mid, g in I.groupby("match_id"):
        if len(g) < 2: continue
        w = L.loc[L.match_id == mid, "win_team_id"]
        if w.isna().all(): continue
        wt = int(w.iloc[0]); gw, gl = g[g.team == wt], g[g.team != wt]
        if len(gw) and len(gl): pool.append((gw.runs.iloc[0], gw.balls.iloc[0], gl.runs.iloc[0], gl.balls.iloc[0]))
    pool = np.array(pool, float)
    pts = np.zeros(T); rf = np.zeros(T); bf = np.zeros(T); ra = np.zeros(T); ba = np.zeros(T)
    Lrows = list(L.itertuples())
    for k, r in enumerate(Lrows):
        a, b_ = ti[r.home_team_id], ti[r.away_team_id]
        rem = Lrows[k + 1:]
        ra_i = np.array([ti[x.home_team_id] for x in rem], int); rb_i = np.array([ti[x.away_team_id] for x in rem], int)
        R = len(rem)
        def qual_prob(force_winner):
            P = np.tile(pts, (N_SIM, 1)); RF = np.tile(rf, (N_SIM, 1)); BF = np.tile(bf, (N_SIM, 1)); RA = np.tile(ra, (N_SIM, 1)); BA = np.tile(ba, (N_SIM, 1))
            ar = np.arange(N_SIM)
            for (x, y, fw) in [(a, b_, force_winner)]:
                wv, lv = (x, y) if fw == x else (y, x)
                s = pool[rng.integers(0, len(pool), N_SIM)]
                P[:, wv] += 2; RF[:, wv] += s[:, 0]; BF[:, wv] += s[:, 1]; RA[:, wv] += s[:, 2]; BA[:, wv] += s[:, 3]
                RF[:, lv] += s[:, 2]; BF[:, lv] += s[:, 3]; RA[:, lv] += s[:, 0]; BA[:, lv] += s[:, 1]
            if R:
                hw = rng.random((N_SIM, R)) < 0.5
                W = np.where(hw, ra_i, rb_i); Lo = np.where(hw, rb_i, ra_i)
                s = pool[rng.integers(0, len(pool), (N_SIM, R))]
                for j in range(R):
                    wv, lv = W[:, j], Lo[:, j]
                    P[ar, wv] += 2; RF[ar, wv] += s[:, j, 0]; BF[ar, wv] += s[:, j, 1]; RA[ar, wv] += s[:, j, 2]; BA[ar, wv] += s[:, j, 3]
                    RF[ar, lv] += s[:, j, 2]; BF[ar, lv] += s[:, j, 3]; RA[ar, lv] += s[:, j, 0]; BA[ar, lv] += s[:, j, 1]
            nrr = RF / np.maximum(BF, 1) * 6 - RA / np.maximum(BA, 1) * 6
            key = P * 1000 + np.clip(nrr, -9.99, 9.99)                     # points first, NRR breaks ties
            rank = (-key).argsort(1).argsort(1)
            return (rank < 4).mean(0)
        qa, qb = qual_prob(a), qual_prob(b_)                             # a wins / b wins
        sa, sb = qa[a] - qb[a], qb[b_] - qa[b_]
        pre = None
        for t_, s_, p_ in ((r.home_team_id, sa, qa[a] * 0.5 + qb[a] * 0.5), (r.away_team_id, sb, qa[b_] * 0.5 + qb[b_] * 0.5)):
            rows.append(dict(match_id=r.match_id, team_id=t_, comp="IPL league", stakes=float(np.clip(s_, 0, 1)), p_top4_before=float(p_)))
        # apply the real result
        if not no_result.loc[r.Index]:
            g = I[I.match_id == r.match_id]
            for gg in g.itertuples():
                t = ti.get(int(gg.team)); o = b_ if t == a else a
                if t is None: continue
                rf[t] += gg.runs; bf[t] += gg.balls; ra[o] += gg.runs; ba[o] += gg.balls
            if r.win_team_id == r.win_team_id: pts[ti[int(r.win_team_id)]] += 2
        else:
            pts[a] += 1; pts[b_] += 1
    for r in S[S.stage != "League"].itertuples():
        st = 0.5 if (r.stage == "Qualifier" and r.match_number == S[S.stage == "Qualifier"].match_number.min()) else 1.0
        for t_ in (r.home_team_id, r.away_team_id):
            rows.append(dict(match_id=r.match_id, team_id=t_, comp="IPL playoff", stakes=st, p_top4_before=np.nan))

# ======================= T20I =======================
t20 = m[m.match_format == "T20I"]
for cid, C in t20.groupby("comp_id"):
    teams = sorted(set(C.home_team_id) | set(C.away_team_id))
    if len(teams) == 2:
        n = len(C)
        if n == 1:
            for t_ in teams: rows.append(dict(match_id=C.match_id.iloc[0], team_id=t_, comp="T20I one-off", stakes=0.5))
            continue
        wins = {t: 0 for t in teams}
        for k, r in enumerate(C.itertuples()):
            left = n - k - 1
            def series_p(wa, wb):                       # P(team A wins series) with 'left' 50/50 games
                tot = 0.0
                for x in range(left + 1):
                    from math import comb
                    p = comb(left, x) / 2 ** left
                    fa, fb = wa + x, wb + (left - x)
                    tot += p * (1.0 if fa > fb else 0.5 if fa == fb else 0.0)
                return tot
            A, B = teams
            for me, op in ((A, B), (B, A)):
                pw = series_p(wins[me] + 1, wins[op]); pl = series_p(wins[me], wins[op] + 1)
                rows.append(dict(match_id=r.match_id, team_id=me, comp="T20I bilateral", stakes=float(pw - pl)))
            if not no_result.loc[r.Index] and r.win_team_id in wins: wins[int(r.win_team_id)] += 1
    else:
        for r in C.itertuples():
            ko = (r.stage in ("Final", "Semi Final")) or (r.knock_out == 1)
            for t_ in (r.home_team_id, r.away_team_id):
                rows.append(dict(match_id=r.match_id, team_id=t_, comp="T20I tournament", stakes=1.0 if ko else 0.5))

st = pd.DataFrame(rows)
# Multiplier, scaled within competition type so each type averages ~1 (bilateral series hinge on every
# game, so their raw stakes run higher than IPL league games): dead rubber 0.5x, biggest games 2x.
mean_s = st[st.comp.isin(["IPL league", "T20I bilateral"])].groupby("comp").stakes.mean()
def mult(r):
    if r.comp in mean_s.index: return float(np.clip(0.5 + 0.5 * r.stakes / mean_s[r.comp], 0.5, 2.0))
    if r.comp == "IPL playoff": return 1.5 if r.stakes < 1 else 2.0
    if r.comp == "T20I tournament": return 2.0 if r.stakes >= 1 else 1.0
    return 1.0
st["M"] = st.apply(mult, axis=1)
st.to_csv(f"{OUT}/match_stakes.csv", index=False)
print(st.groupby("comp").stakes.describe().round(3).to_string())
print(st.groupby("comp").M.describe().round(2).to_string())
print("\ndead rubbers (stakes < 0.05):", round(100 * (st.stakes < 0.05).mean(), 1), "% of team-matches")
x = st[st.comp == "IPL league"].merge(m[["match_id", "season", "match_number"]], on="match_id")
x["phase"] = pd.cut(x.match_number, [0, 20, 40, 56, 63, 71], labels=["1-20", "21-40", "41-56", "57-63", "64-70"])
print(x.groupby("phase", observed=True).stakes.agg(["mean", lambda s: (s < 0.05).mean(), lambda s: (s > 0.5).mean()]).round(3).set_axis(["mean stakes", "share dead", "share must-win(>0.5)"], axis=1))
