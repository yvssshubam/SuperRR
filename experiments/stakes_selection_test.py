"""Test (A) match stakes and (B) selection pressure.
(A) Stakes-weighted pressure: ball leverage x the batting (or bowling) team's match-stakes multiplier,
    replacing the flat 1.2x knockout boost; pressure = top 25% within each innings, as before.
    1. validity: how much pressure comes from dead rubbers, before vs after
    2. league-wide: do players perform differently in high-stakes matches?
    3. player repeatability of the high-vs-low stakes difference
    4. held-out self-consistency on 10 random match splits (does the new definition give ratings that
       predict the other half at least as well?), and top-10 changes.
(B) Selection pressure (competition for a place), per player-match:
    recalled  - missed his team's previous match in this competition, plays now
    bubble    - has played < 60% of his team's matches so far in this competition (>= 3 played by team)
    early     - one of his first 5 matches for this team (from mid-2022, to avoid players already
                established before the data starts)
    impact_in - came on as an Impact Player substitute
    Tested like the psychological factors: league effect, repeatability, held-out prediction.
Usage (from the repo root, after experiments/stakes.py): python -I experiments/stakes_selection_test.py out "<data_dir>" out/match_stakes.csv
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT, D, STK = sys.argv[1], sys.argv[2], sys.argv[3]
RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py")
sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
rng = np.random.default_rng(9)
pd.set_option("display.width", 220)

b = pd.read_pickle(f"{OUT}/balls_scored.pkl"); b["recent"] = b.age_days <= 365; b["w"] = b.w_recency
st = pd.read_csv(STK)
Mk = st.set_index(["match_id", "team_id"])
b["M_bat"] = Mk.M.reindex(pd.MultiIndex.from_arrays([b.match_id, b.batting_team_id])).fillna(1.0).values
b["M_bowl"] = Mk.M.reindex(pd.MultiIndex.from_arrays([b.match_id, b.bowling_team_id])).fillna(1.0).values
b["S_bat"] = Mk.stakes.reindex(pd.MultiIndex.from_arrays([b.match_id, b.batting_team_id])).values
b["S_bowl"] = Mk.stakes.reindex(pd.MultiIndex.from_arrays([b.match_id, b.bowling_team_id])).values
li0 = b.li / np.where(b.knock_out == 1, 1.2, 1.0)                     # remove the flat knockout boost
for side in ("bat", "bowl"):
    x = li0 * b["M_" + side]
    b["press_" + side] = x.groupby(b.innings).rank(pct=True) >= 0.75
b["press_old"] = b.pressure

def with_def(df, role, kind):
    col = {"old": "press_old", "new": "press_" + role}[kind]
    return df.assign(pressure=df[col])

# ---------------- A1: validity ----------------
print("A1  Where does pressure come from?")
for kind, col_b, col_w in (("current", "press_old", "press_old"), ("stakes-weighted", "press_bat", "press_bowl")):
    pb = b[b[col_b]]; pw = b[b[col_w]]
    print(f"  {kind:16s} share of batters' pressure balls in dead rubbers (stakes<0.05): {100 * (pb.S_bat < 0.05).mean():.1f}%  "
          f"| in must-win/elimination (stakes>=0.5, IPL): {100 * ((pb.S_bat >= 0.5) & (pb.league == 'IPL')).mean():.1f}%  "
          f"| mean multiplier {pb.M_bat.mean():.2f}")

# ---------------- A2: league-wide effect of stakes ----------------
CTX = r.CTX
def resid(df, role):
    d = df[df.faced] if role == "bat" else df[df.legal | df.is_wide | df.is_nb]
    val = "rv_bat" if role == "bat" else "rv_bowl"
    return d.assign(res=d[val] - d.groupby(CTX)[val].transform("mean"))
def cluster_diff(d, flag, val="res", B=300):
    s = d.groupby(["match_id", flag])[val].agg(["sum", "count"]).unstack(fill_value=0)
    S1, N1, S0, N0 = s["sum"][True].values, s["count"][True].values, s["sum"][False].values, s["count"][False].values
    est = 100 * (S1.sum() / N1.sum() - S0.sum() / N0.sum()); k = len(S1)
    bs = [100 * (S1[i].sum() / max(N1[i].sum(), 1) - S0[i].sum() / N0[i].sum()) for i in (rng.integers(0, k, k) for _ in range(B))]
    return est, float(np.std(bs))
print("\nA2  Do players perform differently in high-stakes matches? (runs per 100 balls vs same context)")
for role in ("bat", "bowl"):
    d = resid(b, role); side = "M_" + role
    d["high"] = d[side] >= 1.5; d["low"] = d[side] <= 0.6
    for nm, flag in (("high stakes (M>=1.5) vs rest", "high"), ("dead rubber (M<=0.6) vs rest", "low")):
        for scope, dd in (("all balls", d), ("pressure balls", d[d.pressure])):
            e, se = cluster_diff(dd, flag)
            print(f"  {role:4s} {nm:30s} {scope:15s} share {100 * dd[flag].mean():4.1f}%  effect {e:+6.2f} (se {se:.2f}, t {e / se:+.1f})")

# ---------------- A3: repeatability of high-vs-low stakes delta ----------------
print("\nA3  Do some players handle high stakes repeatably better? (split-half, players with >=60 high-stakes balls per half)")
for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
    d = resid(b, role); d["hi"] = d["M_" + role] >= 1.2
    out = []
    for h in (0, 1):
        x = d[(d.match_id % 2) == h].groupby([pid, "hi"]).res.agg(["mean", "size"]).unstack()
        ok = (x["size"][True] >= 60) & (x["size"][False] >= 150)
        out.append((x["mean"][True] - x["mean"][False])[ok])
    j = pd.concat(out, axis=1, join="inner").dropna(); rr = j.iloc[:, 0].corr(j.iloc[:, 1])
    print(f"  {role}: players {len(j)}, split-half r = {rr:.3f}")

# ---------------- A4: held-out self-consistency, 10 random splits ----------------
def target(half, role):
    d = resid(half, role); pid = "striker_id" if role == "bat" else "bowler_id"
    return d[d.pressure].groupby(pid).res.mean()
print("\nA4  Held-out prediction on 10 random match splits (rating on half A predicts pressure value in half B)")
mids = b.match_id.unique(); res4 = []
for seed in range(10):
    half_of = pd.Series(np.random.default_rng(300 + seed).integers(0, 2, len(mids)), index=mids)
    for role in ("bat", "bowl"):
        row = dict(seed=seed, role=role)
        for kind in ("old", "new"):
            cs, cross = [], []
            for a, c in ((0, 1), (1, 0)):
                HA = with_def(b[b.match_id.map(half_of) == a], role, kind); HC = with_def(b[b.match_id.map(half_of) == c], role, kind)
                HCold = with_def(b[b.match_id.map(half_of) == c], role, "old")
                TA, TC = r.player_table(HA, role)[0], r.player_table(HC, role)[0]
                for tgt, store in ((target(HC, role), cs), (target(HCold, role), cross)):
                    f = TA[["press_skill", "pb"]].join(tgt.rename("y"), how="inner").join(TC[["pb"]].rename(columns={"pb": "pbB"}))
                    f = f[(f.pb >= 50) & (f.pbB >= 50)]; store.append(f.press_skill.corr(f.y))
            row[f"{kind}_own_target"] = float(np.mean(cs)); row[f"{kind}_old_target"] = float(np.mean(cross))
        res4.append(row)
r4 = pd.DataFrame(res4)
r4["gain_own"] = r4.new_own_target - r4.old_own_target; r4["gain_on_old_target"] = r4.new_old_target - r4.old_old_target
print(r4.round(3).to_string(index=False))
print(r4.groupby("role")[["gain_own", "gain_on_old_target"]].agg(["mean", lambda s: int((s > 0).sum())]).round(3))

# ---------------- B: selection pressure ----------------
m = pd.read_csv(f"{D}/matches.csv"); m["match_date"] = pd.to_datetime(m.match_date)
pe = pd.read_csv(f"{D}/playing_eleven.csv")
pe["played"] = pe.is_played.astype(str).str.lower().isin(["true", "1"])
pe = pe.merge(m[["match_id", "comp_id", "match_date", "match_number"]], on="match_id").sort_values(["match_date", "match_number", "match_id"])
P = pe[pe.played].copy()
team_seq = P.groupby(["comp_id", "team_id"]).match_id.apply(lambda s: list(dict.fromkeys(s))).to_dict()
played_set = set(zip(P.match_id, P.team_id, P.player_id))
flags = []
for (cid, tid), seq in team_seq.items():
    idx = {mid: i for i, mid in enumerate(seq)}
    g = P[(P.comp_id == cid) & (P.team_id == tid)]
    for rr in g.itertuples():
        i = idx[rr.match_id]
        prev_played = sum((seq[j], tid, rr.player_id) in played_set for j in range(i))
        recalled = i >= 1 and prev_played >= 1 and (seq[i - 1], tid, rr.player_id) not in played_set
        bubble = i >= 3 and prev_played / i < 0.6
        flags.append(dict(match_id=rr.match_id, player_id=rr.player_id, recalled=recalled, bubble=bubble,
                          impact_in=bool(pe.loc[rr.Index, "is_impact"] == 1) if "is_impact" in pe else False))
F = pd.DataFrame(flags)
# early with team: first 5 appearances for that team (team ids are per competition, so use team name)
tn = pd.concat([m[["home_team_id", "home_team"]].set_axis(["id", "n"], axis=1), m[["away_team_id", "away_team"]].set_axis(["id", "n"], axis=1)]).drop_duplicates("id").set_index("id").n
P["team_name"] = P.team_id.map(tn)
P["app_no"] = P.groupby(["player_id", "team_name"]).cumcount()
first_date = P.groupby(["player_id", "team_name"]).match_date.transform("min")
P["early"] = (P.app_no < 5) & (first_date >= "2022-07-01")
F = F.merge(P[["match_id", "player_id", "early"]], on=["match_id", "player_id"], how="left")
F["selection"] = F.recalled | F.bubble | F.early
print("\nB   Selection-pressure flags: share of player-matches", F[["recalled", "bubble", "early", "impact_in", "selection"]].mean().round(3).to_dict())
SEL = ["recalled", "bubble", "early", "impact_in", "selection"]
key = F.drop_duplicates(["match_id", "player_id"]).set_index(["match_id", "player_id"])
rows1, rows2 = [], []
for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
    d = resid(b, role)
    kk = pd.MultiIndex.from_arrays([d.match_id, d[pid]])
    for fl in SEL: d[fl] = key[fl].reindex(kk).fillna(False).astype(bool).values
    for fl in SEL:
        if d[fl].sum() < 500: continue
        e, se = cluster_diff(d, fl); ep, sep = cluster_diff(d[d.pressure], fl)
        # repeatability
        hh = []
        for h in (0, 1):
            x = d[(d.match_id % 2) == h].groupby([pid, fl]).res.agg(["mean", "size"]).unstack()
            ok = (x["size"][True] >= 30) & (x["size"][False] >= 100); hh.append((x["mean"][True] - x["mean"][False])[ok])
        j = pd.concat(hh, axis=1, join="inner").dropna(); rr_ = j.iloc[:, 0].corr(j.iloc[:, 1]) if len(j) > 10 else np.nan
        rows1.append(dict(role=role, flag=fl, share=round(100 * d[fl].mean(), 1), effect_all=round(e, 2), t_all=round(e / se, 1),
                          effect_pressure=round(ep, 2), t_pressure=round(ep / sep, 1), players=len(j), split_half_r=round(rr_, 3)))
print(pd.DataFrame(rows1).to_string(index=False))
# held-out: selection-pressure resilience component
def sel_component(d, role):
    pid = "striker_id" if role == "bat" else "bowler_id"
    g = d.groupby([pid, "selection"]).res.agg(["mean", "size", "var"]).unstack()
    delta = g["mean"][True] - g["mean"][False]; n = g["size"][True]; sig2 = np.nanmean(g["var"][True])
    big = n >= 30; tau2 = max(np.nanvar(delta[big]) - np.nanmean(sig2 / n[big]), 1e-8)
    return (delta * n / (n + sig2 / tau2)).fillna(0)
z = lambda s: (s - s.mean()) / s.std()
for role, pid in (("bat", "striker_id"), ("bowl", "bowler_id")):
    gains = {lam: [] for lam in (0.1, 0.25, 0.5)}
    for seed in range(10):
        half_of = pd.Series(np.random.default_rng(500 + seed).integers(0, 2, len(mids)), index=mids)
        cors = {0: [], **{lam: [] for lam in gains}}
        for a, c in ((0, 1), (1, 0)):
            HA, HC = b[b.match_id.map(half_of) == a], b[b.match_id.map(half_of) == c]
            TA, TC = r.player_table(HA, role)[0], r.player_table(HC, role)[0]
            dA = resid(HA, role); kk = pd.MultiIndex.from_arrays([dA.match_id, dA[pid]])
            dA["selection"] = key["selection"].reindex(kk).fillna(False).astype(bool).values
            comp = sel_component(dA, role)
            f = TA[["press_skill", "pb"]].join(comp.rename("sel")).join(target(HC, role).rename("y"), how="inner").join(TC[["pb"]].rename(columns={"pb": "pbB"}))
            f = f[(f.pb >= 50) & (f.pbB >= 50)].copy(); f["sel"] = f.sel.fillna(0)
            cors[0].append(z(f.press_skill).corr(f.y))
            for lam in gains: cors[lam].append((z(f.press_skill) + lam * z(f.sel)).corr(f.y))
        for lam in gains: gains[lam].append(np.mean(cors[lam]) - np.mean(cors[0]))
    print(f"  {role}: held-out gain from selection-pressure component, 10 splits:",
          {lam: (round(float(np.mean(v)), 3), int(sum(x > 0 for x in v))) for lam, v in gains.items()})
F.to_csv(f"{OUT}/selection_flags.csv", index=False); r4.to_csv(f"{OUT}/stakes_splits.csv", index=False)
pd.DataFrame(rows1).to_csv(f"{OUT}/selection_test.csv", index=False)
