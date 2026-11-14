"""Step 2: win-probability (dynamic-programming Markov model), Leverage Index (pressure),
attributable WPA and run value.
Usage: python -I 02_pressure.py <out_dir>
"""
import sys, json, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

OUT = sys.argv[1]
b = pd.read_pickle(f"{OUT}/balls_state.pkl")

# ---------- scoring environments ----------
# IPL changed sharply from 2024 (Impact Player rule) -> treat as its own environment
b["env"] = np.select([(b.league == "IPL") & (b.season.astype(str) >= "2024"), b.league == "IPL"], [0, 1], 2)
# ---------- pre-match team strength (Elo), updated only after each match: no look-ahead ----------
_m = (b.groupby("match_id").agg(d=("match_date", "first"), win=("win_team_id", "first"),
                                 t1=("batting_team_id", "first")).sort_values(["d"]))
_m["t2"] = b[b.innings == 2].groupby("match_id").batting_team_id.first()
ELO_K, elo, pre = 24, {}, {}
for mid, r in _m.iterrows():
    e1, e2 = elo.get(r.t1, 1500.0), elo.get(r.t2, 1500.0); pre[mid] = e1 - e2
    exp1 = 1 / (1 + 10 ** (-(e1 - e2) / 400)); s1 = 1.0 if r.win == r.t1 else 0.0
    elo[r.t1] = e1 + ELO_K * (s1 - exp1); elo[r.t2] = e2 - ELO_K * (s1 - exp1)
# batting side minus fielding side, in hundreds of Elo points
b["elo_bat"] = b.match_id.map(pre) * np.where(b.innings == 1, 1, -1) / 100

OUTC = ["0", "1", "2", "3", "4", "6", "W", "wd", "nb"]
RUNS = np.array([0, 1, 2, 3, 4, 6, 0, 1, 2]); CONS = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0])
WK = np.array([0, 0, 0, 0, 0, 0, 1, 0, 0])
def _o(w, n, k, t):
    if w: return "wd"
    if n: return "nb"
    if k: return "W"
    return {5: "4", 7: "6"}.get(t, str(t)) if t <= 7 else "6"
b["outc"] = [_o(w, n, k, t) for w, n, k, t in zip(b.is_wide, b.is_nb, b.wkt, b.total_runs)]
b.loc[~b.outc.isin(OUTC), "outc"] = "6"
b["ph"] = np.select([b.balls_rem > 84, b.balls_rem > 30], [0, 1], 2)     # PP / middle / death
b["wb"] = np.select([b.wih <= 3, b.wih <= 6], [0, 1], 2)                  # wickets-in-hand bucket
RRR_EDGES = np.array([0.9, 1.1, 1.3, 1.5, 1.75, 2.1, 2.6])               # required runs per ball
b["rb"] = np.where(b.innings == 2, np.searchsorted(RRR_EDGES, b.need.fillna(0) / np.maximum(b.balls_rem, 1)), 0)

def prob_table(df, keys, shape, prior_keys, alpha=30):
    """Smoothed outcome distribution: cell counts + alpha pseudo-counts from a coarser cell."""
    oi = df.outc.map({o: i for i, o in enumerate(OUTC)}).values
    cnt = np.zeros(shape + (9,))
    np.add.at(cnt, tuple(df[k].values for k in keys) + (oi,), 1)
    coarse = np.zeros(shape[:len(prior_keys)] + (9,))
    np.add.at(coarse, tuple(df[k].values for k in prior_keys) + (oi,), 1)
    coarse = coarse / coarse.sum(-1, keepdims=True)
    exp = coarse.reshape(coarse.shape[:len(prior_keys)] + (1,) * (len(shape) - len(prior_keys)) + (9,))
    p = cnt + alpha * exp
    return p / p.sum(-1, keepdims=True)

i1, i2 = b[b.innings == 1], b[b.innings == 2]
P1b = prob_table(i1, ["env", "ph", "wb"], (3, 3, 3), ["env", "ph"])
P2b = prob_table(i2, ["env", "ph", "wb", "rb"], (3, 3, 3, 8), ["env", "ph"])
WB = np.array([0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 2])          # wickets in hand -> band
def refine(df, keys, shape, prior, alpha=40):
    """Full wickets-in-hand resolution, smoothed toward the band-level table."""
    oi = df.outc.map({o: i for i, o in enumerate(OUTC)}).values
    cnt = np.zeros(shape + (9,))
    np.add.at(cnt, tuple(df[k].values for k in keys) + (oi,), 1)
    p = cnt + alpha * prior
    return p / p.sum(-1, keepdims=True)
P1 = refine(i1, ["env", "ph", "wih"], (3, 3, 11), P1b[:, :, WB])
P2 = refine(i2, ["env", "ph", "wih", "rb"], (3, 3, 11, 8), P2b[:, :, WB])
def ph_of(br): return 0 if br > 84 else (1 if br > 30 else 2)
def wb_of(w): return 0 if w <= 3 else (1 if w <= 6 else 2)
NMAX = 320
NS = np.arange(1, NMAX + 1)

# ---------- 2nd innings: V2[env, balls_rem, wih, need] = P(chaser wins) ----------
V2 = np.zeros((3, 121, 11, NMAX + 1))
V2[:, :, :, 0] = 1.0
for e in range(3):
    V = V2[e]
    V[0, 1:, 1] = 0.5                 # scores level after last ball -> super over ~ coin flip
    for br in range(1, 121):
        ph = ph_of(br)
        rbs = np.minimum(np.searchsorted(RRR_EDGES, NS / br), 7)
        for w in range(1, 11):
            p = P2[e, ph, w][rbs]                  # (NMAX, 9) outcome probs per need
            legal = np.zeros(NMAX)
            for j in range(7):
                nn = np.maximum(NS - RUNS[j], 0)
                legal += p[:, j] * V[br - 1, w - WK[j], nn]
            # extras (wd: -1 need, nb: -2 need) at same (br, w): solve ascending in need
            row = V[br, w]
            pw, pn = p[:, 7], p[:, 8]
            for i, n in enumerate(NS):
                row[n] = legal[i] + pw[i] * row[max(n - 1, 0)] + pn[i] * row[max(n - 2, 0)]

# ---------- 1st innings: distribution of remaining runs D1[env, balls_rem, wih, k] ----------
D1 = np.zeros((3, 121, 11, NMAX + 1)); D1[:, 0, :, 0] = 1; D1[:, :, 0, 0] = 1
for e in range(3):
    for br in range(1, 121):
        for w in range(1, 11):
            p = P1[e, ph_of(br), w]
            d = np.zeros(NMAX + 1)
            for j in range(7):
                src = D1[e, br - 1, w - WK[j]]; r = RUNS[j]
                d[r:] += p[j] * src[:NMAX + 1 - r]
            # extras before the legal ball: geometric number of extras, each worth 1 (wd) or 2 (nb)
            # convolve with the distribution of extra runs (truncate at 3 extras)
            pe = p[7] + p[8]
            legal_share = 1 - pe
            out = legal_share * d.copy() / legal_share   # zero extras weight handled below
            tot = np.zeros(NMAX + 1); cur = d.copy(); weight = legal_share
            # P(k extras) = pe^k * (1-pe); runs per extra: 1 w.p. p7/pe, 2 w.p. p8/pe
            for k in range(4):
                tot += (pe ** k) * (1 - pe) * cur
                nxt = np.zeros(NMAX + 1)
                nxt[1:] += (p[7] / pe) * cur[:-1]; nxt[2:] += (p[8] / pe) * cur[:-2]
                cur = nxt
            D1[e, br, w] = tot / tot.sum()
win_given_total = 1 - V2[:, 120, 10, np.clip(np.arange(NMAX + 1) + 1, 0, NMAX)]   # [env, total]
V1 = np.zeros((3, 121, 11, NMAX + 1))
for e in range(3):
    wgt = np.concatenate([win_given_total[e], np.ones(NMAX + 1)])
    for r in range(NMAX + 1):
        V1[e, :, :, r] = D1[e] @ wgt[r:r + NMAX + 1]

# ---------- lookup + Platt calibration per innings ----------
def raw_wp(inn, env, br, w, runs, need):
    br = np.clip(np.asarray(br), 0, 120).astype(int); w = np.clip(np.asarray(w), 0, 10).astype(int)
    env = np.asarray(env).astype(int)
    r1 = np.clip(np.nan_to_num(np.asarray(runs, float)), 0, NMAX).astype(int)
    n2 = np.clip(np.nan_to_num(np.asarray(need, float)), 0, NMAX).astype(int)
    return np.where(np.asarray(inn) == 1, V1[env, br, w, r1], V2[env, br, w, n2])
eps = 1e-4
def logit(p): p = np.clip(p, eps, 1 - eps); return np.log(p / (1 - p))
# calibration: logistic on [logit(raw Markov WP), pre-match Elo difference] per innings
cal = {}
for inn, d in [(1, i1), (2, i2)]:
    x = logit(raw_wp(inn, d.env, d.balls_rem, d.wih, d.runs_before, d.need))
    cal[inn] = LogisticRegression(C=1e6).fit(np.c_[x, d.elo_bat.values], d.bat_won)
def wp(inn, env, br, w, runs, need, elo_bat):
    raw = raw_wp(inn, env, br, w, runs, need); inn = np.asarray(inn); out = raw.copy()
    elo_bat = np.asarray(elo_bat)
    for k in (1, 2):
        m = (inn == k) & (raw > eps) & (raw < 1 - eps)
        if m.any(): out[m] = cal[k].predict_proba(np.c_[logit(raw[m]), elo_bat[m]])[:, 1]
    return out
def state_wp(runs_add=0, cons=0, wkt=0):
    runs_add, cons, wkt = (np.broadcast_to(np.asarray(x), (len(b),)) for x in (runs_add, cons, wkt))
    return wp(b.innings.values, b.env.values, b.balls_rem.values - cons, b.wih.values - wkt,
              b.runs_before.values + runs_add, b.need.values - runs_add, b.elo_bat.values)

b["wp_before"] = state_wp()
b["wp_raw"] = raw_wp(b.innings.values, b.env.values, b.balls_rem.values, b.wih.values,
                     b.runs_before.values, b.need.values)        # Markov output before calibration
fit = {f"inn{inn}": dict(logloss=round(log_loss(d.bat_won, d.wp_before.clip(eps, 1 - eps)), 4),
                         brier=round(brier_score_loss(d.bat_won, d.wp_before), 4),
                         auc=round(roc_auc_score(d.bat_won, d.wp_before), 4))
       for inn, d in b.groupby("innings")}
calib = b.groupby(pd.cut(b.wp_before, np.linspace(0, 1, 11)), observed=True).agg(
    pred=("wp_before", "mean"), actual=("bat_won", "mean"), n=("bat_won", "size")).round(3)

# ---------- Leverage Index ----------
Pball = np.where((b.innings == 1).values[:, None], P1[b.env, b.ph, b.wih], P2[b.env, b.ph, b.wih, b.rb])
li_raw = np.zeros(len(b))
for j in range(9):
    li_raw += Pball[:, j] * np.abs(state_wp(RUNS[j], CONS[j], WK[j]) - b.wp_before.values)
b["li"] = li_raw / li_raw.mean()
b.loc[b.knock_out == 1, "li"] *= 1.2            # stakes multiplier for knockout games
# pressure = top quarter of Leverage within the same innings (1st-innings balls swing results less
# in absolute terms, but a collapse while setting a total is still the pressure moment of that innings)
thr = b.groupby("innings").li.quantile(0.75).to_dict()
b["li_pct"] = b.groupby("innings").li.rank(pct=True)
b["pressure"] = b.li_pct >= 0.75
b["extreme"] = b.li_pct >= 0.90

# ---------- attributable WPA ----------
wb_ = b.wp_before.values; lg = b.legal.values.astype(int)
b["wpa_bat"] = np.where(b.faced, state_wp(b.bat_runs.values, lg, b.striker_out.values.astype(int)) - wb_, 0.0)
b["wpa_bowl"] = -(state_wp(b.bowler_runs.values, lg, b.bowler_wkt.values.astype(int)) - wb_)

# ---------- run value (expected-runs framework from the same Markov model) ----------
ER = (D1 * np.arange(NMAX + 1)).sum(-1)
def R(br, w, env): return ER[np.asarray(env).astype(int), np.clip(br, 0, 120).astype(int), np.clip(w, 0, 10).astype(int)]
R0 = R(b.balls_rem.values, b.wih.values, b.env.values)
b["rv_bat"] = np.where(b.faced, b.bat_runs + R(b.balls_rem.values - lg, b.wih.values - b.striker_out.values.astype(int), b.env.values) - R0, 0.0)
b["rv_bowl"] = -(b.bowler_runs + R(b.balls_rem.values - lg, b.wih.values - b.bowler_wkt.values.astype(int), b.env.values) - R0)

# ---------- conventional (hand-crafted) pressure index for comparison ----------
rrr_rel = b.need / np.maximum(b.balls_rem, 1) / (b.par / 120)
alt2 = np.clip(rrr_rel, 0, 3) * (1 + (10 - b.wih) / 10) * (1 + (120 - b.balls_rem) / 120)
early_wkts = np.clip((10 - b.wih) - (120 - b.balls_rem) / 20, 0, 10)
alt1 = (1 + early_wkts / 3) * (1 + (b.ph == 2))
b["alt_pi"] = np.where(b.innings == 2, alt2, alt1)
b["alt_pressure"] = b.groupby("innings").alt_pi.transform(lambda s: s >= s.quantile(0.75))

b.to_pickle(f"{OUT}/balls_scored.pkl")
np.save(f"{OUT}/V2.npy", V2); np.save(f"{OUT}/ER.npy", ER)
info = dict(fit=fit, calibration_coefs={k: [round(float(c), 4) for c in v.coef_[0]] + [round(float(v.intercept_[0]), 4)] for k, v in cal.items()}, li_threshold={int(k): round(v, 3) for k, v in thr.items()},
            share_pressure_by_innings=b.groupby("innings").pressure.mean().round(3).to_dict(),
            share_pressure_by_phase=b.groupby("phase").pressure.mean().round(3).to_dict(),
            agreement_alt=round(float((b.pressure == b.alt_pressure).mean()), 3),
            spearman_alt=round(float(b.li.rank().corr(b.alt_pi.rank())), 3))
json.dump(info, open(f"{OUT}/pressure_info.json", "w"), indent=1)
calib.to_csv(f"{OUT}/wp_calibration.csv")
print(json.dumps(info, indent=1)); print(calib)
