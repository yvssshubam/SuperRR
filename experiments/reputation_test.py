"""Does in-data 'reputation' improve the pressure rating?
Signals (all from the supplied data, computed only from the half of matches used to build the rating):
  potm      player-of-the-match awards per match played (both roles)
  captain   share of matches played as captain (both roles)
  playoff   share of his teams' playoff/knockout matches in which he was picked (both roles)
  death     share of his overs bowled at the death, overs 16-20 (bowlers: captain's trust)
  order     share of innings batting in the top 4 (batters: promoted / trusted with more balls)
Test: rating built on one half of matches predicts actual pressure value in the other half
      (as in the README section 9.3). Paired player bootstrap for the change in correlation.
Usage (after the main pipeline, from the repo root): python -I experiments/reputation_test.py out "<data_dir>"
"""
import sys, os, importlib.util, numpy as np, pandas as pd
OUT, D = sys.argv[1], sys.argv[2]
RMOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "03_ratings.py")
sys.argv = [sys.argv[0], OUT]
spec = importlib.util.spec_from_file_location("r", RMOD); r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
rng = np.random.default_rng(11)

b = pd.read_pickle(f"{OUT}/balls_scored.pkl"); b["recent"] = b.age_days <= 365; b["w"] = b.w_recency
m = pd.read_csv(f"{D}/matches.csv").set_index("match_id")
pe = pd.read_csv(f"{D}/playing_eleven.csv")
pe = pe[pe.match_id.isin(b.match_id.unique()) & pe.is_played.astype(str).str.lower().isin(["true", "1"])].copy()
pe["captain"] = pe.is_captain.astype(str).str.lower().isin(["true", "1"])
pe["ko"] = pe.match_id.map(m.stage).isin({"Final", "Qualifier", "Eliminator", "Semi Final", "Super 4"}) | (pe.match_id.map(m.knock_out) == 1)
pe["comp"] = pe.match_id.map(m.comp_id)
potm = m.man_of_the_match

def beta_shrink(k, n, prior_n=10):
    p0 = k.sum() / n.sum()
    return (k + prior_n * p0) / (n + prior_n)

def signals(half_ids, role):
    p = pe[pe.match_id.isin(half_ids)]
    g = p.groupby("player_id")
    n = g.size()
    rec = p[p.match_id.map(potm).fillna(0) != 0]                          # matches with an award recorded
    s = pd.DataFrame(index=n.index)
    s["potm"] = beta_shrink(rec.assign(won=rec.player_id == rec.match_id.map(potm)).groupby("player_id").won.sum().reindex(n.index).fillna(0),
                            rec.groupby("player_id").size().reindex(n.index).fillna(0))
    s["captain"] = beta_shrink(g.captain.sum(), n)
    # playoff selection: picked in team's KO matches, in competitions where he played for that team
    ko_team = p[p.ko].groupby(["comp", "team_id"]).match_id.nunique().rename("team_ko")
    mem = p.groupby(["player_id", "comp", "team_id"]).size().reset_index()[["player_id", "comp", "team_id"]]
    mem = mem.join(ko_team, on=["comp", "team_id"]).fillna({"team_ko": 0})
    picked = p[p.ko].groupby(["player_id", "comp", "team_id"]).match_id.nunique().rename("picked")
    mem = mem.join(picked, on=["player_id", "comp", "team_id"]).fillna({"picked": 0})
    t = mem.groupby("player_id")[["picked", "team_ko"]].sum()
    s["playoff"] = beta_shrink(t.picked.reindex(n.index).fillna(0), t.team_ko.reindex(n.index).fillna(0), prior_n=5)
    h = b[b.match_id.isin(half_ids)]
    if role == "bowl":
        ov = h[h.legal].groupby(["bowler_id", "match_id", "overid"]).over.first().reset_index()
        dd = ov.assign(death=ov.over >= 16).groupby("bowler_id").death.agg(["sum", "size"])
        s["death"] = beta_shrink(dd["sum"], dd["size"], prior_n=10).reindex(n.index)
    else:
        io = h[h.faced].groupby(["striker_id", "match_id"]).batting_order.first().reset_index()
        tt = io.assign(top=io.batting_order <= 4).groupby("striker_id").top.agg(["sum", "size"])
        s["order"] = beta_shrink(tt["sum"], tt["size"], prior_n=5).reindex(n.index)
    return s

def target(half, role):
    pid, val = ("striker_id", "rv_bat") if role == "bat" else ("bowler_id", "rv_bowl")
    d = half[half.faced] if role == "bat" else half[half.legal | half.is_wide | half.is_nb]
    d = d.assign(res=d[val] - d.groupby(r.CTX)[val].transform("mean"))
    return d[d.pressure].groupby(pid).res.mean()

z = lambda s: (s - s.mean()) / s.std()
rows, boot_rows = [], []
for role in ("bat", "bowl"):
    sig_names = ["potm", "captain", "playoff", "death" if role == "bowl" else "order"]
    frames = []
    for a, c in ((0, 1), (1, 0)):
        HA, HC = b[(b.match_id % 2) == a], b[(b.match_id % 2) == c]
        TA = r.player_table(HA, role)[0]; TC = r.player_table(HC, role)[0]
        S = signals(HA.match_id.unique(), role)
        f = TA[["press_skill", "pb"]].join(S, how="left").join(target(HC, role).rename("y"), how="inner").join(TC[["pb"]].rename(columns={"pb": "pbB"}))
        f = f[(f.pb >= 50) & (f.pbB >= 50)].copy()
        for sname in sig_names: f[sname] = f[sname].fillna(f[sname].median())
        f["rep"] = sum(z(f[s_]) for s_ in sig_names) / len(sig_names)
        f["dir"] = f"{a}->{c}"; frames.append(f)
    def score(pred_fn):
        return float(np.mean([pred_fn(f).corr(f.y) for f in frames]))
    base = lambda f: z(f.press_skill)
    variants = {"current model": base}
    for s_ in sig_names:
        variants[f"reputation alone: {s_}"] = (lambda s_: (lambda f: f[s_]))(s_)
    variants["reputation alone: all signals"] = lambda f: f.rep
    for s_ in sig_names:
        variants[f"current + {s_} (0.25)"] = (lambda s_: (lambda f: base(f) + 0.25 * z(f[s_])))(s_)
    for lam in (0.1, 0.25, 0.5, 1.0):
        variants[f"current + all reputation ({lam})"] = (lambda lam: (lambda f: base(f) + lam * z(f.rep)))(lam)
    for name, fn in variants.items():
        rows.append(dict(role=role, variant=name, predicts_other_half=round(score(fn), 3), players=len(frames[0])))
    # paired bootstrap over players for the best combined variant vs current
    best = max([k for k in variants if k.startswith("current +")], key=lambda k: score(variants[k]))
    diffs = []
    for _ in range(1000):
        ds = []
        for f in frames:
            i = rng.integers(0, len(f), len(f)); fb = f.iloc[i]
            ds.append(variants[best](fb).corr(fb.y) - base(fb).corr(fb.y))
        diffs.append(np.mean(ds))
    diffs = np.array(diffs)
    boot_rows.append(dict(role=role, best_variant=best, gain=round(score(variants[best]) - score(base), 3),
                          ci95=f"{np.percentile(diffs, 2.5):+.3f} to {np.percentile(diffs, 97.5):+.3f}",
                          share_of_resamples_better=round(float((diffs > 0).mean()), 2)))
    # how correlated are reputation and the current rating?
    rows.append(dict(role=role, variant="(corr of reputation with current rating)", predicts_other_half=round(float(np.mean([f.rep.corr(f.press_skill) for f in frames])), 3), players=len(frames[0])))

pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 60)
res = pd.DataFrame(rows); print(res.to_string(index=False)); print()
bt = pd.DataFrame(boot_rows); print(bt.to_string(index=False))
res.to_csv(f"{OUT}/reputation_test.csv", index=False); bt.to_csv(f"{OUT}/reputation_bootstrap.csv", index=False)
