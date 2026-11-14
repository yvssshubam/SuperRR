"""Variant of player_table with three optional additions:
  cond    - match-conditions adjustment: leave-player-out match scoring level (shrunk), fitted jointly
            with the player and opponent effects
  rbctx   - name of a required-rate band column added to the context cell (0 in first innings)
  oppteam - opponent effects shrunk toward the opponent's team level instead of toward zero
Everything else is identical to 03_ratings.player_table."""
import numpy as np, pandas as pd

def loo_match(r, d, col, pid, wcol, key="match_id"):
    """Shrunk mean of `col` over the other players' balls in the same match (both innings) or venue."""
    f = d["f"] if "f" in d else 1.0
    x = d.assign(_wv=d[col] * d[wcol], _w=d[wcol], _w2f=d[wcol] ** 2 / f)
    _, k, _ = r.shrink_mean(d, key, col, wcol)
    gm = x.groupby(key)[["_wv", "_w", "_w2f"]].sum()
    gp = x.groupby([key, pid])[["_wv", "_w", "_w2f"]].sum()
    mk = pd.MultiIndex.from_arrays([d[key].values, d[pid].values])
    gpv = gp.reindex(mk).values; gmv = gm.reindex(d[key].values).values
    S, W, W2 = (gmv - gpv).T
    ok = W > 1e-9
    mean = np.where(ok, S / np.where(ok, W, 1), 0.0); neff = np.where(ok, W ** 2 / np.where(ok, W2, 1), 0.0)
    return mean * neff / (neff + k), k

def pt(r, b, role, wcol="w", cond=False, rbctx=None, oppteam=False, npass=3):
    b = b[b[wcol] > 0]
    if role == "bat":
        d = b[b.faced].copy(); pid, val, wpa, opp, oteam = "striker_id", "rv_bat", "wpa_bat", "bowler_id", "bowling_team_id"
    else:
        d = b[b.legal | b.is_wide | b.is_nb].copy(); pid, val, wpa, opp, oteam = "bowler_id", "rv_bowl", "wpa_bowl", "striker_id", "batting_team_id"
    CTX = list(r.CTX) + ([rbctx] if rbctx else [])
    arm = np.where(d.bowling_type.str.lower().str.startswith("left") | d.bowling_type.str.contains("left-arm", case=False), "L", "R")
    d["matchup"] = d.pace_or_spin.astype(str) + "-" + arm + "-" + d.batting_type.astype(str)
    for v in (val, wpa):
        d[v + "_r"] = d[v] - d.groupby(CTX)[v].transform("mean")
        if v == val: d["r0"] = d[v + "_r"]            # plain context residual (targets)
        if r.USE_MATCHUP[role]:
            d[v + "_r"] = d[v + "_r"] - d.groupby(["matchup", "ph"])[v + "_r"].transform("mean")
    eff_p = pd.Series(0.0, index=d[pid].unique()); d["_m"] = 0.0; d["_o"] = 0.0; info = {}
    for _ in range(npass):
        d["_t"] = d[val + "_r"] - d[pid].map(eff_p) - d["_m"]
        if oppteam:
            et, _, _ = r.shrink_mean(d, oteam, "_t", wcol); d["_ot"] = d[oteam].map(et)
            d["_t"] = d["_t"] - d["_ot"]
            eo, _, _ = r.shrink_mean(d, opp, "_t", wcol); d["_o"] = d["_ot"] + d[opp].map(eo)
        else:
            eo, _, _ = r.shrink_mean(d, opp, "_t", wcol); d["_o"] = d[opp].map(eo)
        d["_t"] = d[val + "_r"] - d["_o"] - d["_m"]
        eff_p, _, _ = r.shrink_mean(d, pid, "_t", wcol)
        if cond:
            d["_t"] = d[val + "_r"] - d["_o"] - d[pid].map(eff_p)
            if cond == "vm":      # venue level first, then the match's deviation from its venue
                d["_v"], info["k_venue"] = loo_match(r, d, "_t", pid, wcol, key="venue_id")
                d["_t"] = d["_t"] - d["_v"]
                mm, info["k_match"] = loo_match(r, d, "_t", pid, wcol); d["_m"] = d["_v"] + mm
            elif cond == "v":
                d["_m"], info["k_venue"] = loo_match(r, d, "_t", pid, wcol, key="venue_id")
            else:
                d["_m"], info["k_match"] = loo_match(r, d, "_t", pid, wcol)
    d["adj"] = d[val + "_r"] - d["_o"] - d["_m"]
    d["wpa_adj"] = d[wpa + "_r"]
    P, N = d[d.pressure], d[~d.pressure]
    A, clutch, base, beta, tau2, nA = r.hier(P, N, pid, "adj", wcol)
    kA = dict(beta=round(beta, 3), clutch_sd_per100=round(100 * np.sqrt(tau2), 2), **info)
    Bn, _, _ = r.shrink_mean(N, pid, "adj", wcol)
    allp = A.index.union(Bn.index)
    A = A.reindex(allp).fillna(beta * Bn.reindex(allp).fillna(0.0)); clutch = clutch.reindex(allp).fillna(0.0)
    base = base.reindex(allp).fillna(Bn.reindex(allp)).fillna(0.0)
    Wi, _, _ = r.shrink_mean(P, pid, "wpa_adj", wcol); Wi = Wi.reindex(allp).fillna(0.0)
    pm = P.groupby([pid, "match_id"]).agg(v=("adj", "sum"), n=("adj", "size"), w=(wcol, "first"))
    pm = pm[pm.n >= 3]; prior = (pm.v > 0).mean()
    cons = pm.assign(pos=(pm.v > 0) * pm.w).groupby(level=0).agg(pos=("pos", "sum"), w=("w", "sum"))
    C = ((cons.pos + 6 * prior) / (cons.w + 6)).reindex(allp).fillna(prior)
    t = pd.DataFrame({"press_skill": A * 100, "baseline": base * 100, "win_impact": Wi * 1000,
                      "consistency": C, "clutch_delta": clutch * 100})
    t["raw_press"] = P.groupby(pid).adj.mean() * 100
    t = t.join(P.groupby(pid).agg(pb=("adj", "size"), pm=("match_id", "nunique")), how="left")
    t["recent_pb"] = P[P.recent].groupby(pid).size().reindex(t.index).fillna(0).astype(int)
    t["active"] = t.index.isin(d.loc[d.recent, pid])
    t["n_matches_all"] = d.groupby(pid).match_id.nunique()
    t["cond_press"] = (P["_m"] * P[wcol]).groupby(P[pid]).sum() / P.groupby(pid)[wcol].sum() * 100   # avg match level on his pressure balls
    t["opp_press"] = (P["_o"] * P[wcol]).groupby(P[pid]).sum() / P.groupby(pid)[wcol].sum() * 100
    return t, kA, d
